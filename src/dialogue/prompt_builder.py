"""Prompt construction utilities for the dialogue system."""

from __future__ import annotations

from typing import Optional


class PromptBuilder:
    """Builds structured message lists for different conversation scenarios."""

    # ------------------------------------------------------------------
    # RAG-augmented prompt
    # ------------------------------------------------------------------

    def build_rag_prompt(
        self,
        query: str,
        context_chunks: list[dict],
        history: list[dict],
        user_memories: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Build a RAG prompt with retrieved knowledge, history, and user memories.

        Args:
            query: The current user query.
            context_chunks: Retrieved knowledge chunks, each with keys
                ``title``, ``snippet``, ``url``, and optionally ``score``.
            history: Recent conversation turns (list of role/content dicts).
            user_memories: Optional personal memories for the user.

        Returns:
            A list of message dicts ready to send to the LLM.
        """
        # --- system message ---
        references = self._format_references(context_chunks)
        memory_section = self._format_memories(user_memories) if user_memories else ""

        system_content = (
            "你是北京邮电大学(BUPT)智能校园助理，为师生提供准确、有用的校园信息服务。\n\n"
            "回答要求：\n"
            "1. 请基于提供的参考资料回答问题，并在回答中引用来源编号，如[1]、[2]\n"
            "2. 如果参考资料中没有相关信息，请坦诚说明你不确定，不要编造答案\n"
            "3. 请使用中文回答\n"
            "4. 回答应简洁、准确、有条理\n"
        )
        if references:
            system_content += f"\n参考资料：\n{references}\n"
        if memory_section:
            system_content += f"\n用户相关记忆：\n{memory_section}\n"

        messages: list[dict] = [{"role": "system", "content": system_content}]

        # --- conversation history (last 5 turns) ---
        recent_history = history[-10:]  # 5 turns = 10 messages (user + assistant)
        for msg in recent_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # --- current query ---
        messages.append({"role": "user", "content": query})
        return messages

    # ------------------------------------------------------------------
    # Chitchat prompt
    # ------------------------------------------------------------------

    def build_chitchat_prompt(
        self, query: str, history: list[dict]
    ) -> list[dict]:
        """Build a simple chitchat prompt without knowledge retrieval.

        Args:
            query: The current user query.
            history: Recent conversation turns.

        Returns:
            A list of message dicts.
        """
        system_content = (
            "你是北京邮电大学(BUPT)智能校园助理。\n"
            "用户正在与你闲聊，请友好、自然地回复。\n"
            "请使用中文回答，语气亲切。"
        )
        messages: list[dict] = [{"role": "system", "content": system_content}]

        recent_history = history[-10:]
        for msg in recent_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": query})
        return messages

    # ------------------------------------------------------------------
    # Task execution prompt
    # ------------------------------------------------------------------

    def build_task_prompt(
        self, query: str, task_type: str, context: dict
    ) -> list[dict]:
        """Build a task-execution prompt with a confirmation step.

        Args:
            query: The current user query.
            task_type: Type of task (e.g. ``"repair"``, ``"booking"``).
            context: Additional context for the task (extracted entities, etc.).

        Returns:
            A list of message dicts.
        """
        context_str = "\n".join(f"- {k}: {v}" for k, v in context.items()) if context else "无"

        system_content = (
            "你是北京邮电大学(BUPT)智能校园助理，正在帮助用户执行任务。\n\n"
            f"任务类型: {task_type}\n"
            f"已知信息:\n{context_str}\n\n"
            "操作步骤：\n"
            "1. 确认用户的任务需求和关键信息\n"
            "2. 如果信息不完整，请礼貌地询问缺失信息\n"
            "3. 信息完整后，向用户确认操作详情，等待用户确认后再执行\n"
            "4. 请使用中文回答\n"
        )
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]
        return messages

    # ------------------------------------------------------------------
    # Source / reference formatting
    # ------------------------------------------------------------------

    def format_sources(self, sources: list[dict]) -> str:
        """Format source references for display to the user.

        Args:
            sources: List of source dicts with ``title``, ``snippet``, and
                optional ``url``.

        Returns:
            A formatted string like ``[1] title - snippet (url)``.
        """
        if not sources:
            return ""
        lines: list[str] = []
        for idx, src in enumerate(sources, start=1):
            title = src.get("title", "未知来源")
            snippet = src.get("snippet", "")
            url = src.get("url", "")
            line = f"[{idx}] {title} - {snippet}"
            if url:
                line += f" ({url})"
            lines.append(line)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_references(self, chunks: list[dict]) -> str:
        """Format retrieved chunks as numbered references for the system prompt."""
        if not chunks:
            return ""
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            title = chunk.get("title", "")
            snippet = chunk.get("snippet", "")
            lines.append(f"[{idx}] {title}: {snippet}")
        return "\n".join(lines)

    def _format_memories(self, memories: list[dict]) -> str:
        """Format user memories for inclusion in the system prompt."""
        if not memories:
            return ""
        lines: list[str] = []
        for mem in memories:
            content = mem.get("content", "") or mem.get("summary", "")
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines)
