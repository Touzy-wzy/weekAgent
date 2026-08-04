# -*- coding: utf-8 -*-
"""RecallHistoryTool 单元测试

测试历史对话检索工具的三种操作：
1. expand: 按 seq 范围展开完整轮次
2. search: 按关键词搜索历史
3. recall_tool: 按 tool_call_id 重读工具调用

使用 MockHistoryStore 模拟历史存储，不依赖真实数据库。
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from week_agent.agent.tools.history_tools import RecallHistoryTool


class MockHistoryStore:
    """模拟历史存储，用于测试"""

    def __init__(self):
        self._turns = []
        self._tool_calls = {}

    def add_turn(self, seq: int, role: str, content: str, **kwargs):
        """添加测试数据"""
        turn = {"seq": seq, "role": role, "content": content, **kwargs}
        self._turns.append(turn)
        # 如果有 tool_call_id，也存储工具调用
        if "tool_call_id" in kwargs:
            self._tool_calls[kwargs["tool_call_id"]] = {
                "seq": seq,
                "tool_name": kwargs.get("tool_name", "unknown"),
                "tool_input": kwargs.get("tool_input", {}),
                "tool_output": kwargs.get("tool_output", ""),
            }

    def expand(self, session_id: Optional[str], lo: int, hi: int) -> List[Dict[str, Any]]:
        """展开 seq 范围"""
        return [t for t in self._turns if lo <= t["seq"] <= hi]

    def search(self, session_id: Optional[str], query: str, k: int) -> List[Dict[str, Any]]:
        """关键词搜索"""
        results = []
        query_terms = query.lower().split()
        for turn in self._turns:
            content_lower = turn["content"].lower()
            # 所有关键词都必须匹配
            if all(term in content_lower for term in query_terms):
                # 简单评分：匹配关键词数量
                score = sum(1 for term in query_terms if term in content_lower) / len(query_terms)
                results.append({**turn, "score": score})
        # 按分数排序，取前 k 个
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:k]

    def recall_tool(self, session_id: Optional[str], tool_call_id: str) -> Optional[Dict[str, Any]]:
        """按 tool_call_id 重读工具调用"""
        return self._tool_calls.get(tool_call_id)


class TestRecallHistoryTool:
    """RecallHistoryTool 测试类"""

    def setup_method(self):
        """每个测试前初始化"""
        self.mock_store = MockHistoryStore()
        # 添加测试数据
        self.mock_store.add_turn(1, "user", "你好，我想查询天气")
        self.mock_store.add_turn(2, "assistant", "好的，我来帮你查询北京的天气")
        self.mock_store.add_turn(
            3, "assistant", "北京今天晴，温度 25°C",
            tool_call_id="call_weather_001",
            tool_name="weather_query",
            tool_input={"city": "北京"},
            tool_output="北京今天晴，温度 25°C",
        )
        self.mock_store.add_turn(4, "user", "谢谢，再帮我查一下上海的")
        self.mock_store.add_turn(5, "assistant", "上海今天多云，温度 22°C")
        self.mock_store.add_turn(6, "user", "今天天气不错")
        self.mock_store.add_turn(7, "assistant", "是的，适合出门")

        self.tool = RecallHistoryTool(history_store=self.mock_store)

    def test_tool_initialization(self):
        """测试工具初始化"""
        tool = RecallHistoryTool()
        assert tool.name == "recall_history"
        assert tool._history_store is None

        tool.set_history_store(self.mock_store)
        assert tool._history_store is self.mock_store

    def test_tool_parameters(self):
        """测试工具参数定义"""
        params = self.tool.get_parameters()
        param_names = [p.name for p in params]

        assert "op" in param_names
        assert "lo" in param_names
        assert "hi" in param_names
        assert "query" in param_names
        assert "k" in param_names
        assert "tool_call_id" in param_names
        assert "session_id" in param_names

        # op 参数必须
        op_param = next(p for p in params if p.name == "op")
        assert op_param.required

    def test_expand_basic(self):
        """测试 expand 基本功能"""
        resp = self.tool.run({"op": "expand", "lo": 2, "hi": 4})

        assert resp.status.value == "success"
        assert "turns" in resp.data
        assert len(resp.data["turns"]) == 3
        assert resp.data["lo"] == 2
        assert resp.data["hi"] == 4

    def test_expand_empty_range(self):
        """测试 expand 空范围"""
        resp = self.tool.run({"op": "expand", "lo": 100, "hi": 200})

        assert resp.status.value == "partial"
        assert len(resp.data["turns"]) == 0

    def test_expand_invalid_params(self):
        """测试 expand 无效参数"""
        # 缺少 lo
        resp = self.tool.run({"op": "expand", "hi": 10})
        assert resp.status.value == "error"

        # 缺少 hi
        resp = self.tool.run({"op": "expand", "lo": 1})
        assert resp.status.value == "error"

        # lo > hi
        resp = self.tool.run({"op": "expand", "lo": 10, "hi": 5})
        assert resp.status.value == "error"

    def test_search_basic(self):
        """测试 search 基本功能"""
        resp = self.tool.run({"op": "search", "query": "天气"})

        assert resp.status.value == "success"
        assert "results" in resp.data
        assert len(resp.data["results"]) > 0
        # 所有结果都应包含 "天气"
        for result in resp.data["results"]:
            assert "天气" in result["content"]

    def test_search_with_k(self):
        """测试 search 限制结果数量"""
        resp = self.tool.run({"op": "search", "query": "天气", "k": 2})

        assert resp.status.value == "success"
        assert len(resp.data["results"]) <= 2

    def test_search_empty_query(self):
        """测试 search 空查询"""
        resp = self.tool.run({"op": "search", "query": ""})
        assert resp.status.value == "error"

    def test_search_no_results(self):
        """测试 search 无结果"""
        resp = self.tool.run({"op": "search", "query": "不存在的关键词xyz"})

        assert resp.status.value == "partial"
        assert len(resp.data["results"]) == 0

    def test_recall_tool_basic(self):
        """测试 recall_tool 基本功能"""
        resp = self.tool.run({"op": "recall_tool", "tool_call_id": "call_weather_001"})

        assert resp.status.value == "success"
        assert "result" in resp.data
        result = resp.data["result"]
        assert result["tool_name"] == "weather_query"
        assert result["tool_input"]["city"] == "北京"

    def test_recall_tool_not_found(self):
        """测试 recall_tool 未找到"""
        resp = self.tool.run({"op": "recall_tool", "tool_call_id": "nonexistent"})

        assert resp.status.value == "partial"
        assert resp.data["result"] is None

    def test_recall_tool_empty_id(self):
        """测试 recall_tool 空 ID"""
        resp = self.tool.run({"op": "recall_tool", "tool_call_id": ""})
        assert resp.status.value == "error"

    def test_invalid_op(self):
        """测试无效操作类型"""
        resp = self.tool.run({"op": "invalid_op"})
        assert resp.status.value == "error"
        assert "不支持的操作类型" in resp.error_info.message

    def test_missing_op(self):
        """测试缺少 op 参数"""
        resp = self.tool.run({})
        assert resp.status.value == "error"

    def test_no_history_store(self):
        """测试未初始化历史存储"""
        tool = RecallHistoryTool()
        resp = tool.run({"op": "expand", "lo": 1, "hi": 10})
        assert resp.status.value == "error"
        assert "历史存储未初始化" in resp.error_info.message

    def test_session_id_parameter(self):
        """测试 session_id 参数"""
        resp = self.tool.run({
            "op": "expand",
            "lo": 1,
            "hi": 3,
            "session_id": "test-session",
        })
        # 应该正常工作（session_id 在 mock 中被忽略）
        assert resp.status.value == "success"


class TestRecallHistoryToolEdgeCases:
    """RecallHistoryTool 边界情况测试"""

    def test_expand_single_seq(self):
        """测试展开单个 seq"""
        store = MockHistoryStore()
        store.add_turn(5, "user", "测试消息")
        tool = RecallHistoryTool(history_store=store)

        resp = tool.run({"op": "expand", "lo": 5, "hi": 5})
        assert resp.status.value == "success"
        assert len(resp.data["turns"]) == 1

    def test_search_multiple_terms(self):
        """测试多关键词搜索"""
        store = MockHistoryStore()
        store.add_turn(1, "user", "北京天气查询")
        store.add_turn(2, "user", "上海天气查询")
        store.add_turn(3, "user", "北京温度查询")
        tool = RecallHistoryTool(history_store=store)

        # 搜索 "北京 天气" - 两个词都必须匹配
        resp = tool.run({"op": "search", "query": "北京 天气"})
        assert resp.status.value == "success"
        assert len(resp.data["results"]) == 1
        assert "北京" in resp.data["results"][0]["content"]
        assert "天气" in resp.data["results"][0]["content"]

    def test_recall_tool_complex_output(self):
        """测试复杂工具输出"""
        store = MockHistoryStore()
        store.add_turn(
            1, "assistant", "执行完成",
            tool_call_id="call_complex",
            tool_name="complex_tool",
            tool_input={"data": {"nested": "value"}},
            tool_output={"result": "success", "items": [1, 2, 3]},
        )
        tool = RecallHistoryTool(history_store=store)

        resp = tool.run({"op": "recall_tool", "tool_call_id": "call_complex"})
        assert resp.status.value == "success"
        result = resp.data["result"]
        assert result["tool_input"]["data"]["nested"] == "value"
        assert result["tool_output"]["items"] == [1, 2, 3]


if __name__ == "__main__":
    # 直接运行测试
    print("运行 RecallHistoryTool 测试...")
    pytest.main([__file__, "-v"])
