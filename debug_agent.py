#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlowUs Agent 调试脚本

快速验证 Agent 工具链路是否正常：
1. 单独测试每个工具（不依赖 LLM）
2. 测试完整 Agent 流程（依赖 LLM）

使用方法:
    python debug_agent.py              # 工具单元测试
    python debug_agent.py --tools      # 仅测试工具
    python debug_agent.py --agent      # 测试完整 Agent 对话
    python debug_agent.py --agent --query "积成电子下有哪些页面?"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from week_agent.agent.tools.flowus_tools import (
    FlowUsGetPageTool,
    FlowUsListPagesTool,
    FlowUsSearchTool,
)


def test_tools():
    """测试三个工具是否能正常调用 FlowUs"""
    print("=" * 60)
    print("测试 1: FlowUsListPagesTool - 列出页面")
    print("=" * 60)
    tool = FlowUsListPagesTool()
    resp = tool.run({"project_name": "积成电子"})
    print(f"状态: {resp.status.value}")
    print(f"文本: {resp.text[:500]}")
    if resp.status.value == "error":
        print(f"❌ 失败: {resp.error_info}")
        return False

    pages = resp.data.get("pages", [])
    if not pages:
        print("⚠️ 未找到页面，可能需要先运行 `python run.py --cli` 授权")
        return False

    print(f"✅ 找到 {len(pages)} 个页面")
    first_page = pages[0]
    print(f"   首个页面: {first_page['title']} (id={first_page['id']})")

    # 测试搜索工具
    print(f"\n{'=' * 60}")
    print("测试 2: FlowUsSearchTool - 语义搜索")
    print("=" * 60)
    search_tool = FlowUsSearchTool()
    resp = search_tool.run({"query": "会议纪要"})
    print(f"状态: {resp.status.value}")
    print(f"文本: {resp.text[:500]}")
    if resp.status.value == "error":
        print(f"❌ 失败: {resp.error_info}")
    else:
        print(f"✅ 搜索完成，{len(resp.data.get('results', []))} 个结果")

    # 测试获取页面内容
    print(f"\n{'=' * 60}")
    print("测试 3: FlowUsGetPageTool - 获取页面内容")
    print("=" * 60)
    get_tool = FlowUsGetPageTool()
    resp = get_tool.run({"page_id": first_page["id"]})
    print(f"状态: {resp.status.value}")
    md_len = resp.data.get("length", 0)
    print(f"内容长度: {md_len} 字符")
    if md_len > 0:
        print(f"预览:\n{resp.data.get('markdown', '')[:300]}")
        print("✅ 获取成功")
        return True
    else:
        print("❌ 内容为空")
        return False


def test_agent(query: str, max_steps: int = 6):
    """测试完整 Agent 流程"""
    print("=" * 60)
    print(f"测试 Agent 对话: {query}")
    print("=" * 60)

    try:
        from week_agent.agent.runner import run_query

        answer = run_query(query, max_steps=max_steps)
        print(f"\n{'=' * 60}")
        print("Agent 最终回答:")
        print("=" * 60)
        print(answer)
        return True
    except Exception as e:
        print(f"❌ Agent 运行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="FlowUs Agent 调试")
    parser.add_argument(
        "--tools", action="store_true", help="仅测试工具（不依赖 LLM）"
    )
    parser.add_argument(
        "--agent", action="store_true", help="测试完整 Agent 对话（依赖 LLM）"
    )
    parser.add_argument("--query", default="积成电子项目下有哪些页面?")
    parser.add_argument("--max-steps", type=int, default=6)
    args = parser.parse_args()

    # 默认：先测工具
    if not args.agent or args.tools:
        ok = test_tools()
        if not ok:
            print("\n⚠️ 工具测试未通过，请先解决上述问题")
            if not args.agent:
                return 1

    # 测 Agent
    if args.agent:
        ok = test_agent(args.query, max_steps=args.max_steps)
        return 0 if ok else 1

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
