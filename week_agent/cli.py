"""CLI 入口 - 命令行模式"""

import asyncio
import sys

from week_agent.config import DATA_DIR, DEFAULT_PROJECT, FLOWUS_MCP_URL
from week_agent.flowus.mcp_client import FlowUsMCPClient


async def run_cli(args):
    """命令行模式：OAuth 授权 + 拉取内容"""
    client = FlowUsMCPClient(server_url=args.url)

    print("=" * 60)
    print("FlowUs MCP 内容读取工具")
    print("=" * 60)
    print(f"工作空间路径: {args.path}")
    print(f"输出目录: {args.output}")
    print(f"MCP 服务器: {args.url}")
    print("认证方式: OAuth 2.0 (首次使用将打开浏览器授权)\n")

    try:
        if args.list_tools:
            tools = await client.list_tools()
            print(f"\n可用工具 ({len(tools)} 个):")
            for t in tools:
                print(f"  - {t['name']}: {t.get('description', '(无描述)')[:80]}")
            return 0

        filepath = await client.fetch_and_save(args.path, args.output)
        print(f"\n成功! 内容已保存到: {filepath}")
        return 0

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


def run_web(args):
    """Web UI 模式"""
    import uvicorn

    from week_agent.web.app import app

    print("=" * 60)
    print("FlowUs 内容浏览器 + Agent - Web UI")
    print("=" * 60)
    print(f"服务地址: http://localhost:{args.port}")
    print(f"MCP 服务器: {FLOWUS_MCP_URL}")
    print(f"默认项目: {DEFAULT_PROJECT}")
    print(f"输出目录: {DATA_DIR}")
    print("\nAPI 端点:")
    print("  GET  /api/pages         列出项目页面")
    print("  GET  /api/page/{id}     获取页面内容")
    print("  GET  /api/search?q=...  语义搜索")
    print("  POST /api/agent/chat?q=...  Agent 对话")
    print("\n按 Ctrl+C 停止服务\n")

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


def run_agent_query(query: str, max_steps: int = 6) -> str:
    """Agent 模式：单次查询"""
    from week_agent.agent.runner import run_query

    return run_query(query, max_steps=max_steps)


def run_agent_debug():
    """Agent 调试模式：交互式 REPL（会话级单例 Agent，保持多轮对话记忆）

    整个会话复用同一个 FlowUsAgent 实例，history_manager 累积历史，
    FlowUsAgent._build_messages 会把历史注入到 LLM 调用中。
    TraceLogger 文件句柄问题由 FlowUsAgent.run() 内部自动重置处理。
    """
    from week_agent.agent.runner import create_flowus_agent

    print("=" * 60)
    print("FlowUs Agent - 交互式调试（多轮记忆）")
    print("=" * 60)
    print("输入查询进行对话，输入 'quit' / 'exit' 退出")
    print("输入 'clear' 清空对话历史\n")

    # 会话级单例 Agent：整个交互过程复用同一实例
    try:
        agent = create_flowus_agent()
    except RuntimeError as e:
        print(f"初始化失败: {e}")
        return 1

    while True:
        try:
            query = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("再见!")
            break
        if query.lower() == "clear":
            agent.clear_history()
            print("✅ 对话历史已清空\n")
            continue

        print()
        try:
            # 同一 Agent 实例多次 run()，历史自动累积
            # FlowUsAgent 内部会重置 trace_logger 避免文件句柄问题
            answer = agent.run(query)
            print(f"\n--- Agent 回答 ---\n{answer}\n")
        except Exception as e:
            print(f"\n❌ 错误: {e}\n")
            # 偶发 LLM API 错误，agent 实例仍可复用
            # （FlowUsAgent 会在下次 run() 时重置 trace_logger）

    return 0


# =====================================================================
# 日志监控智能体入口
# =====================================================================
def run_log_agent(query: str, max_steps: int = 8) -> str:
    """日志监控 Agent：单次查询"""
    from week_agent.agent.runner import run_log_query

    return run_log_query(query, max_steps=max_steps)


def run_log_agent_debug():
    """日志监控 Agent 调试模式：交互式 REPL（会话级单例，多轮记忆）"""
    from week_agent.agent.runner import create_log_monitor_agent

    try:
        agent = create_log_monitor_agent()
    except RuntimeError as e:
        print(f"初始化失败: {e}")
        return 1

    print("=" * 60)
    print("日志监控 Agent - 交互式调试（多轮记忆）")
    print("=" * 60)
    print("输入查询进行对话，输入 'quit' / 'exit' 退出")
    print("输入 'clear' 清空对话历史\n")

    while True:
        try:
            query = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("再见!")
            break
        if query.lower() == "clear":
            agent.clear_history()
            print("✅ 对话历史已清空\n")
            continue

        print()
        try:
            answer = agent.run(query)
            print(f"\n--- 日志监控 Agent 回答 ---\n{answer}\n")
        except Exception as e:
            print(f"\n❌ 错误: {e}\n")

    return 0
