"""FlowUs Agent 工具 - 封装 FlowUs HTTP 客户端为 hello-agents 工具

三个工具：
- FlowUsListPagesTool：列出项目下的所有子页面
- FlowUsGetPageTool：获取页面 Markdown 内容
- FlowUsSearchTool：语义搜索工作空间

工具的 run() 是同步方法（hello-agents ReActAgent 同步调用），
内部通过 _run_async() 在独立线程中运行事件循环，避免与 Web UI 的事件循环冲突。
"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

from week_agent.flowus.http_client import FlowUsHTTPClient, get_http_client
from week_agent.flowus.utils import (
    extract_block_title,
    extract_tool_result,
    parse_page_links,
)
from week_agent.config import FLOWUS_PROJECT_ROOT_IDS


# 单线程执行器，用于在独立线程中运行 async 函数
_executor = ThreadPoolExecutor(max_workers=4)


def _run_async(coro) -> Any:
    """在独立线程中运行 async 协程，避免与已有事件循环冲突

    hello-agents 的 ReActAgent.run() 是同步方法，会调用 tool.run()。
    如果当前线程已有事件循环（例如在 FastAPI 的 async 路由里通过 run.py --agent 调用），
    直接 asyncio.run() 会报错。这里用线程池隔离事件循环。
    """
    import asyncio as _asyncio

    def _runner():
        loop = _asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    fut = _executor.submit(_runner)
    return fut.result()


# ---------------------------------------------------------------------------
# 工具 1：列出项目下的所有页面
# ---------------------------------------------------------------------------

class FlowUsListPagesTool(Tool):
    """列出 FlowUs 指定项目下的所有子页面（树形结构）

    积成电子项目结构：项目文件夹 → 月份文件夹 → 日期文件
    默认递归 2 层，返回嵌套树。
    """

    def __init__(self):
        super().__init__(
            name="flowus_list_pages",
            description=(
                "列出 FlowUs 指定项目下的页面树。"
                "积成电子等项目的结构为：项目 → 月份文件夹 → 日期文件，"
                "默认递归 2 层返回嵌套树（月份含 children 日期列表）。"
                "返回每个节点的 title、page_id、type、level。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="project_name",
                type="string",
                description="项目名称，例如 '积成电子'",
                required=True,
            ),
            ToolParameter(
                name="max_depth",
                type="integer",
                description="递归深度（默认 2：项目→月→日；1：仅月份）",
                required=False,
                default=2,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        project_name = parameters.get("project_name", "").strip()
        max_depth = parameters.get("max_depth", 2)
        if not project_name:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="project_name 不能为空",
            )

        print(f"📋 [flowus_list_pages] 项目: {project_name} (depth={max_depth})")
        try:
            tree = _run_async(self._fetch_tree(project_name, max_depth))
            if not tree:
                return ToolResponse.partial(
                    text=f"项目 '{project_name}' 下未找到任何页面",
                    data={"pages": [], "project_name": project_name},
                )

            # 扁平化用于文本展示
            flat = self._flatten(tree)
            text_lines = [f"项目 '{project_name}' 下共 {len(flat)} 个页面（树形）："]
            for node in flat:
                indent = "  " * node["level"]
                text_lines.append(f"{indent}- {node['title']}  (id={node['id']}, {node['type']})")
            text = "\n".join(text_lines)

            print(f"  ✅ 找到 {len(flat)} 个页面")
            return ToolResponse.success(
                text=text,
                data={"pages": tree, "project_name": project_name},
            )
        except Exception as e:
            print(f"  ❌ 列出页面失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"列出页面失败: {str(e)}",
                context={"project_name": project_name},
            )

    @staticmethod
    def _flatten(tree: list[dict]) -> list[dict]:
        """扁平化树用于文本展示"""
        out: list[dict] = []
        for node in tree:
            out.append(node)
            if node.get("children"):
                out.extend(FlowUsListPagesTool._flatten(node["children"]))
        return out

    async def _fetch_tree(self, project_name: str, max_depth: int) -> list[dict]:
        """获取项目页面树

        流程：
        1. 语义搜索找到项目主页
        2. 获取项目主页的子页面（月份文件夹，level=1）
        3. 对每个月份递归获取子页面（日期文件，level=2）
        """
        client = get_http_client()

        async def fetch(http, session_id):
            req_id = 2

            # 1. 语义搜索找到项目主页
            result = await client.call_tool(
                http, session_id, "API-semanticSearch",
                {"query": project_name}, req_id,
            )
            req_id += 1
            search_data = extract_tool_result(result)

            parent_id = None
            if isinstance(search_data, dict):
                for r in search_data.get("results", []):
                    if r.get("page_title") == project_name:
                        parent_id = r.get("page_id")
                        break
                if not parent_id and search_data.get("results"):
                    parent_id = search_data["results"][0].get("page_id")

            # 语义搜索找不到时，回退到配置的项目根 ID 映射
            if not parent_id:
                parent_id = FLOWUS_PROJECT_ROOT_IDS.get(project_name)
                if parent_id:
                    print(f"  ℹ️ 语义搜索未命中，使用配置的 {project_name} 根 ID: {parent_id}")

            if not parent_id:
                return []

            # 2. 获取项目主页的子页面（月份，level=1）
            seen: set[str] = {parent_id}
            months = await self._fetch_children(client, http, session_id, parent_id, req_id)
            req_id += 2  # getMarkdown + getBlockChildren 各 +1
            for m in months:
                m["level"] = 1
                seen.add(m["id"])

            # 3. 递归获取月份的子页面（日期，level=2）
            if max_depth >= 2:
                for m in months:
                    try:
                        days = await self._fetch_children(
                            client, http, session_id, m["id"], req_id
                        )
                        req_id += 2
                        # 去重 + 设置 level
                        days = [d for d in days if d["id"] not in seen]
                        for d in days:
                            d["level"] = 2
                            seen.add(d["id"])
                        m["children"] = days
                    except Exception as e:
                        print(f"  ⚠️ 获取 {m['title']} 子页面失败: {e}")
                        m["children"] = []

            return months

        return await client.with_session(fetch)

    async def _fetch_children(
        self, client, http, session_id: str, parent_id: str, req_id_start: int
    ) -> list[dict]:
        """获取某个页面的直接子页面

        组合 getMarkdown（解析链接）+ getBlockChildren（补充 child_page block）。
        返回 [{"id", "title", "type", "level"}, ...]，level 不在此设置（由调用方补）。
        """
        req_id = req_id_start
        pages: list[dict] = []
        seen: set[str] = set()

        # A. getMarkdown 解析链接
        try:
            result = await client.call_tool(
                http, session_id, "API-getMarkdown",
                {"page_id": parent_id}, req_id,
            )
            req_id += 1
            md_data = extract_tool_result(result)
            md_text = ""
            if isinstance(md_data, dict):
                md_text = md_data.get("markdown", "")
            elif isinstance(md_data, str):
                md_text = md_data

            for p in parse_page_links(md_text):
                if p["id"] not in seen:
                    seen.add(p["id"])
                    pages.append({
                        "id": p["id"],
                        "title": p["title"],
                        "type": "page",
                        "level": 0,  # 调用方覆盖
                        "children": [],
                    })
        except Exception:
            pass

        # B. getBlockChildren 补充
        try:
            result = await client.call_tool(
                http, session_id, "API-getBlockChildren",
                {"block_id": parent_id, "page_size": 100}, req_id,
            )
            req_id += 1
            children = extract_tool_result(result)
            if isinstance(children, dict):
                for block in children.get("results", []):
                    block_type = block.get("type", "")
                    block_id = block.get("id", "")
                    title = extract_block_title(block)
                    if block_type == "child_page" and block_id not in seen:
                        seen.add(block_id)
                        pages.append({
                            "id": block_id,
                            "title": title or "(无标题)",
                            "type": "page",
                            "level": 0,
                            "children": [],
                        })
        except Exception:
            pass

        # 推断类型：标题匹配 YYYY.M 或 YYYY.MM 视为月份文件夹
        import re
        month_re = re.compile(r"^\d{4}[.\-年]\d{1,2}月?$")
        for p in pages:
            if month_re.match(p["title"]):
                p["type"] = "folder"

        return pages

    async def _fetch_pages(self, project_name: str) -> list[dict]:
        """兼容旧调用：返回扁平列表（树形的前序遍历）"""
        tree = await self._fetch_tree(project_name, max_depth=2)
        return self._flatten(tree)


# ---------------------------------------------------------------------------
# 工具 2：获取页面内容
# ---------------------------------------------------------------------------

class FlowUsGetPageTool(Tool):
    """获取 FlowUs 页面的 Markdown 内容"""

    def __init__(self):
        super().__init__(
            name="flowus_get_page",
            description=(
                "获取指定 FlowUs 页面的 Markdown 内容。"
                "参数 page_id 是 36 位 UUID，可从 flowus_list_pages 或 flowus_search 获取。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="page_id",
                type="string",
                description="页面 ID（36 位 UUID）",
                required=True,
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        page_id = parameters.get("page_id", "").strip()
        if not page_id:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="page_id 不能为空",
            )

        print(f"📄 [flowus_get_page] page_id={page_id}")
        try:
            markdown_text = _run_async(self._fetch_content(page_id))
            if not markdown_text:
                return ToolResponse.partial(
                    text=f"页面 {page_id} 内容为空",
                    data={"page_id": page_id, "markdown": ""},
                )

            # 截断超长内容，避免撑爆 LLM 上下文（阈值 2000，多轮对话更安全）
            preview = markdown_text[:2000]
            if len(markdown_text) > 2000:
                preview += f"\n\n...(共 {len(markdown_text)} 字符，已截断，如需完整内容请单独说明)"

            print(f"  ✅ 获取成功，{len(markdown_text)} 字符")
            return ToolResponse.success(
                text=preview,
                data={
                    "page_id": page_id,
                    "markdown": markdown_text,
                    "length": len(markdown_text),
                },
            )
        except Exception as e:
            print(f"  ❌ 获取页面失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"获取页面失败: {str(e)}",
                context={"page_id": page_id},
            )

    async def _fetch_content(self, page_id: str) -> str:
        client = get_http_client()

        async def fetch(http, session_id):
            result = await client.call_tool(
                http, session_id, "API-getMarkdown",
                {"page_id": page_id}, 2,
            )
            data = extract_tool_result(result)

            if isinstance(data, dict):
                return data.get("markdown") or data.get("content") or ""
            elif isinstance(data, str):
                return data
            return str(data) if data else ""

        return await client.with_session(fetch)


# ---------------------------------------------------------------------------
# 工具 3：语义搜索
# ---------------------------------------------------------------------------

class FlowUsSearchTool(Tool):
    """语义搜索 FlowUs 工作空间"""

    def __init__(self):
        super().__init__(
            name="flowus_search",
            description=(
                "对整个 FlowUs 工作空间进行语义搜索，返回匹配的页面列表（含 page_id 和标题）。"
                "用于按主题查找内容，而非按项目浏览。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="搜索关键词或主题描述",
                required=True,
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        query = parameters.get("query", "").strip()
        if not query:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="query 不能为空",
            )

        print(f"🔍 [flowus_search] query={query}")
        try:
            results = _run_async(self._search(query))
            if not results:
                return ToolResponse.partial(
                    text=f"未找到与 '{query}' 相关的页面",
                    data={"query": query, "results": []},
                )

            text_lines = [f"搜索 '{query}' 共找到 {len(results)} 个相关页面："]
            for i, r in enumerate(results, 1):
                title = r.get("page_title") or r.get("title") or "(无标题)"
                pid = r.get("page_id") or r.get("id", "")
                text_lines.append(f"{i}. {title}  (id={pid})")
            text = "\n".join(text_lines)

            print(f"  ✅ 找到 {len(results)} 个结果")
            return ToolResponse.success(
                text=text,
                data={"query": query, "results": results},
            )
        except Exception as e:
            print(f"  ❌ 搜索失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"搜索失败: {str(e)}",
                context={"query": query},
            )

    async def _search(self, query: str) -> list[dict]:
        client = get_http_client()

        async def fetch(http, session_id):
            # 优先语义搜索
            try:
                result = await client.call_tool(
                    http, session_id, "API-semanticSearch",
                    {"query": query}, 2,
                )
                data = extract_tool_result(result)
                if isinstance(data, dict) and data.get("results"):
                    return data["results"]
            except Exception:
                pass

            # 回退到常规搜索
            try:
                result = await client.call_tool(
                    http, session_id, "API-search",
                    {"query": query, "page_size": 20}, 3,
                )
                data = extract_tool_result(result)
                if isinstance(data, dict):
                    return data.get("results", [])
                if isinstance(data, list):
                    return data
            except Exception:
                pass

            return []

        return await client.with_session(fetch)
