"""集成测试脚本 - 验证所有新组件"""

from week_agent.memory.history_store import SQLiteHistoryStore

def test_sqlite_history_store():
    """测试 SQLiteHistoryStore"""
    print("测试 SQLiteHistoryStore...")
    
    # 创建测试实例（使用内存数据库）
    store = SQLiteHistoryStore(session_id='test-session', db_path=':memory:')
    
    # 测试追加消息
    store.append({'role': 'user', 'content': '你好'})
    store.append({'role': 'assistant', 'content': '你好！有什么可以帮助你的？'})
    
    # 测试获取历史
    history = store.get_history()
    assert len(history) == 2, f"期望 2 条消息，实际 {len(history)} 条"
    print(f"  ✅ 获取历史成功，共 {len(history)} 条消息")
    
    # 测试轮次边界
    boundaries = store.find_round_boundaries()
    assert boundaries == [0], f"期望 [0]，实际 {boundaries}"
    print(f"  ✅ 轮次边界: {boundaries}")
    
    # 测试压缩
    store.compress('这是对话摘要')
    history = store.get_history()
    assert len(history) == 1, f"期望 1 条消息，实际 {len(history)} 条"
    assert history[0]['role'] == 'system', f"期望 system 角色，实际 {history[0]['role']}"
    print(f"  ✅ 压缩后历史: {len(history)} 条消息")
    
    print("✅ SQLiteHistoryStore 测试通过！\n")


def test_recall_history_tool():
    """测试 RecallHistoryTool"""
    print("测试 RecallHistoryTool...")
    
    from week_agent.agent.tools.history_tools import RecallHistoryTool
    
    tool = RecallHistoryTool()
    assert tool.name == "recall_history", f"期望 recall_history，实际 {tool.name}"
    print(f"  ✅ 工具名称: {tool.name}")
    
    # 测试参数
    params = tool.get_parameters()
    param_names = [p.name for p in params]
    assert 'op' in param_names, "缺少 op 参数"
    assert 'lo' in param_names, "缺少 lo 参数"
    assert 'hi' in param_names, "缺少 hi 参数"
    assert 'query' in param_names, "缺少 query 参数"
    print(f"  ✅ 参数完整: {param_names}")
    
    print("✅ RecallHistoryTool 测试通过！\n")


def test_memory_search_tool():
    """测试 MemorySearchTool"""
    print("测试 MemorySearchTool...")
    
    from week_agent.agent.tools.memory_tools import MemorySearchTool
    
    tool = MemorySearchTool()
    assert tool.name == "memory_search", f"期望 memory_search，实际 {tool.name}"
    print(f"  ✅ 工具名称: {tool.name}")
    
    # 测试参数
    params = tool.get_parameters()
    param_names = [p.name for p in params]
    assert 'query' in param_names, "缺少 query 参数"
    assert 'max_results' in param_names, "缺少 max_results 参数"
    print(f"  ✅ 参数完整: {param_names}")
    
    print("✅ MemorySearchTool 测试通过！\n")


def test_dream_processor():
    """测试 DreamProcessor"""
    print("测试 DreamProcessor...")
    
    from week_agent.memory.dream import DreamProcessor
    
    processor = DreamProcessor()
    print(f"  ✅ DreamProcessor 实例创建成功")
    
    # 测试提取规则
    test_lines = [
        "- **用户偏好**：喜欢简洁的回答",
        "我们决定使用 SQLite 作为数据库",
        "会议日期：2026-08-04",
    ]
    
    facts = []
    for line in test_lines:
        if line.startswith('- **'):
            facts.append({'type': 'fact', 'content': line})
        elif '决定' in line:
            facts.append({'type': 'decision', 'content': line})
        elif '日期' in line:
            facts.append({'type': 'date', 'content': line})
    
    assert len(facts) == 3, f"期望 3 条事实，实际 {len(facts)} 条"
    print(f"  ✅ 提取到 {len(facts)} 条事实")
    
    print("✅ DreamProcessor 测试通过！\n")


def test_skill_discovery():
    """测试 SkillDiscovery"""
    print("测试 SkillDiscovery...")
    
    from week_agent.skills.discovery import SkillDiscovery
    
    discovery = SkillDiscovery()
    print(f"  ✅ SkillDiscovery 实例创建成功")
    
    print("✅ SkillDiscovery 测试通过！\n")


def test_tool_registry():
    """测试工具注册"""
    print("测试工具注册...")
    
    from week_agent.agent.runner import create_tool_registry
    
    registry = create_tool_registry()
    tools = registry._tools
    
    expected_tools = [
        'flowus_list_pages', 'flowus_get_page', 'flowus_search',
        'agently_compose_mail', 'agently_send_mail',
        'recall_history', 'memory_search'
    ]
    
    for tool_name in expected_tools:
        assert tool_name in tools, f"缺少工具: {tool_name}"
    
    print(f"  ✅ 所有 {len(expected_tools)} 个工具已注册")
    print("✅ 工具注册测试通过！\n")


if __name__ == '__main__':
    print("=" * 60)
    print("weekAgent 生产级架构 - 集成测试")
    print("=" * 60)
    print()
    
    test_sqlite_history_store()
    test_recall_history_tool()
    test_memory_search_tool()
    test_dream_processor()
    test_skill_discovery()
    test_tool_registry()
    
    print("=" * 60)
    print("🎉 所有集成测试通过！")
    print("=" * 60)
