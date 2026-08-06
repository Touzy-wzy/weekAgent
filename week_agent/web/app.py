"""FastAPI 应用 - FlowUs 内容浏览器 + Agent 对话"""

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from week_agent.config import DATA_DIR, DEFAULT_PROJECT, STATIC_DIR
from week_agent.web.services import (
    cached_get,
    clear_agent_session,
    clear_cache,
    create_agent_session,
    delete_agent_session,
    fetch_page_content,
    fetch_page_tree,
    get_agent_messages,
    get_agent_session,
    list_agent_files,
    list_agent_sessions,
    run_agent_query,
    save_agent_upload,
    search_pages,
    stream_agent_query,
)

app = FastAPI(title="GGBond")

# CORS（开发期 Vite dev server 跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面（Vue 构建产物）"""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>前端未构建，请先在 frontend/ 执行 npm run build</h1>", status_code=404)


@app.get("/api/pages")
async def list_pages(project: str = DEFAULT_PROJECT):
    """获取项目下的所有页面（通过 Agent 工具层）"""
    cache_key = f"pages_{project}"

    async def fetch():
        return await fetch_page_tree(project)

    try:
        pages = await cached_get(cache_key, fetch)
        return pages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/page/{page_id}")
async def get_page_content(page_id: str):
    """获取页面 Markdown 内容并转换为 HTML"""
    cache_key = f"content_{page_id}"

    async def fetch():
        return await fetch_page_content(page_id)

    try:
        content = await cached_get(cache_key, fetch)
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search")
async def search(q: str):
    """语义搜索页面（通过 Agent 工具层）"""
    cache_key = f"search_{q}"

    async def fetch():
        return await search_pages(q)

    try:
        results = await cached_get(cache_key, fetch)
        return {"query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/refresh")
async def refresh_cache(project: str = DEFAULT_PROJECT):
    """刷新所有缓存"""
    count = await clear_cache(project)
    return {"status": "ok", "cleared": count}


@app.post("/api/agent/chat")
async def agent_chat(q: str, session_id: str = "default"):
    """Agent 对话端点 - 通过 LLM 自主决策调用 FlowUs 工具

    与 /api/pages 等直接调用工具不同，这里走完整的 ReAct 流程：
    用户提问 → LLM 推理 → 选择工具 → 执行 → 整合答案

    支持多轮对话：按 session_id 复用 Agent 实例，历史消息注入 LLM。
    """
    try:
        answer = await run_agent_query(q, session_id=session_id)
        return {"query": q, "session_id": session_id, "answer": answer}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/reset")
async def agent_reset(session_id: str = "default"):
    """重置 Agent 会话（清空对话历史）"""
    cleared = await clear_agent_session(session_id)
    return {"session_id": session_id, "cleared": cleared}


# ==================== 通用智能体对话（会话管理 + 上传 + 流式） ====================


@app.post("/api/agent/sessions")
async def agent_create_session():
    """新建智能体对话会话"""
    return create_agent_session()


@app.get("/api/agent/sessions")
async def agent_list_sessions():
    """列出所有智能体对话会话（按更新时间倒序）"""
    return list_agent_sessions()


@app.get("/api/agent/sessions/{session_id}/messages")
async def agent_get_messages(session_id: str):
    """获取会话历史消息（前端加载历史对话用）"""
    meta = get_agent_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": session_id,
        "meta": meta,
        "messages": get_agent_messages(session_id),
    }


@app.delete("/api/agent/sessions/{session_id}")
async def agent_delete_session(session_id: str):
    """删除会话（元数据 + 历史 + 上传文件）"""
    deleted = delete_agent_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"session_id": session_id, "deleted": True}


@app.post("/api/agent/sessions/{session_id}/upload")
async def agent_upload_file(session_id: str, file: UploadFile):
    """上传文件到会话（白名单：docx/pdf/txt/xlsx/md）"""
    meta = get_agent_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        return save_agent_upload(session_id, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/sessions/{session_id}/files")
async def agent_list_files(session_id: str):
    """列出会话已上传文件"""
    meta = get_agent_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"session_id": session_id, "files": list_agent_files(session_id)}


@app.post("/api/agent/sessions/{session_id}/chat")
async def agent_session_chat(session_id: str, q: str):
    """智能体对话（一次性返回完整回答，兼容非流式客户端）"""
    meta = get_agent_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        answer = await run_agent_query(q, session_id=session_id)
        return {"query": q, "session_id": session_id, "answer": answer}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/sessions/{session_id}/chat/stream")
async def agent_session_chat_stream(session_id: str, q: str):
    """智能体对话（SSE 流式：思考中 → 工具调用 → 逐字回答）"""
    meta = get_agent_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    return StreamingResponse(
        stream_agent_query(q.strip(), session_id=session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/agent/sessions/{session_id}/chat/sse")
async def agent_session_chat_sse(session_id: str, q: str):
    """智能体对话（SSE 流式，GET 方式，供前端 EventSource 使用）

    与 POST /chat/stream 等价，但用 GET 以便前端使用原生 EventSource，
    避免 fetch + ReadableStream 在 Chrome 中被中止的问题。
    """
    meta = get_agent_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    return StreamingResponse(
        stream_agent_query(q.strip(), session_id=session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== 会话文件下载 ====================


@app.get("/api/agent/sessions/{session_id}/files/{filename}")
async def agent_download_file(session_id: str, filename: str):
    """下载会话内的文件（用户上传文件 / Agent 生成的周报草稿等）

    支持两种来源：
    - data/uploads/{session_id}/{filename}：用户上传的文件
    - data/agent_outputs/{session_id}/{filename}：Agent 生成的文件（如周报 xlsx）

    filename 不允许包含路径分隔符，防路径穿越。
    """
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    # 候选目录：上传目录 + Agent 输出目录
    candidates = [
        DATA_DIR / "uploads" / session_id / safe_name,
        DATA_DIR / "agent_outputs" / session_id / safe_name,
        DATA_DIR / "drafts" / safe_name,  # 兼容历史草稿目录
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return FileResponse(
                str(p),
                filename=p.name,
            )
    raise HTTPException(status_code=404, detail="文件不存在")


# 静态文件挂载
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA history 路由 fallback：非 API、非 static 资源的请求回退到 index.html

    顺序：FastAPI 按声明顺序匹配，此前已声明所有 /api/* 与 /static 挂载，
    此 catch-all 仅兜底前端路由（如 /chat、/knowledge）。
    """
    # 已存在的精确文件直接返回（static 下的 js/css/图片等）
    candidate = STATIC_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(str(candidate))

    # 其余前端路由回退到 index.html
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>前端未构建</h1>", status_code=404)
