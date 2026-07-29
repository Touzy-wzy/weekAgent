"""周报会话状态机 + JSON 持久化

7 个状态：
INIT → GATHERING → DRAFTING → FILLING → REVIEWING → COLLECTING_RECIPIENT → CONFIRMING_SEND → SENT/FAILED
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from week_agent.config import DATA_DIR


class SessionState(str, Enum):
    INIT = "init"
    GATHERING = "gathering"
    DRAFTING = "drafting"
    FILLING = "filling"
    REVIEWING = "reviewing"
    COLLECTING_RECIPIENT = "collecting_recipient"
    CONFIRMING_SEND = "confirming_send"
    SENT = "sent"
    FAILED = "failed"


SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class WeeklySession:
    """周报会话状态机

    维护会话上下文，落盘 JSON 可恢复。
    与 hello-agents HistoryManager 分离：HistoryManager 管 LLM 对话历史，
    WeeklySession 管业务流程状态。
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        state: SessionState = SessionState.INIT,
        reporter_name: str = "",
        week_range: str = "",
        data_source: str = "",  # "flowus" or "docx"
        uploaded_doc_path: Optional[Path] = None,
        flowus_project: str = "",
        material_text: str = "",
        draft_data: Optional[dict] = None,
        draft_xlsx_path: Optional[Path] = None,
        recipients: Optional[list[str]] = None,
        confirmation_token: str = "",
        mail_sent: bool = False,
        history: Optional[list[dict]] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.session_id = session_id or f"ws-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.state = state
        self.reporter_name = reporter_name
        self.week_range = week_range
        self.data_source = data_source
        self.uploaded_doc_path = uploaded_doc_path
        self.flowus_project = flowus_project
        self.material_text = material_text
        self.draft_data = draft_data
        self.draft_xlsx_path = draft_xlsx_path
        self.recipients = recipients or []
        self.confirmation_token = confirmation_token
        self.mail_sent = mail_sent
        self.history = history or []
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()

    # ---------- 状态流转 ----------

    def transition(self, new_state: SessionState):
        """状态流转"""
        self.state = new_state
        self.updated_at = datetime.now().isoformat()
        self.save()

    # ---------- 反问检查 ----------

    def check_init_complete(self) -> list[str]:
        """INIT 阶段检查缺失信息，返回缺失字段列表"""
        missing = []
        if not self.reporter_name:
            missing.append("reporter_name")
        if not self.week_range:
            missing.append("week_range")
        if not self.data_source:
            missing.append("data_source")
        elif self.data_source == "flowus" and not self.flowus_project:
            missing.append("flowus_project")
        elif self.data_source == "docx" and not self.uploaded_doc_path:
            missing.append("uploaded_doc_path")
        return missing

    def check_recipient_complete(self) -> list[str]:
        """COLLECTING_RECIPIENT 阶段检查"""
        if not self.recipients:
            return ["recipients"]
        return []

    # ---------- 历史记录 ----------

    def add_message(self, role: str, content: str):
        """追加对话历史（用于上下文恢复）"""
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self.updated_at = datetime.now().isoformat()
        self.save()

    # ---------- 持久化 ----------

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "reporter_name": self.reporter_name,
            "week_range": self.week_range,
            "data_source": self.data_source,
            "uploaded_doc_path": str(self.uploaded_doc_path) if self.uploaded_doc_path else None,
            "flowus_project": self.flowus_project,
            "material_text": self.material_text,
            "draft_data": self.draft_data,
            "draft_xlsx_path": str(self.draft_xlsx_path) if self.draft_xlsx_path else None,
            "recipients": self.recipients,
            "confirmation_token": self.confirmation_token,
            "mail_sent": self.mail_sent,
            "history": self.history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WeeklySession":
        uploaded = data.get("uploaded_doc_path")
        draft_xlsx = data.get("draft_xlsx_path")
        return cls(
            session_id=data["session_id"],
            state=SessionState(data["state"]),
            reporter_name=data.get("reporter_name", ""),
            week_range=data.get("week_range", ""),
            data_source=data.get("data_source", ""),
            uploaded_doc_path=Path(uploaded) if uploaded else None,
            flowus_project=data.get("flowus_project", ""),
            material_text=data.get("material_text", ""),
            draft_data=data.get("draft_data"),
            draft_xlsx_path=Path(draft_xlsx) if draft_xlsx else None,
            recipients=data.get("recipients", []),
            confirmation_token=data.get("confirmation_token", ""),
            mail_sent=data.get("mail_sent", False),
            history=data.get("history", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @property
    def file_path(self) -> Path:
        return SESSIONS_DIR / f"{self.session_id}.json"

    def save(self):
        """落盘"""
        self.file_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, session_id: str) -> Optional["WeeklySession"]:
        """从磁盘加载会话"""
        path = SESSIONS_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def list_all(cls) -> list[dict]:
        """列出所有会话摘要"""
        result = []
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append({
                    "session_id": data["session_id"],
                    "state": data["state"],
                    "reporter_name": data.get("reporter_name", ""),
                    "week_range": data.get("week_range", ""),
                    "updated_at": data.get("updated_at", ""),
                })
            except Exception:
                continue
        return result

    def delete(self):
        """删除会话"""
        if self.file_path.exists():
            self.file_path.unlink()
