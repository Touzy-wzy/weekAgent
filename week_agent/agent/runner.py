"""Agent 运行器 - 创建并运行 FlowUs 智能体 / 日志监控智能体"""

import os

from hello_agents import HelloAgentsLLM, ToolRegistry
from hello_agents.core.config import Config

from week_agent.agent.flowus_agent import FlowUsAgent
from week_agent.agent.prompts import SYSTEM_PROMPT
from week_agent.agent.tools.flowus_tools import (
    FlowUsGetPageTool,
    FlowUsListPagesTool,
    FlowUsSearchTool,
)
from week_agent.agent.tools.flowus_weekly_tool import FlowUsFetchWeeklyTool
from week_agent.agent.tools.fill_excel_tool import FillExcelTool
from week_agent.agent.tools.agently_mail_tools import (
    AgentlyComposeMailTool,
    AgentlySendMailTool,
)
from week_agent.agent.tools.log_monitor_tools import (
    LogReadAnomaliesTool,
    LogPositionLookupTool,
    RunLogCheckTool,
    LogPreviewTool,
)
from week_agent.agent.log_monitor_agent import create_log_monitor_agent as _create_log_monitor_agent


def _check_llm_config() -> list[str]:
    """检查 LLM 配置是否完整，返回缺失项列表"""
    missing = []
    if not os.getenv("LLM_MODEL_ID"):
        missing.append("LLM_MODEL_ID")
    if not os.getenv("LLM_API_KEY"):
        missing.append("LLM_API_KEY")
    if not os.getenv("LLM_BASE_URL"):
        missing.append("LLM_BASE_URL")
    return missing


def create_tool_registry() -> ToolRegistry:
    """创建并注册通用智能体的工具集

    工具一旦注册即对 Agent 可见，但是否调用由 LLM 根据用户意图决定。
    日常聊天不会触发周报相关工具，只有在用户表达周报意图时才会被调用。
    """
    registry = ToolRegistry()
    # FlowUs 通用查询工具
    registry.register_tool(FlowUsListPagesTool())
    registry.register_tool(FlowUsGetPageTool())
    registry.register_tool(FlowUsSearchTool())
    # FlowUs 周报素材拉取（按日期区间汇总）
    registry.register_tool(FlowUsFetchWeeklyTool())
    # 通用文件读取（含 docx/pdf/txt/md/xlsx）
    from week_agent.agent.tools.read_uploaded_file_tool import (
        ListUploadedFilesTool,
        ReadUploadedFileTool,
    )
    registry.register_tool(ReadUploadedFileTool())
    registry.register_tool(ListUploadedFilesTool())
    # 周报 Excel 填写
    registry.register_tool(FillExcelTool())
    # 邮件
    registry.register_tool(AgentlyComposeMailTool())
    registry.register_tool(AgentlySendMailTool())
    # 常用收件人管理
    from week_agent.agent.tools.recipient_tools import (
        AddRecipientTool,
        ListRecipientsTool,
    )
    registry.register_tool(ListRecipientsTool())
    registry.register_tool(AddRecipientTool())
    # 历史/记忆/日志
    from week_agent.agent.tools.history_tools import RecallHistoryTool
    from week_agent.agent.tools.memory_tools import MemorySearchTool
    from week_agent.agent.tools.log_monitor_tools import LogListFilesTool
    registry.register_tool(RecallHistoryTool())
    registry.register_tool(MemorySearchTool())
    registry.register_tool(LogListFilesTool())
    return registry


