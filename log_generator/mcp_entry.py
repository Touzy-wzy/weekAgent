# -*- coding: utf-8 -*-
"""MCP Server 命令行入口

启动方式:
    # Streamable HTTP（远程访问）
    python -m log_generator.mcp_entry --transport streamable-http --port 8899

    # SSE（Web 客户端）
    python -m log_generator.mcp_entry --transport sse --port 8899

    # stdio（本地 IDE 集成）
    python -m log_generator.mcp_entry --transport stdio

MCP 客户端配置:
    客户端标识符: log_generator
    显示名称:     日志数据访问
    传输方式:     Streamable HTTP / SSE / stdio

    stdio 模式:
      启动命令: python
      命令参数: -m log_generator.mcp_entry --transport stdio
      环境变量: LOG_GEN_DIR=E:\\weekAgent\\generated_logs
               LOG_GEN_MCP_PORT=8899
"""

import argparse
import sys

# 兼容直接运行（python mcp_entry.py）和模块运行（python -m log_generator.mcp_entry）
try:
    from . import config
    from .mcp_server import mcp
except ImportError:
    import config
    from mcp_server import mcp


def main():
    parser = argparse.ArgumentParser(
        description="日志生成器 MCP Server - 纯 Resource 数据暴露",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m log_generator.mcp_entry --transport streamable-http --port 8899
  python -m log_generator.mcp_entry --transport sse --port 8899
  python -m log_generator.mcp_entry --transport stdio
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="streamable-http",
        help="传输协议 (默认: streamable-http)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"HTTP 端口 (默认: {config.MCP_PORT})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help=f"绑定的主机地址 (默认: {config.MCP_HOST})",
    )

    args = parser.parse_args()

    # 应用 host/port 覆盖
    if args.port is not None:
        mcp.settings.port = args.port
    else:
        mcp.settings.port = config.MCP_PORT

    if args.host is not None:
        mcp.settings.host = args.host
    else:
        mcp.settings.host = config.MCP_HOST

    print(f"[log_generator MCP] 启动中...")
    print(f"  传输方式: {args.transport}")
    if args.transport != "stdio":
        print(f"  监听地址: http://{mcp.settings.host}:{mcp.settings.port}")
    print(f"  日志目录: {config.LOG_OUTPUT_DIR}")

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()