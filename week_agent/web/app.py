"""FastAPI 应用 - FlowUs 内容浏览器 + Agent 对话"""

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from week_agent.config import DEFAULT_PROJECT, STATIC_DIR
from week_agent.web.services import (
    cached_get,
    clear_agent_session,
    clear_cache,
    fetch_page_content,
    fetch_page_tree,
    run_agent_query,
    search_pages,
)
from week_agent.web.weekly_services import (
    add_recipient,
    create_session,
    get_session,
    handle_session_message,
    list_recipients,
    list_sessions,
    remove_recipient,
    save_upload_file,
)

app = FastAPI(title="FlowUs 内容浏览器 + 周报 Agent")


@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面"""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>static/index.html 未找到</h1>")


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


# ==================== 周报智能体 API ====================


@app.post("/api/weekly/sessions")
async def weekly_create_session():
    """创建周报会话"""
    session = create_session()
    return session.to_dict()


@app.get("/api/weekly/sessions")
async def weekly_list_sessions():
    """列出所有周报会话"""
    return list_sessions()


@app.get("/api/weekly/sessions/{session_id}")
async def weekly_get_session(session_id: str):
    """查询周报会话状态"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.to_dict()


@app.post("/api/weekly/sessions/{session_id}/message")
async def weekly_send_message(session_id: str, q: str):
    """发送对话消息（非 SSE 流式版，一次返回完整结果）

    SSE 流式版见 /api/weekly/sessions/{session_id}/message/stream
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        result = await handle_session_message(session, q)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/weekly/sessions/{session_id}/upload")
async def weekly_upload_file(session_id: str, file: UploadFile):
    """上传 Word 文件绑定到会话"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 文件")
    try:
        path = await save_upload_file(session_id, file)
        return {
            "session_id": session_id,
            "filename": path.name,
            "path": str(path),
            "size": path.stat().st_size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weekly/sessions/{session_id}/draft")
async def weekly_download_draft(session_id: str):
    """下载当前会话的 xlsx 草稿"""
    session = get_session(session_id)
    if not session or not session.draft_xlsx_path:
        raise HTTPException(status_code=404, detail="无草稿")
    path = Path(session.draft_xlsx_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="草稿文件不存在")
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@app.post("/api/weekly/sessions/{session_id}/approve")
async def weekly_approve_draft(session_id: str):
    """审核通过，进入收件人收集"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    from week_agent.weekly_report.session import SessionState

    if session.state != SessionState.REVIEWING:
        raise HTTPException(status_code=400, detail=f"当前状态 {session.state.value} 不可审核")
    session.transition(SessionState.COLLECTING_RECIPIENT)
    return session.to_dict()


@app.post("/api/weekly/sessions/{session_id}/reject")
async def weekly_reject_draft(session_id: str, reason: str = ""):
    """要求修改，带修改意见"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    from week_agent.weekly_report.session import SessionState

    session.transition(SessionState.DRAFTING)
    if reason:
        session.add_message("user", f"[要求修改] {reason}")
    return session.to_dict()


@app.post("/api/weekly/sessions/{session_id}/send")
async def weekly_send_mail(session_id: str, to: str = ""):
    """二次确认后真正发送邮件（通过 Agent 调用工具）"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if to:
        session.recipients = [e.strip() for e in to.split(",") if e.strip()]
        session.save()
    if not session.recipients:
        raise HTTPException(status_code=400, detail="未提供收件人")
    try:
        result = await handle_session_message(
            session,
            f"请用 confirmation_token 发送邮件给: {', '.join(session.recipients)}",
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weekly/recipients")
async def weekly_list_recipients():
    """获取常用收件人列表"""
    return list_recipients()


@app.post("/api/weekly/recipients")
async def weekly_add_recipient(name: str, email: str):
    """新增常用收件人"""
    if not email:
        raise HTTPException(status_code=400, detail="email 不能为空")
    return add_recipient(name or email.split("@")[0], email)


@app.delete("/api/weekly/recipients")
async def weekly_remove_recipient(email: str):
    """删除常用收件人"""
    return remove_recipient(email)


# 静态文件挂载
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
