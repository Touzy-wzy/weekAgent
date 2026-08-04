# -*- coding: utf-8 -*-
"""RecallHistoryTool 独立测试

不依赖完整项目导入链，直接测试工具核心逻辑。
"""

import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# 直接导入工具模块（避免触发整个项目的导入链）
sys.path.insert(0, str(Path(__file__).parent))

# 模拟必要的 hello_agents 组件
class MockTool:
    def __init__(self, name, description):
        self.name = name
        self.description = description

class MockToolParameter:
    def __init__(self, name, type, description, required=False, default=None):
        self.name = name
        self.type = type
        self.description = description
        self.required = required
        self.default = default

class MockToolResponse:
    class Status:
        def __init__(self, value):
            self.value = value

    def __init__(self, status, text="", data=None, error_info=None):
        self.status = status
        self.text = text
        self.data = data or {}
        self.error_info = error_info

    @classmethod
    def success(cls, text="", data=None):
        return cls(cls.Status("success"), text, data)

    @classmethod
    def partial(cls, text="", data=None):
        return cls(cls.Status("partial"), text, data)

    @classmethod
    def error(cls, code=None, message="", context=None):
        error_info = MockErrorInfo(code, message, context)
        return cls(cls.Status("error"), error_info=error_info)

class MockErrorInfo:
    def __init__(self, code=None, message="", context=None):
        self.code = code
        self.message = message
        self.context = context

class MockToolErrorCode:
    INVALID_PARAM = "INVALID_PARAM"
    EXECUTION_ERROR = "EXECUTION_ERROR"

# 替换 hello_agents 模块
import types
hello_agents = types.ModuleType('hello_agents')
hello_agents.tools = types.ModuleType('hello_agents.tools')
hello_agents.tools.base = types.ModuleType('hello_agents.tools.base')
hello_agents.tools.errors = types.ModuleType('hello_agents.tools.errors')
hello_agents.tools.response = types.ModuleType('hello_agents.tools.response')

hello_agents.tools.base.Tool = MockTool
hello_agents.tools.base.ToolParameter = MockToolParameter
hello_agents.tools.errors.ToolErrorCode = MockToolErrorCode
hello_agents.tools.response.ToolResponse = MockToolResponse

sys.modules['hello_agents'] = hello_agents
sys.modules['hello_agents.tools'] = hello_agents.tools
sys.modules['hello_agents.tools.base'] = hello_agents.tools.base
sys.modules['hello_agents.tools.errors'] = hello_agents.tools.errors
sys.modules['hello_agents.tools.response'] = hello_agents.tools.response

