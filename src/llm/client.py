"""LLM client wrapping an OpenAI-compatible API (DeepSeek by default)."""

from __future__ import annotations

import json
from typing import AsyncIterator, Optional

from loguru import logger
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Only retry on transient network/rate-limit errors. Business errors
# (auth, bad request, model returned garbage) should surface immediately
# so the frontend doesn't wait through ~30s of exponential backoff.
_TRANSIENT_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)

# Per-request timeout handed to the OpenAI SDK. Combined with
# ``stop_after_attempt(2)`` this caps the worst case around ~2 minutes.
_REQUEST_TIMEOUT_SECS = 60.0


class LLMClient:
    """Async wrapper around an OpenAI-compatible LLM endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_REQUEST_TIMEOUT_SECS,
        )

    # ------------------------------------------------------------------
    # Core generation helpers
    # ------------------------------------------------------------------

    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> str:
        """Generate a completion from a single user prompt.

        Args:
            prompt: The user message.
            system_prompt: Optional system-level instruction.

        Returns:
            The assistant's response text.
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return await self.generate_with_messages(messages)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(_TRANSIENT_ERRORS),
        before_sleep=lambda rs: logger.warning(
            "LLM call failed (attempt {}), retrying...", rs.attempt_number,
        ),
        reraise=True,
    )
    async def generate_with_messages(self, messages: list[dict]) -> str:
        """Generate a completion from an arbitrary message list.

        Args:
            messages: A list of ``{"role": ..., "content": ...}`` dicts.

        Returns:
            The assistant's response text.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        except Exception:
            logger.exception("LLM generation failed")
            raise

    async def stream_with_messages(
        self, messages: list[dict]
    ) -> AsyncIterator[str]:
        """Stream a completion token-by-token from an arbitrary message list.

        Yields each non-empty content delta as it arrives. Errors are
        re-raised; the caller is responsible for any retry/fallback.

        Args:
            messages: A list of ``{"role": ..., "content": ...}`` dicts.

        Yields:
            Content chunks (typically a few characters each).
        """
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    async def classify_intent(self, query: str) -> dict:
        """Classify the intent of *query* into one of four categories.

        Returns:
            A dict with keys ``intent`` (str) and ``confidence`` (float).
        """
        system_prompt = (
            "你是一个意图分类器。根据用户输入，将其分类为以下四种意图之一：\n"
            "- KNOWLEDGE: 用户想查询校园知识或信息\n"
            "- CHITCHAT: 用户在闲聊或打招呼\n"
            "- TASK_EXECUTION: 用户想执行某个任务（如报修、预约等）\n"
            "- CLARIFICATION: 用户的问题不够清晰，需要澄清\n\n"
            "请严格以JSON格式返回结果，不要包含其他文字。\n"
            '格式: {"intent": "<INTENT>", "confidence": <0.0-1.0>}'
        )
        try:
            raw = await self.generate(query, system_prompt=system_prompt)
            # Strip possible markdown code fences
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            result = json.loads(raw)
            return {
                "intent": result.get("intent", "KNOWLEDGE"),
                "confidence": float(result.get("confidence", 0.5)),
            }
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to parse intent classification result: {}", exc)
            return {"intent": "KNOWLEDGE", "confidence": 0.0}

    # ------------------------------------------------------------------
    # Profile extraction
    # ------------------------------------------------------------------

    async def extract_profile(self, history_text: str) -> dict:
        """Extract user preferences and behavioural patterns from conversation history.

        Args:
            history_text: Concatenated conversation history.

        Returns:
            A dict containing extracted preferences, frequent topics, etc.
        """
        system_prompt = (
            "你是一个用户画像提取器。根据以下对话历史，提取用户的偏好和行为模式。\n"
            "请以JSON格式返回，包含以下字段：\n"
            '- "preferences": 用户偏好（dict）\n'
            '- "frequent_topics": 用户经常讨论的话题（list）\n'
            '- "summary": 用户画像摘要（string）\n\n'
            "请严格返回JSON，不要包含其他文字。"
        )
        try:
            raw = await self.generate(history_text, system_prompt=system_prompt)
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse profile extraction result: {}", exc)
            return {"preferences": {}, "frequent_topics": [], "summary": ""}
