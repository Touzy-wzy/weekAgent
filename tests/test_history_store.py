"""SQLiteHistoryStore 单元测试

测试持久化历史存储的核心功能：
- 消息追加、查询、清除
- 轮次边界检测
- 历史压缩
- 序列化/反序列化
- 进程重启后数据不丢失
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from hello_agents.core.message import Message
from week_agent.memory.history_store import SQLiteHistoryStore


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_history.db"
        yield db_path


@pytest.fixture
def store(temp_db):
    """创建 SQLiteHistoryStore 实例"""
    s = SQLiteHistoryStore(
        session_id="test-session",
        db_path=temp_db,
        min_retain_rounds=2,
    )
    yield s
    s.close()


def test_append_and_get_history(store):
    """测试追加消息和获取历史"""
    # 追加消息
    store.append(Message("hello", "user"))
    store.append(Message("hi", "assistant"))
    store.append(Message("how are you?", "user"))

    # 获取历史
    history = store.get_history()
    assert len(history) == 3
    assert history[0].role == "user"
    assert history[0].content == "hello"
    assert history[1].role == "assistant"
    assert history[1].content == "hi"
    assert history[2].role == "user"
    assert history[2].content == "how are you?"


def test_get_history_with_session_id(store):
    """测试使用指定 session_id 获取历史"""
    # 追加到不同会话
    store.session_id = "session-1"
    store.append(Message("msg1", "user"))

    store.session_id = "session-2"
    store.append(Message("msg2", "user"))

    # 获取 session-1 的历史
    history = store.get_history("session-1")
    assert len(history) == 1
    assert history[0].content == "msg1"

    # 获取 session-2 的历史
    history = store.get_history("session-2")
    assert len(history) == 1
    assert history[0].content == "msg2"


def test_clear_history(store):
    """测试清除历史"""
    store.append(Message("hello", "user"))
    store.append(Message("hi", "assistant"))
    assert store.get_message_count() == 2

    store.clear()
    assert store.get_message_count() == 0
    assert store.get_history() == []


def test_clear_specific_session(store):
    """测试清除指定会话的历史"""
    store.session_id = "session-1"
    store.append(Message("msg1", "user"))

    store.session_id = "session-2"
    store.append(Message("msg2", "user"))

    # 清除 session-1
    store.clear("session-1")
    assert store.get_message_count("session-1") == 0
    assert store.get_message_count("session-2") == 1


def test_estimate_rounds(store):
    """测试预估轮次数"""
    # 一轮
    store.append(Message("q1", "user"))
    store.append(Message("a1", "assistant"))
    assert store.estimate_rounds() == 1

    # 两轮
    store.append(Message("q2", "user"))
    store.append(Message("a2", "assistant"))
    assert store.estimate_rounds() == 2

    # 三轮
    store.append(Message("q3", "user"))
    assert store.estimate_rounds() == 3


def test_find_round_boundaries(store):
    """测试查找轮次边界"""
    store.append(Message("q1", "user"))
    store.append(Message("a1", "assistant"))
    store.append(Message("q2", "user"))
    store.append(Message("a2", "assistant"))
    store.append(Message("q3", "user"))

    boundaries = store.find_round_boundaries()
    assert boundaries == [0, 2, 4]


def test_compress_history(store):
    """测试压缩历史"""
    # 添加足够的轮次（min_retain_rounds=2）
    for i in range(5):
        store.append(Message(f"q{i}", "user"))
        store.append(Message(f"a{i}", "assistant"))

    # 压缩前
    assert store.estimate_rounds() == 5
    assert store.get_message_count() == 10

    # 压缩
    store.compress("前3轮对话的摘要")

    # 压缩后：保留最近2轮 + 1个summary
    history = store.get_history()
    assert len(history) == 5  # 1 summary + 4 messages (2 rounds)

    # 验证 summary 消息
    assert history[0].role == "summary"
    assert "前3轮对话的摘要" in history[0].content


def test_compress_not_enough_rounds(store):
    """测试轮次不足时不压缩"""
    # 只添加2轮（等于 min_retain_rounds）
    for i in range(2):
        store.append(Message(f"q{i}", "user"))
        store.append(Message(f"a{i}", "assistant"))

    store.compress("摘要")

    # 不应该压缩
    assert store.get_message_count() == 4


def test_to_dict_and_load_from_dict(store):
    """测试序列化和反序列化"""
    # 添加消息
    store.append(Message("hello", "user"))
    store.append(Message("hi", "assistant"))

    # 序列化
    data = store.to_dict()
    assert data["session_id"] == "test-session"
    assert len(data["history"]) == 2
    assert data["rounds"] == 1

    # 反序列化到新会话
    new_store = SQLiteHistoryStore(
        session_id="new-session",
        db_path=store._db_path,
    )
    new_store.load_from_dict(data)

    # 验证
    history = new_store.get_history("new-session")
    assert len(history) == 2
    assert history[0].content == "hello"
    assert history[1].content == "hi"


def test_persistence_after_reopen(temp_db):
    """测试进程重启后数据不丢失"""
    # 第一次打开并写入
    store1 = SQLiteHistoryStore(session_id="persist-test", db_path=temp_db)
    store1.append(Message("hello", "user"))
    store1.append(Message("hi", "assistant"))
    store1.close()

    # 重新打开（模拟进程重启）
    store2 = SQLiteHistoryStore(session_id="persist-test", db_path=temp_db)
    history = store2.get_history()

    assert len(history) == 2
    assert history[0].content == "hello"
    assert history[1].content == "hi"
    store2.close()


def test_list_sessions(store):
    """测试列出所有会话"""
    store.session_id = "session-1"
    store.append(Message("msg1", "user"))

    store.session_id = "session-2"
    store.append(Message("msg2", "user"))

    store.session_id = "session-3"
    store.append(Message("msg3", "user"))

    sessions = store.list_sessions()
    assert len(sessions) == 3
    assert "session-1" in sessions
    assert "session-2" in sessions
    assert "session-3" in sessions


def test_delete_session(store):
    """测试删除指定会话"""
    store.session_id = "session-1"
    store.append(Message("msg1", "user"))

    store.session_id = "session-2"
    store.append(Message("msg2", "user"))

    # 删除 session-1
    store.delete_session("session-1")

    assert store.get_message_count("session-1") == 0
    assert store.get_message_count("session-2") == 1


def test_message_metadata(store):
    """测试消息元数据"""
    msg = Message(
        content="hello",
        role="user",
        metadata={"source": "test", "priority": "high"}
    )
    store.append(msg)

    history = store.get_history()
    assert len(history) == 1
    assert history[0].metadata == {"source": "test", "priority": "high"}


def test_message_timestamp(store):
    """测试消息时间戳"""
    from datetime import datetime

    timestamp = datetime(2026, 1, 1, 12, 0, 0)
    msg = Message(
        content="hello",
        role="user",
        timestamp=timestamp
    )
    store.append(msg)

    history = store.get_history()
    assert len(history) == 1
    assert history[0].timestamp is not None
    # 时间戳可能因精度问题有微小差异
    assert history[0].timestamp.year == 2026
    assert history[0].timestamp.month == 1
    assert history[0].timestamp.day == 1


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v"])
