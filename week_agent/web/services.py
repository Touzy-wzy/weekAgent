"""Web UI 业务服务 - 通过 Agent 工具层获取数据

原 web_ui.py 的页面树发现、内容获取逻辑现在统一走 Agent 工具类，
保证 Web UI 与 Agent 对话使用同一套数据访问层。
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import markdown

from week_agent.agent.tools.flowus_tools import (
    FlowUsGetPageTool,
    FlowUsListPagesTool,
    FlowUsSearchTool,
)

# 缓存
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()
CACHE_TTL = 300  # 5 分钟

# 线程池：Web 路由在 async 事件循环中，工具的 run() 是同步方法，
# 需要在独立线程中运行（工具内部会再用线程跑 async FlowUs 调用）
_executor = ThreadPoolExecutor(max_workers=4)


def _run_tool_sync(tool, parameters: dict) -> Any:
    """在线程池中同步执行工具，返回 ToolResponse"""
    fut = _executor.submit(tool.run, parameters)
    return fut.result()


async def cached_get(key: str, fetcher):
    """通用缓存读取"""
    async with _cache_lock:
        if key in _cache:
            ts, val = _cache[key]
            if time.time() - ts < CACHE_TTL:
                return val
    result = await fetcher()
    async with _cache_lock:
        _cache[key] = (time.time(), result)
    return result


async def fetch_page_tree(project_name: str = "积成电子") -> list[dict]:
    """获取项目下的页面树（通过 FlowUsListPagesTool）"""
    tool = FlowUsListPagesTool()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        _executor, tool.run, {"project_name": project_name}
    )
    if response.status.value == "error":
        raise RuntimeError(response.text)
    return response.data.get("pages", [])


async def fetch_page_content(page_id: str) -> dict:
    """获取页面内容并转换为 HTML（通过 FlowUsGetPageTool）"""
    tool = FlowUsGetPageTool()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        _executor, tool.run, {"page_id": page_id}
    )
    if response.status.value == "error":
        raise RuntimeError(response.text)

    md_text = response.data.get("markdown", "")
    html_content = markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables", "codehilite", "nl2br"],
    )
    return {"html": html_content, "markdown": md_text}


async def search_pages(query: str) -> list[dict]:
    """语义搜索页面（通过 FlowUsSearchTool）"""
    tool = FlowUsSearchTool()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        _executor, tool.run, {"query": query}
    )
    if response.status.value == "error":
        raise RuntimeError(response.text)
    return response.data.get("results", [])


# Agent 实例池：按 session_id 维护，同一会话复用 Agent 保持多轮记忆
# 内存字典实现，服务重启后清空（符合方案 A）
_agent_pool: dict[str, Any] = {}
_agent_pool_lock = asyncio.Lock()
# 简单的 LRU：超过 20 个会话时清理最早的
_MAX_AGENTS = 20


async def get_or_create_agent(session_id: str = "default") -> Any:
    """获取或创建 Agent 实例（按 session_id 复用，保持多轮对话记忆）"""
    async with _agent_pool_lock:
        if session_id in _agent_pool:
            return _agent_pool[session_id]

        # 超过上限时清理最早的会话
        if len(_agent_pool) >= _MAX_AGENTS:
            oldest_key = next(iter(_agent_pool))
            del _agent_pool[oldest_key]

        from week_agent.agent.runner import create_flowus_agent
        agent = create_flowus_agent()
        _agent_pool[session_id] = agent
        return agent


async def run_agent_query(query: str, session_id: str = "default") -> str:
    """运行 Agent 查询（完整 ReAct 流程，含 LLM 推理 + 多轮记忆）

    按 session_id 复用 Agent 实例，history_manager 累积历史，
    FlowUsAgent._build_messages 把历史注入到 LLM 调用中。

    Agent.run() 是同步方法且会调用 LLM，耗时较长，
    在线程池中运行避免阻塞 Web 事件循环。
    """
    agent = await get_or_create_agent(session_id)

    def _run():
        return agent.run(query)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _run)


async def clear_agent_session(session_id: str = "default") -> bool:
    """清除指定会话的 Agent（重置对话历史）"""
    async with _agent_pool_lock:
        if session_id in _agent_pool:
            del _agent_pool[session_id]
            return True
        return False


async def clear_cache(project: str = "积成电子") -> int:
    """清除缓存"""
    async with _cache_lock:
        keys_to_del = [
            k
            for k in _cache
            if k.startswith(f"pages_{project}")
            or k.startswith("content_")
            or k.startswith("info_")
            or k.startswith("search_")
        ]
        for k in keys_to_del:
            del _cache[k]
    return len(keys_to_del)
