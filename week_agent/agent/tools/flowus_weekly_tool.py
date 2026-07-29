"""FlowUs 周报数据拉取组合工具

封装 flowus_search + flowus_get_page 的组合调用，按日期区间和项目名拉取周报素材。
减少 Agent 推理步数，一次调用拿到所有相关页面内容。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

from week_agent.flowus.http_client import get_http_client
from week_agent.flowus.utils import extract_tool_result


_executor = ThreadPoolExecutor(max_workers=4)


def _run_async(coro) -> Any:
    """在独立线程中运行 async 协程"""
    import asyncio as _asyncio

    def _runner():
        loop = _asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    fut = _executor.submit(_runner)
    return fut.result()


class FlowUsFetchWeeklyTool(Tool):
    """按日期区间从 FlowUs 拉取周报素材

    内部组合 flowus_search + flowus_get_page，一次调用获取多个相关页面的汇总文本。
    """

    def __init__(self):
        super().__init__(
            name="flowus_fetch_weekly",
            description=(
                "按日期区间从 FlowUs 拉取周报素材。"
                "返回多个相关页面的 Markdown 内容汇总。"
                "用于周报数据源 A：自动从 FlowUs 收集本周工作内容。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="project_name",
                type="string",
                description="FlowUs 项目名称，如 '积成电子'",
                required=True,
            ),
            ToolParameter(
                name="week_range",
                type="string",
                description="周报区间，如 '2026.7.22-7.28'。用于搜索时按日期过滤",
                required=True,
            ),
            ToolParameter(
                name="max_pages",
                type="integer",
                description="最多拉取页面数（默认 5，避免内容过长）",
                required=False,
                default=5,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        project_name = parameters.get("project_name", "").strip()
        week_range = parameters.get("week_range", "").strip()
        max_pages = parameters.get("max_pages", 5)

        if not project_name or not week_range:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="project_name 和 week_range 都不能为空",
            )

        print(f"📋 [flowus_fetch_weekly] project={project_name} range={week_range}")
        try:
            material = _run_async(self._fetch(project_name, week_range, max_pages))
            if not material:
                return ToolResponse.partial(
                    text=f"未在项目 '{project_name}' 中找到 '{week_range}' 区间的相关内容",
                    data={"project_name": project_name, "week_range": week_range, "material": ""},
                )

            print(f"  ✅ 拉取素材 {len(material)} 字符")
            return ToolResponse.success(
                text=f"从 FlowUs 项目 '{project_name}' 拉取周报素材成功（{len(material)} 字符）：\n\n{material[:6000]}",
                data={
                    "project_name": project_name,
                    "week_range": week_range,
                    "material": material,
                    "length": len(material),
                },
            )
        except Exception as e:
            print(f"  ❌ 拉取周报素材失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"拉取周报素材失败: {str(e)}",
                context={"project_name": project_name, "week_range": week_range},
            )

    async def _fetch(self, project_name: str, week_range: str, max_pages: int) -> str:
        """实际拉取逻辑：语义搜索 + 取 Markdown 汇总"""
        client = get_http_client()

        async def fetch(http, session_id):
            req_id = 2
            # 搜索 project_name + week_range 相关页面
            query = f"{project_name} {week_range}"
            result = await client.call_tool(
                http, session_id, "API-semanticSearch",
                {"query": query}, req_id,
            )
            req_id += 1
            search_data = extract_tool_result(result)

            results = []
            if isinstance(search_data, dict):
                results = search_data.get("results", [])
            elif isinstance(search_data, list):
                results = search_data

            if not results:
                return ""

            # 取前 max_pages 个页面的 Markdown
            pages_text: list[str] = []
            seen_ids: set[str] = set()
            for r in results[: max_pages * 2]:  # 多取一些用于去重
                page_id = r.get("page_id") or r.get("id", "")
                title = r.get("page_title") or r.get("title", "")
                if not page_id or page_id in seen_ids:
                    continue
                seen_ids.add(page_id)

                try:
                    md_result = await client.call_tool(
                        http, session_id, "API-getMarkdown",
                        {"page_id": page_id}, req_id,
                    )
                    req_id += 1
                    md_data = extract_tool_result(md_result)
                    md_text = ""
                    if isinstance(md_data, dict):
                        md_text = md_data.get("markdown") or md_data.get("content") or ""
                    elif isinstance(md_data, str):
                        md_text = md_data

                    if md_text:
                        # 截断单页内容
                        if len(md_text) > 3000:
                            md_text = md_text[:3000] + "..."
                        pages_text.append(f"## {title}\n\n{md_text}")
                except Exception:
                    continue

                if len(pages_text) >= max_pages:
                    break

            return "\n\n---\n\n".join(pages_text)

        return await client.with_session(fetch)
