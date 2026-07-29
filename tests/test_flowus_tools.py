"""FlowUs Agent 工具单元测试

不依赖 LLM，仅验证三个工具能否正确调用 FlowUs MCP。
需要先完成 OAuth 授权（运行 `python run.py --list-tools` 生成 token）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from week_agent.agent.tools.flowus_tools import (
    FlowUsGetPageTool,
    FlowUsListPagesTool,
    FlowUsSearchTool,
)


def test_list_pages_tool():
    """测试列出页面工具"""
    tool = FlowUsListPagesTool()
    resp = tool.run({"project_name": "积成电子"})

    assert resp.status.value in ("success", "partial"), f"工具失败: {resp.error_info}"
    assert "pages" in resp.data
    if resp.data["pages"]:
        page = resp.data["pages"][0]
        assert "id" in page
        assert "title" in page


def test_list_pages_empty_name():
    """测试空项目名应返回错误"""
    tool = FlowUsListPagesTool()
    resp = tool.run({"project_name": ""})
    assert resp.status.value == "error"


def test_get_page_tool_invalid_id():
    """测试无效 page_id"""
    tool = FlowUsGetPageTool()
    resp = tool.run({"page_id": "invalid-id"})
    # 无效 ID 应返回 error 或 partial（取决于 FlowUs 行为）
    assert resp.status.value in ("error", "partial")


def test_get_page_tool_empty_id():
    """测试空 page_id"""
    tool = FlowUsGetPageTool()
    resp = tool.run({"page_id": ""})
    assert resp.status.value == "error"


def test_search_tool():
    """测试搜索工具"""
    tool = FlowUsSearchTool()
    resp = tool.run({"query": "会议纪要"})

    assert resp.status.value in ("success", "partial"), f"搜索失败: {resp.error_info}"
    assert "results" in resp.data


def test_search_tool_empty_query():
    """测试空查询"""
    tool = FlowUsSearchTool()
    resp = tool.run({"query": ""})
    assert resp.status.value == "error"


def test_tool_parameters_schema():
    """测试工具参数 schema 正确"""
    list_tool = FlowUsListPagesTool()
    params = list_tool.get_parameters()
    assert len(params) == 1
    assert params[0].name == "project_name"
    assert params[0].required

    get_tool = FlowUsGetPageTool()
    params = get_tool.get_parameters()
    assert len(params) == 1
    assert params[0].name == "page_id"

    search_tool = FlowUsSearchTool()
    params = search_tool.get_parameters()
    assert len(params) == 1
    assert params[0].name == "query"


def test_tool_openai_schema():
    """测试 OpenAI function calling schema 生成"""
    tool = FlowUsListPagesTool()
    schema = tool.to_openai_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "flowus_list_pages"
    assert "properties" in schema["function"]["parameters"]
    assert "project_name" in schema["function"]["parameters"]["properties"]
    assert "project_name" in schema["function"]["parameters"]["required"]


if __name__ == "__main__":
    # 直接运行：跳过 pytest，手动执行
    print("运行工具测试...")
    test_list_pages_tool()
    print("✅ test_list_pages_tool")
    test_search_tool()
    print("✅ test_search_tool")
    test_tool_parameters_schema()
    print("✅ test_tool_parameters_schema")
    test_tool_openai_schema()
    print("✅ test_tool_openai_schema")
    print("\n所有测试通过!")
