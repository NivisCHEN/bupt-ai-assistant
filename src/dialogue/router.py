"""Intent router – classifies user queries and extracts entities."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from src.models import IntentResult, IntentType

if TYPE_CHECKING:
    from src.llm.client import LLMClient


class IntentRouter:
    """Routes a user query to the appropriate processing pipeline."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    async def classify(self, query: str) -> IntentResult:
        """Classify the user query and extract entities.

        Args:
            query: The raw user query string.

        Returns:
            An :class:`IntentResult` containing the detected intent,
            confidence score, and extracted entities.
        """
        system_prompt = (
            "你是北京邮电大学智能校园助理的意图识别模块。\n"
            "请根据用户的输入，判断其意图类别并提取关键实体。\n\n"
            "意图类别说明：\n"
            "- KNOWLEDGE: 校园知识查询，如课程安排、图书馆开放时间、校园导航等\n"
            "- CHITCHAT: 日常闲聊、问候、情感交流等非任务性对话\n"
            "- TASK_EXECUTION: 需要执行具体操作的任务，如报修申请、场地预约、成绩查询等\n"
            "- CLARIFICATION: 用户输入信息不足或模糊，需要进一步澄清\n\n"
            "请严格以JSON格式返回，不要包含其他文字。\n"
            "格式:\n"
            "{\n"
            '  "intent": "<KNOWLEDGE|CHITCHAT|TASK_EXECUTION|CLARIFICATION>",\n'
            '  "confidence": <0.0-1.0>,\n'
            '  "entities": {<提取的实体键值对>}\n'
            "}"
        )
        try:
            raw = await self.llm_client.generate(query, system_prompt=system_prompt)
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(raw)

            intent_str = parsed.get("intent", "KNOWLEDGE").upper()
            try:
                intent = IntentType(intent_str.lower())
            except ValueError:
                # Map uppercase names to enum values
                intent_map = {
                    "KNOWLEDGE": IntentType.KNOWLEDGE,
                    "CHITCHAT": IntentType.CHITCHAT,
                    "TASK_EXECUTION": IntentType.TASK_EXECUTION,
                    "CLARIFICATION": IntentType.CLARIFICATION,
                }
                intent = intent_map.get(intent_str, IntentType.KNOWLEDGE)

            confidence = float(parsed.get("confidence", 0.5))
            entities = parsed.get("entities", {})

            return IntentResult(
                intent=intent,
                confidence=confidence,
                entities=entities,
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Intent classification failed, falling back to KNOWLEDGE: {}", exc)
            return IntentResult(
                intent=IntentType.KNOWLEDGE,
                confidence=0.0,
                entities={},
            )
        except Exception:
            logger.exception("Unexpected error during intent classification")
            return IntentResult(
                intent=IntentType.KNOWLEDGE,
                confidence=0.0,
                entities={},
            )
