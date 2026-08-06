"""Web UI 业务服务 - 通过 Agent 工具层获取数据

原 web_ui.py 的页面树发现、内容获取逻辑现在统一走 Agent 工具类，
保证 Web UI 与 Agent 对话使用同一套数据访问层。
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import markdown

from week_agent.agent.tools.flowus_tools import (
    FlowUsGetPageTool,
    FlowUsListPagesTool,
    FlowUsSearchTool,
)
from week_agent.config import DATA_DIR
from week_agent.memory.session_store import AgentSessionStore

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
    """获取或创建 Agent 实例（按 session_id 复用，保持多轮对话记忆）

    修复：把 session_id 传给 create_flowus_agent，让 SQLiteHistoryStore
    按会话隔离历史（此前所有会话共用 'default' 历史，互相污染）。
    """
    async with _agent_pool_lock:
        if session_id in _agent_pool:
            return _agent_pool[session_id]

        # 超过上限时清理最早的会话
        if len(_agent_pool) >= _MAX_AGENTS:
            oldest_key = next(iter(_agent_pool))
            del _agent_pool[oldest_key]

        from week_agent.agent.runner import create_flowus_agent
        agent = create_flowus_agent(session_id=session_id)
        _agent_pool[session_id] = agent
        return agent


async def run_agent_query(query: str, session_id: str = "default") -> str:
    """运行 Agent 查询（完整 ReAct 流程，含 LLM 推理 + 多轮记忆）

    按 session_id 复用 Agent 实例，history_manager 累积历史，
    FlowUsAgent._build_messages 把历史注入到 LLM 调用中。

    Agent.run() 是同步方法且会调用 LLM，耗时较长，
    在线程池中运行避免阻塞 Web 事件循环。
    """
    # 确保会话元数据存在（兼容直接传 session_id 的旧调用）
    session_store = AgentSessionStore()
    session_store.create_with_id(session_id)

    agent = await get_or_create_agent(session_id)

    def _run():
        return agent.run(query)

    loop = asyncio.get_event_loop()
    answer = await loop.run_in_executor(_executor, _run)

    # 更新会话元数据：自动命名、更新时间、消息数对账
    _refresh_session_meta(session_store, agent, session_id, query)
    return answer


async def clear_agent_session(session_id: str = "default") -> bool:
    """清除指定会话的 Agent（重置对话历史）"""
    async with _agent_pool_lock:
        if session_id in _agent_pool:
            del _agent_pool[session_id]
            return True
        return False


# =====================================================================
# 通用智能体对话：会话管理 + 文件上传 + SSE 流式
# =====================================================================

_UPLOAD_ALLOWED_EXTENSIONS = {".docx", ".pdf", ".txt", ".md", ".xlsx"}


def _session_store() -> AgentSessionStore:
    """获取会话元数据存储（进程内复用连接池由 sqlite 自身管理）"""
    return AgentSessionStore()


def create_agent_session() -> dict:
    """新建智能体对话会话"""
    return _session_store().create(title="新对话")


def list_agent_sessions() -> list[dict]:
    """列出所有智能体对话会话（按更新时间倒序）"""
    return _session_store().list()


def get_agent_session(session_id: str) -> dict | None:
    """获取单个会话元数据"""
    return _session_store().get(session_id)


def get_agent_messages(session_id: str) -> list[dict]:
    """获取会话的历史消息（供前端加载历史对话）"""
    from week_agent.memory.history_store import SQLiteHistoryStore

    store = SQLiteHistoryStore(session_id=session_id)
    messages = store.get_history()
    # 过滤掉 system 摘要消息，避免前端展示
    return [m for m in messages if m.get("role") in ("user", "assistant")]


def delete_agent_session(session_id: str) -> bool:
    """删除会话：元数据 + 历史消息 + Agent 实例 + 上传文件"""
    store = _session_store()
    deleted = store.delete(session_id)

    # 删除历史消息
    try:
        from week_agent.memory.history_store import SQLiteHistoryStore

        SQLiteHistoryStore(session_id=session_id).clear()
    except Exception as e:
        print(f"⚠️ [delete_agent_session] 清理历史失败: {e}")

    # 删除内存 Agent 实例
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 事件循环运行中，直接操作（调用方通常是 sync 路由）
            pass
        if session_id in _agent_pool:
            del _agent_pool[session_id]
    except Exception:
        pass

    # 删除上传文件目录
    upload_dir = DATA_DIR / "uploads" / session_id
    if upload_dir.exists():
        import shutil

        shutil.rmtree(upload_dir, ignore_errors=True)

    return deleted


def save_agent_upload(session_id: str, upload_file) -> dict:
    """保存通用对话上传文件（白名单校验）

    Args:
        session_id: 会话 ID
        upload_file: fastapi.UploadFile

    Returns:
        {"name", "size", "ext"} 信息
    """
    from fastapi import UploadFile

    filename = Path(upload_file.filename or "").name
    ext = Path(filename).suffix.lower()
    if not filename:
        raise ValueError("文件名不能为空")
    if ext not in _UPLOAD_ALLOWED_EXTENSIONS:
        raise ValueError(
            f"不支持的文件类型: {ext}（允许: {', '.join(sorted(_UPLOAD_ALLOWED_EXTENSIONS))}）"
        )

    upload_dir = DATA_DIR / "uploads" / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename

    # 同名文件：加时间戳后缀避免覆盖
    if file_path.exists():
        import uuid

        file_path = upload_dir / f"{Path(filename).stem}-{uuid.uuid4().hex[:4]}{ext}"
        filename = file_path.name

    content = upload_file.file.read() if hasattr(upload_file, "file") else upload_file.read()
    file_path.write_bytes(content)

    return {
        "session_id": session_id,
        "name": filename,
        "size": len(content),
        "ext": ext,
        "path": str(file_path),
    }


def list_agent_files(session_id: str) -> list[dict]:
    """列出会话已上传的文件"""
    upload_dir = DATA_DIR / "uploads" / session_id
    if not upload_dir.exists():
        return []
    files = []
    for p in upload_dir.iterdir():
        if p.is_file():
            files.append({
                "name": p.name,
                "size": p.stat().st_size,
                "ext": p.suffix.lower(),
            })
    files.sort(key=lambda f: f["name"])
    return files


def _refresh_session_meta(session_store: AgentSessionStore, agent: Any, session_id: str, user_query: str) -> None:
    """对话完成后刷新会话元数据：自动命名 + 更新时间 + 消息数对账"""
    try:
        session_store.create_with_id(session_id)
        session_store.ensure_title(session_id, user_query)
        session_store.touch(session_id)
        # 消息数对账（以 messages 表实际为准）
        messages = get_agent_messages(session_id)
        session_store.set_message_count(session_id, len(messages))
    except Exception as e:
        print(f"⚠️ [_refresh_session_meta] 更新会话元数据失败: {e}")


async def stream_agent_query(query: str, session_id: str = "default"):
    """SSE 流式运行 Agent 查询（async generator）

    复用 hello-agents 的 arun_stream()，实时产出：
    - agent_start / step_start / llm_chunk（打字机效果）
    - tool_call_finish（工具调用结果）
    - agent_finish（最终答案）
    - error

    事件格式为标准 SSE：event: <type>\ndata: <json>\n\n

    保活机制（豆包方案）：
    1. 首字节立即响应（: connected）：避免 fetch stream 首字节超时
    2. 心跳保活（: heartbeat）：Agent 多步推理期间 LLM 思考可能持续数秒无事件输出，
       通过 asyncio.Queue 并发运行 agent 与心跳任务，每 5 秒发送 SSE 注释行保活。
    """
    from hello_agents.core.streaming import StreamEventType

    session_store = _session_store()
    session_store.create_with_id(session_id)

    agent = await get_or_create_agent(session_id)

    # 队列哨兵
    HEARTBEAT = object()
    DONE = object()

    queue: asyncio.Queue = asyncio.Queue()

    async def producer():
        """运行 agent，将事件放入队列"""
        try:
            async for event in agent.arun_stream(query):
                await queue.put(event)
        except Exception as e:
            await queue.put(e)
        finally:
            await queue.put(DONE)

    async def heartbeat():
        """每 5 秒发送一次心跳"""
        while True:
            await asyncio.sleep(5)
            await queue.put(HEARTBEAT)

    producer_task = asyncio.create_task(producer())
    heartbeat_task = asyncio.create_task(heartbeat())

    final_answer = None
    try:
        # 立即发送首字节，避免 fetch stream 首字节超时
        # SSE 注释行（: 开头），浏览器/前端解析器会忽略，但 HTTP 响应已建立
        yield ": connected\n\n"

        while True:
            item = await queue.get()
            if item is DONE:
                break
            if item is HEARTBEAT:
                # SSE 注释行，浏览器会忽略，但能保持连接活跃
                yield ": heartbeat\n\n"
                continue
            if isinstance(item, Exception):
                print(f"❌ [stream_agent_query] 流式执行失败: {item}")
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'data': {'error': str(item)}}, ensure_ascii=False)}\n\n"
                break
            # 正常事件
            event = item
            etype = event.type.value if hasattr(event.type, "value") else str(event.type)
            if event.type == StreamEventType.AGENT_FINISH:
                final_answer = event.data.get("result", "")
            payload = {
                "type": etype,
                "data": event.data,
                "timestamp": event.timestamp,
            }
            yield f"event: {etype}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    finally:
        # 取消心跳任务（producer_task 在 DONE 后已自然结束）
        heartbeat_task.cancel()
        if not producer_task.done():
            producer_task.cancel()
        # 完成后刷新会话元数据
        _refresh_session_meta(session_store, agent, session_id, query)


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
