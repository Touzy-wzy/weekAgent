"""SQLiteHistoryStore - 基于 SQLite 的历史消息持久化存储

功能：
- 支持多会话（session_id）隔离
- 消息追加、查询、清除
- 轮次边界检测
- 历史压缩（生成 summary 替换旧消息）
- 序列化/反序列化（to_dict / load_from_dict）

SQLite 数据库存储在 week_agent/memory/history.db
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional


class SQLiteHistoryStore:
    """基于 SQLite 的历史消息持久化存储

    用法示例：
    ```python
    store = SQLiteHistoryStore(session_id="session-1")

    # 追加消息
    store.append({"role": "user", "content": "hello"})
    store.append({"role": "assistant", "content": "hi"})

    # 获取历史
    history = store.get_history()

    # 压缩历史
    store.compress("这是前面对话的摘要")

    # 序列化
    data = store.to_dict()

    # 反序列化
    store.load_from_dict(data)
    ```
    """

    def __init__(self, session_id: str = "default", db_path: str = "week_agent/memory/history.db", min_retain_rounds: int = 10):
        """初始化 SQLite 历史存储

        Args:
            session_id: 会话 ID
            db_path: SQLite 数据库文件路径
            min_retain_rounds: 最少保留轮次（压缩时使用）
        """
        self.session_id = session_id
        self.db_path = db_path
        self.min_retain_rounds = min_retain_rounds
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id)
            """)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def append(self, message: dict, session_id: str = None) -> None:
        """追加消息到历史

        Args:
            message: 消息字典，包含 role, content, timestamp(可选), metadata(可选)
            session_id: 会话 ID（可选，默认使用初始化时的 session_id）
        """
        session_id = session_id or self.session_id
        metadata_str = json.dumps(message.get("metadata")) if message.get("metadata") else None
        timestamp = message.get("timestamp")

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, message["role"], message["content"], timestamp, metadata_str)
            )
            conn.commit()

    def get_history(self, session_id: str = None) -> List[dict]:
        """获取会话的所有消息

        Args:
            session_id: 会话 ID（可选，默认使用初始化时的 session_id）

        Returns:
            消息列表，每条消息为 dict
        """
        session_id = session_id or self.session_id
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT role, content, timestamp, metadata
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,)
            )
            rows = cursor.fetchall()

        messages = []
        for row in rows:
            role, content, timestamp, metadata_str = row
            msg: dict = {"role": role, "content": content}
            if timestamp:
                msg["timestamp"] = timestamp
            if metadata_str:
                try:
                    msg["metadata"] = json.loads(metadata_str)
                except (json.JSONDecodeError, TypeError):
                    pass
            messages.append(msg)

        return messages

    def clear(self, session_id: str = None) -> None:
        """清除会话的所有历史消息

        Args:
            session_id: 会话 ID（可选，默认使用初始化时的 session_id）
        """
        session_id = session_id or self.session_id
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.commit()

    def find_round_boundaries(self, session_id: str = None) -> List[int]:
        """查找每轮对话的起始索引

        一轮对话从 role='user' 的消息开始。返回这些消息在历史列表中的索引。

        Args:
            session_id: 会话 ID（可选，默认使用初始化时的 session_id）

        Returns:
            每轮起始索引列表，例如 [0, 3, 7]
        """
        history = self.get_history(session_id)
        boundaries = []
        for i, msg in enumerate(history):
            if msg["role"] == "user":
                boundaries.append(i)
        return boundaries

    def compress(self, summary: str, session_id: str = None) -> None:
        """压缩历史：删除所有旧消息，保留一条 summary 系统消息

        Args:
            summary: 摘要文本
            session_id: 会话 ID（可选，默认使用初始化时的 session_id）
        """
        session_id = session_id or self.session_id
        with self._get_conn() as conn:
            # 删除该会话所有消息
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            # 插入一条系统消息作为摘要
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, "system", summary, None)
            )
            conn.commit()

    def to_dict(self, session_id: str = None) -> dict:
        """将会话历史序列化为字典

        Args:
            session_id: 会话 ID（可选，默认使用初始化时的 session_id）

        Returns:
            包含 session_id 和 history 的字典
        """
        session_id = session_id or self.session_id
        return {
            "session_id": session_id,
            "history": self.get_history(session_id),
        }

    def load_from_dict(self, data: dict, session_id: str = None) -> None:
        """从字典加载历史

        先清除该会话的现有历史，再从 data["history"] 中加载。

        Args:
            data: 包含 history 列表的字典
            session_id: 会话 ID（可选，默认使用初始化时的 session_id）
        """
        session_id = session_id or self.session_id
        self.clear(session_id)
        for msg in data.get("history", []):
            self.append(msg, session_id)
