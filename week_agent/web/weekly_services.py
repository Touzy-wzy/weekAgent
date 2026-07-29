"""周报智能体 Web 服务层

对接周报会话状态机 + 周报 Agent
"""

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

from week_agent.config import DATA_DIR
from week_agent.weekly_report.session import SESSIONS_DIR, SessionState, WeeklySession

# 线程池：Agent.run() 是同步方法，需独立线程
_executor = ThreadPoolExecutor(max_workers=4)

# 收件人列表文件
RECIPIENTS_FILE = DATA_DIR / "recipients.json"

# 周报 Agent 实例池：按 session_id 复用，保持多轮对话记忆
_weekly_agent_pool: dict[str, Any] = {}
_weekly_agent_pool_lock = asyncio.Lock()
_MAX_WEEKLY_AGENTS = 20


def _read_recipients() -> list[dict]:
    """读取常用收件人列表"""
    if not RECIPIENTS_FILE.exists():
        return []
    try:
        return json.loads(RECIPIENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_recipients(data: list[dict]):
    """写入常用收件人列表"""
    RECIPIENTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------- 会话管理 ----------

def create_session() -> WeeklySession:
    """创建新周报会话"""
    session = WeeklySession()
    session.save()
    return session


def get_session(session_id: str) -> Optional[WeeklySession]:
    """加载会话"""
    return WeeklySession.load(session_id)


def list_sessions() -> list[dict]:
    """列出所有会话"""
    return WeeklySession.list_all()


# ---------- 对话处理 ----------

def _extract_and_update_fields(session: WeeklySession, user_message: str):
    """从用户原始消息中提取结构化信息，更新 session 业务字段

    修复"说一句忘一句"的根因：原版只把信息存进 history，
    从不填充 session.reporter_name/week_range/data_source/flowus_project，
    导致下一轮 _build_context_prompt 读到的仍是"未提供"。

    用正则从用户消息提取，不依赖 LLM 输出格式，稳定可靠。
    """
    msg = user_message.strip()

    # 1. 填报人：匹配 "填报人王五" / "填报人：王五" / "我叫王五" / "姓名王五"
    if not session.reporter_name:
        m = re.search(r"填报人\s*[是为：:]?\s*([^\s,，。、]+)", msg)
        if not m:
            m = re.search(r"我叫([^\s,，。、]+)", msg)
        if not m:
            m = re.search(r"姓名\s*[是为：:]?\s*([^\s,，。、]+)", msg)
        if m:
            session.reporter_name = m.group(1)

    # 2. 周报区间：优先匹配日期范围，再匹配 "周报区间xxx"
    if not session.week_range:
        m = re.search(
            r"(\d{4}\.\d{1,2}\.\d{1,2})\s*[到至\-~]\s*(\d{1,2}\.\d{1,2}|\d{4}\.\d{1,2}\.\d{1,2})",
            msg,
        )
        if m:
            start = m.group(1)
            end = m.group(2)
            # 结尾无年份时补上开头年份
            if len(end.split(".")) == 2:
                year = start.split(".")[0]
                end = f"{year}.{end}"
            session.week_range = f"{start}~{end}"
        else:
            m = re.search(r"周报区间\s*[是为：:]?\s*(.+?)(?:[，,。]|$)", msg)
            if m:
                session.week_range = m.group(1).strip()

    # 3. 数据源：flowus / docx / word
    if not session.data_source:
        msg_lower = msg.lower()
        if "flowus" in msg_lower:
            session.data_source = "flowus"
        elif "docx" in msg_lower or "word" in msg_lower or "上传" in msg:
            session.data_source = "docx"

    # 4. FlowUs 项目名：当数据源为 flowus 时，从消息提取项目名
    if session.data_source == "flowus" and not session.flowus_project:
        # 先明确匹配 "项目xxx" / "项目：xxx"
        m = re.search(r"项目\s*[是为：:]?\s*([^\s,，。、]+)", msg)
        if m:
            session.flowus_project = m.group(1)
        else:
            # 从消息中剔除已知结构化短语，剩下的中文串作为项目名候选
            cleaned = msg
            for pattern in [
                r"填报人\s*[是为：:]?\s*[^\s,，。、]+",
                r"我叫[^\s,，。、]+",
                r"姓名\s*[是为：:]?\s*[^\s,，。、]+",
                r"周报区间\s*[是为：:]?\s*.+?(?:[，,。]|$)",
                r"\d{4}\.\d{1,2}\.\d{1,2}\s*[到至\-~]\s*\d{1,2}\.?\d{0,2}",
                r"数据源\s*[是为：:]?\s*\w+",
                r"flowus", r"docx", r"word",
                r"这两个文件", r"这两个",
            ]:
                cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
            # 匹配剩下的连续中文串（至少 2 字）
            m = re.search(r"([\u4e00-\u9fa5]{2,})", cleaned)
            if m:
                candidate = m.group(1)
                # 排除常见动词/虚词
                if candidate not in ("填报人", "周报区间", "数据源", "我叫", "姓名", "为", "是", "到", "至"):
                    session.flowus_project = candidate

    session.save()


async def _get_or_create_weekly_agent(session_id: str) -> Any:
    """按 session_id 复用周报 Agent 实例（保持多轮对话记忆）"""
    async with _weekly_agent_pool_lock:
        if session_id in _weekly_agent_pool:
            return _weekly_agent_pool[session_id]

        if len(_weekly_agent_pool) >= _MAX_WEEKLY_AGENTS:
            oldest_key = next(iter(_weekly_agent_pool))
            del _weekly_agent_pool[oldest_key]

        from week_agent.weekly_report.agent import create_weekly_agent
        agent = create_weekly_agent()
        _weekly_agent_pool[session_id] = agent
        return agent


async def handle_session_message(
    session: WeeklySession, user_message: str
) -> dict:
    """处理用户在会话中的消息，返回 Agent 回复与状态

    流程：
    1. 从用户消息提取结构化信息，更新 session 业务字段（修复记忆丢失根因）
    2. 把会话上下文拼装成 Agent prompt
    3. 调用周报 Agent.run()（按 session_id 复用，LLM 能看到历史）
    4. 根据 Agent 输出推进状态机
    5. 落盘会话
    """
    # 关键修复 1：调用 Agent 前，先从用户消息提取结构化字段
    _extract_and_update_fields(session, user_message)

    # 把会话上下文注入用户消息
    context_prompt = _build_context_prompt(session, user_message)

    # 关键修复 2：按 session_id 复用 Agent，LLM 能看到历史对话
    agent = await _get_or_create_weekly_agent(session.session_id)

    def _run():
        try:
            return agent.run(context_prompt)
        except Exception as e:
            return f"⚠️ Agent 执行失败: {e}"

    loop = asyncio.get_event_loop()
    answer = await loop.run_in_executor(_executor, _run)

    # 追加历史
    session.add_message("user", user_message)
    session.add_message("assistant", answer)

    # 状态机推进（简化版：根据回答内容推断）
    _advance_state_by_answer(session, answer)

    return {
        "session_id": session.session_id,
        "answer": answer,
        "state": session.state.value,
        "reporter_name": session.reporter_name,
        "week_range": session.week_range,
        "data_source": session.data_source,
        "flowus_project": session.flowus_project,
    }


def _build_context_prompt(session: WeeklySession, user_message: str) -> str:
    """构建带会话上下文的 prompt"""
    parts = [
        f"【当前会话状态】{session.state.value}",
        f"【填报人】{session.reporter_name or '未提供'}",
        f"【周报区间】{session.week_range or '未提供'}",
        f"【数据源】{session.data_source or '未选择'}",
    ]
    if session.data_source == "flowus":
        parts.append(f"【FlowUs 项目】{session.flowus_project or '未提供'}")
    if session.data_source == "docx" and session.uploaded_doc_path:
        parts.append(f"【已上传文件】{session.uploaded_doc_path.name}")
    if session.draft_xlsx_path:
        parts.append(f"【草稿 xlsx】{session.draft_xlsx_path}")
    if session.recipients:
        parts.append(f"【收件人】{', '.join(session.recipients)}")

    parts.append(f"\n【用户消息】{user_message}")
    return "\n".join(parts)


def _advance_state_by_answer(session: WeeklySession, answer: str):
    """根据 Agent 回答推断状态推进（简化版）

    实际工程中可让 Agent 输出结构化状态指令，这里靠关键词匹配。
    """
    answer_lower = answer.lower()

    # 检测到生成了 xlsx
    if "已生成" in answer and ".xlsx" in answer.lower():
        # 从回答中提取 xlsx 路径
        import re
        m = re.search(r"[\w\-/\\:]+\.(?:xlsx|XLSX)", answer)
        if m:
            session.draft_xlsx_path = Path(m.group(0))
        if session.state in (SessionState.DRAFTING, SessionState.FILLING, SessionState.GATHERING):
            session.transition(SessionState.REVIEWING)
            return

    # 检测到要求审核
    if "审核" in answer or "确认" in answer:
        if session.state == SessionState.FILLING:
            session.transition(SessionState.REVIEWING)
            return

    # 检测到邮件已发送
    if "已发送" in answer or "发送成功" in answer:
        session.mail_sent = True
        session.transition(SessionState.SENT)
        return

    # 检测到反问（要求补充信息）
    if any(kw in answer for kw in ["请提供", "请告诉我", "请问", "需要您提供"]):
        if session.state == SessionState.INIT:
            return  # 保持 INIT
        if session.state == SessionState.REVIEWING:
            session.transition(SessionState.COLLECTING_RECIPIENT)
            return

    # 检测到 compose_mail 完成（有 confirmation_token）
    if "confirmation_token" in answer_lower or "确认令牌" in answer:
        if session.state == SessionState.COLLECTING_RECIPIENT:
            session.transition(SessionState.CONFIRMING_SEND)
            return

    session.save()


# ---------- 上传 Word ----------

async def save_upload_file(session_id: str, upload_file: UploadFile) -> Path:
    """保存上传的 Word 文件到会话目录"""
    upload_dir = DATA_DIR / "uploads" / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = upload_file.filename or "uploaded.docx"
    # 防止路径穿越
    safe_name = Path(filename).name
    file_path = upload_dir / safe_name

    content = await upload_file.read()
    file_path.write_bytes(content)

    # 更新会话
    session = WeeklySession.load(session_id)
    if session:
        session.uploaded_doc_path = file_path
        if not session.data_source:
            session.data_source = "docx"
        session.save()

    return file_path


# ---------- 收件人 ----------

def list_recipients() -> list[dict]:
    return _read_recipients()


def add_recipient(name: str, email: str) -> dict:
    recipients = _read_recipients()
    # 去重
    if any(r.get("email") == email for r in recipients):
        return recipients
    recipients.append({"name": name, "email": email})
    _write_recipients(recipients)
    return recipients


def remove_recipient(email: str) -> list[dict]:
    recipients = _read_recipients()
    recipients = [r for r in recipients if r.get("email") != email]
    _write_recipients(recipients)
    return recipients