# 现在导入工具
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


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("RecallHistoryTool 独立测试")
    print("=" * 60)

    # 初始化测试数据
    mock_store = MockHistoryStore()
    mock_store.add_turn(1, "user", "你好，我想查询天气")
    mock_store.add_turn(2, "assistant", "好的，我来帮你查询北京的天气")
    mock_store.add_turn(
        3, "assistant", "北京今天晴，温度 25°C",
        tool_call_id="call_weather_001",
        tool_name="weather_query",
        tool_input={"city": "北京"},
        tool_output="北京今天晴，温度 25°C",
    )
    mock_store.add_turn(4, "user", "谢谢，再帮我查一下上海的")
    mock_store.add_turn(5, "assistant", "上海今天多云，温度 22°C")
    mock_store.add_turn(6, "user", "今天天气不错")
    mock_store.add_turn(7, "assistant", "是的，适合出门")

    tool = RecallHistoryTool(history_store=mock_store)

    passed = 0
    failed = 0

    # 测试 1: 工具初始化
    print("\n测试 1: 工具初始化")
    try:
        tool2 = RecallHistoryTool()
        assert tool2.name == "recall_history"
        assert tool2._history_store is None

        tool2.set_history_store(mock_store)
        assert tool2._history_store is mock_store
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 2: 工具参数定义
    print("\n测试 2: 工具参数定义")
    try:
        params = tool.get_parameters()
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
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 3: expand 基本功能
    print("\n测试 3: expand 基本功能")
    try:
        resp = tool.run({"op": "expand", "lo": 2, "hi": 4})
        assert resp.status.value == "success"
        assert "turns" in resp.data
        assert len(resp.data["turns"]) == 3
        assert resp.data["lo"] == 2
        assert resp.data["hi"] == 4
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 4: expand 空范围
    print("\n测试 4: expand 空范围")
    try:
        resp = tool.run({"op": "expand", "lo": 100, "hi": 200})
        assert resp.status.value == "partial"
        assert len(resp.data["turns"]) == 0
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 5: expand 无效参数
    print("\n测试 5: expand 无效参数")
    try:
        # 缺少 lo
        resp = tool.run({"op": "expand", "hi": 10})
        assert resp.status.value == "error"

        # 缺少 hi
        resp = tool.run({"op": "expand", "lo": 1})
        assert resp.status.value == "error"

        # lo > hi
        resp = tool.run({"op": "expand", "lo": 10, "hi": 5})
        assert resp.status.value == "error"
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 6: search 基本功能
    print("\n测试 6: search 基本功能")
    try:
        resp = tool.run({"op": "search", "query": "天气"})
        assert resp.status.value == "success"
        assert "results" in resp.data
        assert len(resp.data["results"]) > 0
        # 所有结果都应包含 "天气"
        for result in resp.data["results"]:
            assert "天气" in result["content"]
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 7: search 限制结果数量
    print("\n测试 7: search 限制结果数量")
    try:
        resp = tool.run({"op": "search", "query": "天气", "k": 2})
        assert resp.status.value == "success"
        assert len(resp.data["results"]) <= 2
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 8: search 空查询
    print("\n测试 8: search 空查询")
    try:
        resp = tool.run({"op": "search", "query": ""})
        assert resp.status.value == "error"
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 9: search 无结果
    print("\n测试 9: search 无结果")
    try:
        resp = tool.run({"op": "search", "query": "不存在的关键词xyz"})
        assert resp.status.value == "partial"
        assert len(resp.data["results"]) == 0
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 10: recall_tool 基本功能
    print("\n测试 10: recall_tool 基本功能")
    try:
        resp = tool.run({"op": "recall_tool", "tool_call_id": "call_weather_001"})
        assert resp.status.value == "success"
        assert "result" in resp.data
        result = resp.data["result"]
        assert result["tool_name"] == "weather_query"
        assert result["tool_input"]["city"] == "北京"
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 11: recall_tool 未找到
    print("\n测试 11: recall_tool 未找到")
    try:
        resp = tool.run({"op": "recall_tool", "tool_call_id": "nonexistent"})
        assert resp.status.value == "partial"
        assert resp.data["result"] is None
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 12: recall_tool 空 ID
    print("\n测试 12: recall_tool 空 ID")
    try:
        resp = tool.run({"op": "recall_tool", "tool_call_id": ""})
        assert resp.status.value == "error"
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 13: 无效操作类型
    print("\n测试 13: 无效操作类型")
    try:
        resp = tool.run({"op": "invalid_op"})
        assert resp.status.value == "error"
        assert "不支持的操作类型" in resp.error_info.message
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 14: 缺少 op 参数
    print("\n测试 14: 缺少 op 参数")
    try:
        resp = tool.run({})
        assert resp.status.value == "error"
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 15: 未初始化历史存储
    print("\n测试 15: 未初始化历史存储")
    try:
        tool3 = RecallHistoryTool()
        resp = tool3.run({"op": "expand", "lo": 1, "hi": 10})
        assert resp.status.value == "error"
        assert "历史存储未初始化" in resp.error_info.message
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 16: session_id 参数
    print("\n测试 16: session_id 参数")
    try:
        resp = tool.run({
            "op": "expand",
            "lo": 1,
            "hi": 3,
            "session_id": "test-session",
        })
        # 应该正常工作（session_id 在 mock 中被忽略）
        assert resp.status.value == "success"
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 测试 17: 多关键词搜索
    print("\n测试 17: 多关键词搜索")
    try:
        store2 = MockHistoryStore()
        store2.add_turn(1, "user", "北京天气查询")
        store2.add_turn(2, "user", "上海天气查询")
        store2.add_turn(3, "user", "北京温度查询")
        tool4 = RecallHistoryTool(history_store=store2)

        # 搜索 "北京 天气" - 两个词都必须匹配
        resp = tool4.run({"op": "search", "query": "北京 天气"})
        assert resp.status.value == "success"
        assert len(resp.data["results"]) == 1
        assert "北京" in resp.data["results"][0]["content"]
        assert "天气" in resp.data["results"][0]["content"]
        print("  ✅ 通过")
        passed += 1
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        failed += 1

    # 汇总
    print("\n" + "=" * 60)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
