"""FlowUs MCP 客户端 - 使用 MCP 协议 + OAuth 2.0 PKCE 认证

用于首次授权（浏览器 OAuth 流程），授权后 token 持久化到文件，
后续 Web/Agent 调用使用 FlowUsHTTPClient 即可。
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from week_agent.config import DATA_DIR, FLOWUS_MCP_URL
from week_agent.flowus.auth import build_oauth_provider
from week_agent.flowus.utils import extract_content, extract_page_ids


class FlowUsMCPClient:
    """FlowUs MCP 客户端 - 使用 MCP 协议 + OAuth 认证"""

    def __init__(self, server_url: str = FLOWUS_MCP_URL):
        self.server_url = server_url
        self._oauth_lock = asyncio.Lock()

    async def with_session(self, callback):
        """打开一个持久 MCP 会话，执行回调。

        回调签名: async def callback(session: ClientSession) -> Any
        """
        async with self._oauth_lock:
            auth = build_oauth_provider(self.server_url)
            async with streamablehttp_client(self.server_url, auth=auth) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await callback(session)

    async def list_tools(self) -> list[dict]:
        """列出 MCP 服务器提供的所有工具"""
        async with self._oauth_lock:
            auth = build_oauth_provider(self.server_url)
            async with streamablehttp_client(self.server_url, auth=auth) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [tool.model_dump() for tool in result.tools]

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> Any:
        """调用指定的 MCP 工具"""
        async with self._oauth_lock:
            auth = build_oauth_provider(self.server_url)
            async with streamablehttp_client(self.server_url, auth=auth) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(tool_name, arguments or {})

    async def fetch_and_save(
        self,
        workspace_path: str = "/积成电子/2026.7.2",
        output_dir: str | Path = DATA_DIR,
    ) -> str:
        """获取工作空间内容并保存为文件"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        all_content: dict[str, Any] = {}
        tool_list: list[dict] = []

        path_parts = [p for p in workspace_path.strip("/").split("/") if p]
        search_query = " ".join(path_parts) if path_parts else workspace_path.strip("/")

        async def _fetch(session: ClientSession):
            nonlocal tool_list
            # 1. 列出所有可用工具
            tools_result = await session.list_tools()
            tool_list = [t.model_dump() for t in tools_result.tools]
            print(f"\n发现 {len(tool_list)} 个可用工具")

            # 2. 获取用户信息
            print("\n--- 获取用户信息 ---")
            try:
                result = await session.call_tool("API-getMe", {})
                all_content["user_info"] = extract_content(result)
                print("  ✓ 用户信息获取成功")
            except Exception as e:
                print(f"  ✗ 获取用户信息失败: {e}")

            # 3. 搜索 + 语义搜索
            print(f"\n--- 搜索: {search_query} ---")
            search_results = None
            try:
                result = await session.call_tool(
                    "API-search", {"query": search_query, "page_size": 20}
                )
                search_results = extract_content(result)
                all_content["search_results"] = search_results
                print("  ✓ 常规搜索完成")
            except Exception as e:
                print(f"  ✗ 常规搜索失败: {e}")

            try:
                result = await session.call_tool(
                    "API-semanticSearch", {"query": search_query}
                )
                all_content["semantic_search"] = extract_content(result)
                print("  ✓ 语义搜索完成")
            except Exception as e:
                print(f"  ✗ 语义搜索失败: {e}")

            # 4. 获取页面 Markdown 内容
            print("\n--- 获取页面内容 ---")
            page_ids = extract_page_ids(search_results) or extract_page_ids(
                all_content.get("semantic_search")
            )
            if page_ids:
                for pid in page_ids[:10]:
                    try:
                        result = await session.call_tool(
                            "API-getMarkdown", {"page_id": pid}
                        )
                        content = extract_content(result)
                        all_content[f"page_{pid}"] = content
                        print(f"  ✓ 页面 {pid}")
                    except Exception as e:
                        print(f"  ✗ 页面 {pid}: {e}")
            else:
                print("  未找到页面 ID，跳过内容获取")

        await self.with_session(_fetch)

        # 5. 写入文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"flowus_content_{timestamp}.txt"
        filepath = output_path / filename

        import json

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("FlowUs 工作空间内容\n")
            f.write(f"{'=' * 50}\n\n")
            f.write(f"路径: {workspace_path}\n")
            f.write(f"搜索关键词: {search_query}\n")
            f.write(f"服务器: {self.server_url}\n")
            f.write(f"获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"可用工具 ({len(tool_list)} 个):\n")
            f.write(f"{'=' * 50}\n")
            for t in tool_list:
                f.write(
                    f"  - {t['name']}: {t.get('description', '(无描述)')[:60]}\n"
                )
            f.write("\n获取内容:\n")
            f.write(f"{'=' * 50}\n")
            f.write(json.dumps(all_content, ensure_ascii=False, indent=2))

        print(f"\n✓ 内容已保存到: {filepath}")
        return str(filepath)
