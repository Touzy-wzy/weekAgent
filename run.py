#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weekAgent 统一入口

使用方法:
    # CLI 模式：OAuth 授权 + 拉取内容到 data/
    python run.py
    python run.py --path "/积成电子/2026.7.2"
    python run.py --list-tools

    # Web UI 模式：浏览器界面（含 Agent 对话端点）
    python run.py --web
    python run.py --web --port 8080

    # Agent 模式：单次查询
    python run.py --agent "列出积成电子项目下的所有页面"

    # Agent 调试模式：交互式 REPL
    python run.py --agent-debug
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from week_agent.cli import run_agent_debug, run_agent_query, run_cli, run_web, run_log_agent, run_log_agent_debug
from week_agent.config import DATA_DIR


def main():
    parser = argparse.ArgumentParser(
        description="weekAgent - FlowUs 智能体",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py                                    # CLI 拉取内容
  python run.py --path "/积成电子/2026.7.2"         # 指定路径
  python run.py --list-tools                       # 列出 MCP 工具
  python run.py --web                              # 启动 Web UI (端口 8000)
  python run.py --web --port 8080                  # 自定义端口
  python run.py --agent "积成电子下有哪些页面?"      # Agent 单次查询
  python run.py --agent-debug                      # Agent 交互式调试
  python run.py --log-agent "今天日志怎么样?"        # 日志监控 Agent 单次查询
  python run.py --log-agent-debug                  # 日志监控 Agent 交互式调试
        """,
    )

    parser.add_argument(
        "--path",
        default="/积成电子/2026.7.2",
        help="FlowUs 工作空间路径 (默认: /积成电子/2026.7.2)",
    )
    parser.add_argument(
        "--output",
        default=str(DATA_DIR),
        help=f"输出目录 (默认: {DATA_DIR})",
    )
    parser.add_argument(
        "--url",
        default="https://mcp.flowus.cn/message",
        help="FlowUs MCP 服务器地址",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="仅列出可用 MCP 工具",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Web UI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Web 服务端口 (默认: 8000)",
    )
    parser.add_argument(
        "--agent",
        metavar="QUERY",
        help="Agent 单次查询模式，传入问题",
    )
    parser.add_argument(
        "--agent-debug",
        action="store_true",
        help="Agent 交互式调试模式",
    )
    parser.add_argument(
        "--log-agent",
        metavar="QUERY",
        help="日志监控 Agent 单次查询模式，传入问题",
    )
    parser.add_argument(
        "--log-agent-debug",
        action="store_true",
        help="日志监控 Agent 交互式调试模式",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=6,
        help="Agent 最大推理步数 (默认: 6)",
    )

    args = parser.parse_args()

    # 日志监控 Agent 调试模式
    if args.log_agent_debug:
        return run_log_agent_debug()

    # 日志监控 Agent 单次查询模式
    if args.log_agent:
        try:
            answer = run_log_agent(args.log_agent, max_steps=args.max_steps)
            print(f"\n{'=' * 60}\n日志监控 Agent 回答:\n{'=' * 60}\n{answer}")
            return 0
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            return 1

    # Agent 调试模式
    if args.agent_debug:
        return run_agent_debug()

    # Agent 单次查询模式
    if args.agent:
        try:
            answer = run_agent_query(args.agent, max_steps=args.max_steps)
            print(f"\n{'=' * 60}\nAgent 回答:\n{'=' * 60}\n{answer}")
            return 0
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            return 1

    # Web UI 模式
    if args.web:
        return run_web(args)

    # 默认：CLI 模式
    return asyncio.run(run_cli(args))


if __name__ == "__main__":
    sys.exit(main())