def create_agent_config() -> Config:
    """创建优化的 Agent 配置

    针对 modelscope DeepSeek-V4-Flash 调优：
    - context_window: 32768（实际可用上下文，默认 128000 太大）
    - compression_threshold: 0.7（70% 时触发压缩，避免太晚）
    - min_retain_rounds: 6（压缩后保留 6 轮完整对话）
    - enable_smart_compression: True（启用智能摘要，保留关键信息）
    """
    return Config(
        context_window=32768,
        compression_threshold=0.7,
        min_retain_rounds=6,
        enable_smart_compression=True,
        # 智能摘要参数
        summary_max_tokens=800,
        summary_temperature=0.3,
        # 关闭自动保存（避免文件句柄问题，trace 仍保留）
        auto_save_enabled=False,
        # 保留 trace 用于调试
        trace_enabled=True,
    )


def create_flowus_agent(max_steps: int = 6, session_id: str = "default") -> FlowUsAgent:
    """创建 FlowUs Agent 实例（支持多轮对话记忆）

    Args:
        max_steps: 最大推理步数
        session_id: 会话 ID（传入后历史消息按会话隔离存储，默认 "default"）

    Returns:
        FlowUsAgent 实例（ReActAgent 子类，注入历史消息）

    Raises:
        RuntimeError: 若 LLM 配置缺失
    """
    missing = _check_llm_config()
    if missing:
        raise RuntimeError(
            f"LLM 配置缺失: {', '.join(missing)}。"
            f"请在项目根目录的 .env 文件中填写这些配置。"
        )

    llm = HelloAgentsLLM()
    registry = create_tool_registry()
    config = create_agent_config()

    # 把当前会话 ID 注入 system prompt，让 LLM 调用文件工具时传对参数
    system_prompt = SYSTEM_PROMPT + (
        f"\n\n## 当前会话信息\n"
        f"- 当前会话 ID: {session_id}\n"
        f"- 用户上传的文件保存在当前会话下，调用 `list_uploaded_files` 和 "
        f"`read_uploaded_file` 时，session_id 参数必须填 `{session_id}`\n"
    )

    return FlowUsAgent(
        name="FlowUs助手",
        llm=llm,
        tool_registry=registry,
        system_prompt=system_prompt,
        config=config,
        max_steps=max_steps,
        session_id=session_id,
    )


def run_query(query: str, max_steps: int = 6, retries: int = 2) -> str:
    """便捷方法：创建 Agent 并运行一次查询（单次会话，无记忆保持）

    注意：此函数每次创建新 Agent，不保留历史。
    多轮对话场景请直接使用 create_flowus_agent() 获取持久实例，
    或使用 run_agent_debug() / Web UI 的 session 机制。

    modelscope 等第三方 LLM 网关偶发返回 None choices，
    这里加入自动重试。

    Args:
        query: 用户问题
        max_steps: 最大推理步数
        retries: 失败重试次数（默认 2 次）

    Returns:
        Agent 的最终回答
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            agent = create_flowus_agent(max_steps=max_steps)
            return agent.run(query)
        except (TypeError, RuntimeError) as e:
            # TypeError: 'NoneType' object is not subscriptable (LLM 返回空 choices)
            # RuntimeError: 偶发 API 错误
            last_error = e
            if attempt <= retries:
                print(f"⚠️ 第 {attempt} 次尝试失败（{e}），重试中...")
            else:
                raise
    raise last_error  # type: ignore[misc]


# =====================================================================
# 日志监控智能体（复用 FlowUsAgent 体系）
# =====================================================================
def create_log_monitor_agent(max_steps: int = 8) -> FlowUsAgent:
    """创建日志监控 Agent 实例（继承 FlowUsAgent，支持多轮记忆）

    这是对外暴露的统一接口，内部委托给 week_agent.agent.log_monitor_agent。
    """
    return _create_log_monitor_agent(max_steps=max_steps)


def run_log_query(query: str, max_steps: int = 8, retries: int = 2) -> str:
    """便捷方法：创建日志监控 Agent 并运行一次查询（单次会话，无记忆保持）

    多轮对话请用 create_log_monitor_agent() 获取持久实例。
    """
    from week_agent.agent.log_monitor_agent import run_log_query as _run_log_query
    return _run_log_query(query, max_steps=max_steps, retries=retries)
