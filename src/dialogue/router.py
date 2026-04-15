"""Intent router – classifies user queries and extracts entities.

Uses keyword-based matching instead of an LLM call to keep per-request
latency low. The previous LLM-based classifier added 3~10s per chat for
a task that, in this domain, can be handled with simple pattern matching.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from src.models import IntentResult, IntentType

if TYPE_CHECKING:
    from src.llm.client import LLMClient


# Keywords that strongly indicate the user wants the assistant to *do*
# something on their behalf (form submission, lookup, booking ...).
_TASK_KEYWORDS: tuple[str, ...] = (
    "申请", "预约", "报修", "提交", "办理", "注册", "登记", "报名",
    "帮我", "帮忙", "代我", "替我",
    "查询我的", "查我的", "查一下我", "我的成绩", "我的课表",
    "选课", "退课", "改密码", "修改密码", "重置",
    "打印", "导出", "下载",
)

# Keywords for casual/social interactions.
_CHITCHAT_KEYWORDS: tuple[str, ...] = (
    "你好", "您好", "嗨", "hi", "hello", "哈喽", "在吗", "在不在",
    "谢谢", "感谢", "多谢", "thanks", "thank you",
    "再见", "拜拜", "bye",
    "哈哈", "呵呵", "嘻嘻", "嘿嘿",
    "你是谁", "你叫什么", "你好棒", "你真厉害",
    "无聊", "聊天", "陪我聊", "心情",
)

# Keywords that suggest a campus-knowledge question.
_KNOWLEDGE_KEYWORDS: tuple[str, ...] = (
    "图书馆", "食堂", "宿舍", "教室", "校车", "校园卡", "一卡通",
    "课程", "课表", "上课", "选修", "必修", "学分", "考试", "成绩",
    "教务", "教学", "通知", "公告", "新闻",
    "老师", "教授", "导师", "辅导员", "学院", "专业",
    "校园", "校区", "校门", "校史", "学校", "北邮", "bupt",
    "怎么走", "在哪", "在哪里", "几点", "什么时候", "如何", "怎么",
    "是什么", "什么是", "为什么", "为何",
)


class IntentRouter:
    """Routes a user query to the appropriate processing pipeline.

    Implementation note: ``llm_client`` is kept as a constructor argument
    for backward compatibility with callers that still pass it, but the
    classifier no longer invokes the LLM.
    """

    def __init__(self, llm_client: "LLMClient | None" = None) -> None:
        self.llm_client = llm_client

    async def classify(self, query: str) -> IntentResult:
        """Classify the user query using keyword matching.

        Args:
            query: The raw user query string.

        Returns:
            An :class:`IntentResult` containing the detected intent,
            confidence score, and (currently empty) extracted entities.
        """
        if not query or not query.strip():
            return IntentResult(
                intent=IntentType.CLARIFICATION,
                confidence=1.0,
                entities={},
            )

        normalized = query.strip().lower()

        # Very short / vague inputs need clarification before we spend a
        # full retrieval+generation cycle on them.
        if len(normalized) <= 2:
            return IntentResult(
                intent=IntentType.CLARIFICATION,
                confidence=0.8,
                entities={},
            )

        task_hits = sum(1 for kw in _TASK_KEYWORDS if kw in normalized)
        chitchat_hits = sum(1 for kw in _CHITCHAT_KEYWORDS if kw in normalized)
        knowledge_hits = sum(1 for kw in _KNOWLEDGE_KEYWORDS if kw in normalized)

        scores: dict[IntentType, int] = {
            IntentType.TASK_EXECUTION: task_hits,
            IntentType.CHITCHAT: chitchat_hits,
            IntentType.KNOWLEDGE: knowledge_hits,
        }

        best_intent, best_score = max(scores.items(), key=lambda kv: kv[1])

        if best_score == 0:
            # No keywords matched; default to KNOWLEDGE so we still try
            # retrieval — most user questions about BUPT fall here.
            logger.debug("No intent keywords matched; defaulting to KNOWLEDGE")
            return IntentResult(
                intent=IntentType.KNOWLEDGE,
                confidence=0.4,
                entities={},
            )

        # Confidence: 0.6 baseline + 0.1 per extra hit, capped at 0.95.
        confidence = min(0.95, 0.6 + 0.1 * (best_score - 1))

        return IntentResult(
            intent=best_intent,
            confidence=confidence,
            entities={},
        )
