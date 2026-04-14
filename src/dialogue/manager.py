"""Dialogue manager – main orchestrator for the conversation pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from loguru import logger

from src.models import (
    ChatRequest,
    ChatResponse,
    IntentResult,
    IntentType,
    Source,
)

if TYPE_CHECKING:
    from src.dialogue.prompt_builder import PromptBuilder
    from src.dialogue.router import IntentRouter
    from src.embedding.service import EmbeddingService
    from src.llm.client import LLMClient


class DialogueManager:
    """Central orchestrator that ties intent routing, retrieval, memory, and
    LLM generation together into a single ``handle_message`` flow.
    """

    def __init__(
        self,
        router: IntentRouter,
        retriever: object,
        memory_manager: object,
        llm_client: LLMClient,
        embedding_service: EmbeddingService,
        prompt_builder: PromptBuilder,
    ) -> None:
        self.router = router
        self.retriever = retriever
        self.memory_manager = memory_manager
        self.llm_client = llm_client
        self.embedding_service = embedding_service
        self.prompt_builder = prompt_builder

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def handle_message(self, request: ChatRequest) -> ChatResponse:
        """Process an incoming chat request through the full pipeline.

        Steps:
            1. Classify intent
            2. Retrieve knowledge / user context (if needed)
            3. Fetch recent conversation history
            4. Build the appropriate prompt
            5. Call the LLM
            6. Persist the exchange to short-term memory
            7. Return a structured response

        Args:
            request: The incoming :class:`ChatRequest`.

        Returns:
            A :class:`ChatResponse` with the answer, sources, suggestions,
            and confidence score.
        """
        user_id = request.user_id
        query = request.query

        try:
            messages, sources, intent_result = await self._prepare_generation(
                user_id, query
            )

            # 5. Call LLM
            answer = await self.llm_client.generate_with_messages(messages)

            # 6. Save to short-term memory
            await self._save_exchange(user_id, query, answer)

            # 7. Build and return response
            return self._build_response(answer, sources, intent_result)

        except Exception:
            logger.exception("Error handling message for user={}", user_id)
            return ChatResponse(
                answer="抱歉，处理您的请求时出现了错误，请稍后再试。",
                sources=[],
                suggestions=["请重新提问", "换一种方式描述您的问题"],
                confidence=0.0,
            )

    async def handle_message_stream(
        self, request: ChatRequest
    ) -> AsyncIterator[dict]:
        """Process a chat request and stream the answer token-by-token.

        Yields event dicts suitable for SSE framing:
          * ``{"type": "meta", "sources": [...], "confidence": ..., "intent": ...}``
            emitted once before any tokens.
          * ``{"type": "token", "content": "..."}`` emitted per chunk.
          * ``{"type": "done", "suggestions": [...], "answer": "..."}``
            emitted at the end.
          * ``{"type": "error", "message": "..."}`` if something fails.
        """
        user_id = request.user_id
        query = request.query

        try:
            messages, sources, intent_result = await self._prepare_generation(
                user_id, query
            )
        except Exception:
            logger.exception("Error preparing streaming generation for user={}", user_id)
            yield {
                "type": "error",
                "message": "抱歉，处理您的请求时出现了错误，请稍后再试。",
            }
            return

        source_models = self._sources_to_models(sources)
        yield {
            "type": "meta",
            "intent": intent_result.intent.value,
            "confidence": intent_result.confidence,
            "sources": [s.model_dump(mode="json") for s in source_models],
        }

        collected: list[str] = []
        try:
            async for chunk in self.llm_client.stream_with_messages(messages):
                collected.append(chunk)
                yield {"type": "token", "content": chunk}
        except Exception:
            logger.exception("LLM streaming failed for user={}", user_id)
            yield {
                "type": "error",
                "message": "抱歉，生成回答时出现了错误，请稍后再试。",
            }
            return

        answer = "".join(collected).strip()
        await self._save_exchange(user_id, query, answer)

        suggestions = self._extract_suggestions(answer, intent_result.intent.value)
        yield {
            "type": "done",
            "answer": answer,
            "suggestions": suggestions,
        }

    # ------------------------------------------------------------------
    # Pipeline helpers shared between streaming and non-streaming paths
    # ------------------------------------------------------------------

    async def _prepare_generation(
        self, user_id: str, query: str
    ) -> tuple[list[dict], list[dict], "IntentResult"]:
        """Run the classify → retrieve → history → prompt-build stages.

        Returns:
            ``(messages, sources, intent_result)`` where ``messages`` is the
            prompt ready to feed to the LLM, ``sources`` is the list of
            retrieval hits (raw dicts), and ``intent_result`` carries the
            final intent (possibly downgraded to CLARIFICATION).
        """
        # 1. Classify intent
        intent_result = await self.router.classify(query)
        logger.info(
            "Intent for user={}: intent={}, confidence={:.2f}",
            user_id,
            intent_result.intent.value,
            intent_result.confidence,
        )

        sources: list[dict] = []
        user_memories: list[dict] = []

        # 2. Retrieval (for KNOWLEDGE and TASK_EXECUTION)
        if intent_result.intent in (IntentType.KNOWLEDGE, IntentType.TASK_EXECUTION):
            query_vec = self.embedding_service.encode_query(query)
            sources = await self._retrieve_knowledge(query, query_vec)
            user_memories = await self._retrieve_user_context(user_id, query_vec)

            if self._should_clarify(sources):
                intent_result.intent = IntentType.CLARIFICATION

        # 3. Get recent conversation history
        history: list[dict] = []
        try:
            history = await self.memory_manager.get_recent_history(user_id)  # type: ignore[union-attr]
        except Exception:
            logger.warning("Failed to retrieve conversation history for user={}", user_id)

        # 4. Build prompt based on intent
        if intent_result.intent == IntentType.CHITCHAT:
            messages = self.prompt_builder.build_chitchat_prompt(query, history)
        elif intent_result.intent == IntentType.TASK_EXECUTION:
            task_context = intent_result.entities
            task_type = task_context.pop("task_type", "general")
            messages = self.prompt_builder.build_task_prompt(query, task_type, task_context)
        else:
            # KNOWLEDGE or CLARIFICATION
            messages = self.prompt_builder.build_rag_prompt(
                query, sources, history, user_memories
            )

        return messages, sources, intent_result

    async def _save_exchange(self, user_id: str, query: str, answer: str) -> None:
        """Persist the user/assistant exchange to short-term memory."""
        try:
            await self.memory_manager.save_to_short_term(  # type: ignore[union-attr]
                user_id=user_id,
                query=query,
                response=answer,
            )
        except Exception:
            logger.warning(
                "Failed to save exchange to short-term memory for user={}", user_id
            )

    def _sources_to_models(self, sources: list[dict]) -> list[Source]:
        return [
            Source(
                id=src.get("id", ""),
                title=src.get("title", ""),
                snippet=src.get("snippet", ""),
                url=src.get("url"),
                score=float(src.get("score", 0.0)),
            )
            for src in sources
        ]

    def _build_response(
        self,
        answer: str,
        sources: list[dict],
        intent_result: "IntentResult",
    ) -> ChatResponse:
        return ChatResponse(
            answer=answer,
            sources=self._sources_to_models(sources),
            suggestions=self._extract_suggestions(answer, intent_result.intent.value),
            confidence=intent_result.confidence,
        )

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------

    async def _retrieve_knowledge(self, query: str, query_vec: object) -> list[dict]:
        """Retrieve relevant knowledge chunks from the school index.

        Args:
            query: The user query string.
            query_vec: The query embedding vector.

        Returns:
            A list of source dicts with ``id``, ``title``, ``snippet``,
            ``url``, and ``score``.
        """
        try:
            results = self.retriever.retrieve(query=query, top_k=10)
            return [
                {
                    "id": r.get("id", ""),
                    "title": r.get("metadata", {}).get("title", ""),
                    "snippet": r.get("content", "")[:200],
                    "url": r.get("metadata", {}).get("source_url", ""),
                    "score": r.get("score", 0.0),
                }
                for r in results
            ]
        except Exception:
            logger.warning("Knowledge retrieval failed for query: {}", query)
            return []

    async def _retrieve_user_context(self, user_id: str, query_vec: object) -> list[dict]:
        """Retrieve personal context from user memory.

        Args:
            user_id: The user identifier.
            query_vec: The query embedding vector.

        Returns:
            A list of memory dicts.
        """
        try:
            results = await self.memory_manager.search_memories(  # type: ignore[union-attr]
                user_id=user_id,
                query_vector=query_vec,
            )
            return results if isinstance(results, list) else []
        except Exception:
            logger.warning("User context retrieval failed for user={}", user_id)
            return []

    # ------------------------------------------------------------------
    # Decision helpers
    # ------------------------------------------------------------------

    def _should_clarify(self, retrieval_results: list, threshold: float = 0.6) -> bool:
        """Determine whether the system should ask for clarification.

        Returns ``True`` if the top retrieval result's confidence score is
        below *threshold*, indicating the query may be ambiguous.
        """
        if not retrieval_results:
            return True
        top_score = float(retrieval_results[0].get("score", 0.0))
        return top_score < threshold

    def _extract_suggestions(self, answer: str, intent: str) -> list[str]:
        """Generate follow-up suggestions based on the answer and intent.

        Args:
            answer: The generated answer text.
            intent: The classified intent string.

        Returns:
            A list of suggested follow-up queries.
        """
        suggestions: list[str] = []

        if intent == IntentType.KNOWLEDGE.value:
            suggestions = [
                "还有其他相关信息吗？",
                "能详细说明一下吗？",
                "相关的联系方式是什么？",
            ]
        elif intent == IntentType.TASK_EXECUTION.value:
            suggestions = [
                "确认执行",
                "取消操作",
                "查看更多选项",
            ]
        elif intent == IntentType.CHITCHAT.value:
            suggestions = [
                "我想了解校园信息",
                "帮我查一下课程安排",
            ]
        elif intent == IntentType.CLARIFICATION.value:
            suggestions = [
                "我想查询课程信息",
                "我想了解校园设施",
                "我需要报修服务",
            ]

        return suggestions
