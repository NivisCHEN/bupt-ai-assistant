"""Tests for the PromptBuilder."""

import pytest

from src.dialogue.prompt_builder import PromptBuilder


@pytest.fixture()
def builder():
    return PromptBuilder()


# ------------------------------------------------------------------ #
# build_rag_prompt
# ------------------------------------------------------------------ #

class TestBuildRAGPrompt:

    def test_includes_system_message(self, builder):
        messages = builder.build_rag_prompt(
            query="图书馆几点开门？",
            context_chunks=[],
            history=[],
        )
        assert messages[0]["role"] == "system"
        assert "北京邮电大学" in messages[0]["content"]

    def test_includes_sources_in_system(self, builder):
        chunks = [
            {"title": "图书馆", "snippet": "开放时间为8:00-22:00"},
            {"title": "自习室", "snippet": "24小时开放"},
        ]
        messages = builder.build_rag_prompt(
            query="图书馆开放时间",
            context_chunks=chunks,
            history=[],
        )
        system_content = messages[0]["content"]
        assert "参考资料" in system_content
        assert "[1]" in system_content
        assert "[2]" in system_content
        assert "图书馆" in system_content
        assert "8:00-22:00" in system_content

    def test_includes_history(self, builder):
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮您？"},
        ]
        messages = builder.build_rag_prompt(
            query="图书馆在哪？",
            context_chunks=[],
            history=history,
        )
        # history messages + system + current query
        roles = [m["role"] for m in messages]
        assert roles.count("user") == 2  # history user + current query
        assert roles.count("assistant") == 1

    def test_current_query_is_last(self, builder):
        messages = builder.build_rag_prompt(
            query="测试问题",
            context_chunks=[],
            history=[{"role": "user", "content": "之前的问题"}],
        )
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "测试问题"

    def test_includes_user_memories(self, builder):
        memories = [
            {"content": "用户经常问图书馆相关问题"},
            {"summary": "用户是计算机学院学生"},
        ]
        messages = builder.build_rag_prompt(
            query="推荐学习资源",
            context_chunks=[],
            history=[],
            user_memories=memories,
        )
        system_content = messages[0]["content"]
        assert "用户相关记忆" in system_content
        assert "图书馆" in system_content

    def test_history_truncated_to_10_messages(self, builder):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
            for i in range(20)
        ]
        messages = builder.build_rag_prompt(
            query="问题",
            context_chunks=[],
            history=history,
        )
        # system + 10 history messages + 1 current query = 12
        assert len(messages) == 12

    def test_no_sources_no_references_block(self, builder):
        messages = builder.build_rag_prompt(
            query="问题",
            context_chunks=[],
            history=[],
        )
        system_content = messages[0]["content"]
        # The instructions text always mentions "参考资料" as guidance,
        # but the dedicated "\n参考资料：\n" section with actual sources
        # should be absent when no chunks are provided.
        assert "\n参考资料：\n" not in system_content


# ------------------------------------------------------------------ #
# build_chitchat_prompt
# ------------------------------------------------------------------ #

class TestBuildChitchatPrompt:

    def test_system_message(self, builder):
        messages = builder.build_chitchat_prompt(query="你好", history=[])
        assert messages[0]["role"] == "system"
        assert "闲聊" in messages[0]["content"]

    def test_includes_query(self, builder):
        messages = builder.build_chitchat_prompt(query="今天心情不错", history=[])
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "今天心情不错"

    def test_includes_history(self, builder):
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀！"},
        ]
        messages = builder.build_chitchat_prompt(query="再见", history=history)
        assert len(messages) == 4  # system + 2 history + 1 query

    def test_no_knowledge_references(self, builder):
        messages = builder.build_chitchat_prompt(query="聊聊天", history=[])
        system_content = messages[0]["content"]
        assert "参考资料" not in system_content


# ------------------------------------------------------------------ #
# format_sources
# ------------------------------------------------------------------ #

class TestFormatSources:

    def test_basic_format(self, builder):
        sources = [
            {"title": "图书馆指南", "snippet": "开放时间8:00-22:00", "url": "https://lib.bupt.edu.cn"},
        ]
        output = builder.format_sources(sources)
        assert "[1]" in output
        assert "图书馆指南" in output
        assert "8:00-22:00" in output
        assert "https://lib.bupt.edu.cn" in output

    def test_multiple_sources_numbered(self, builder):
        sources = [
            {"title": f"Source {i}", "snippet": f"Snippet {i}"}
            for i in range(3)
        ]
        output = builder.format_sources(sources)
        assert "[1]" in output
        assert "[2]" in output
        assert "[3]" in output

    def test_no_url(self, builder):
        sources = [{"title": "Title", "snippet": "Snippet"}]
        output = builder.format_sources(sources)
        assert "(" not in output  # no URL parentheses

    def test_empty_sources(self, builder):
        assert builder.format_sources([]) == ""

    def test_missing_title_uses_default(self, builder):
        sources = [{"snippet": "some snippet"}]
        output = builder.format_sources(sources)
        assert "未知来源" in output

    def test_output_is_multiline(self, builder):
        sources = [
            {"title": "A", "snippet": "a"},
            {"title": "B", "snippet": "b"},
        ]
        output = builder.format_sources(sources)
        lines = output.strip().split("\n")
        assert len(lines) == 2
