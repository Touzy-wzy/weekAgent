"""周报专用 Agent - 基于 FlowUsAgent 二次开发（支持多轮记忆）"""

from typing import Optional

from hello_agents import HelloAgentsLLM, ReActAgent, ToolRegistry
from hello_agents.core.config import Config

from week_agent.agent.flowus_agent import FlowUsAgent
from week_agent.agent.prompts import WEEKLY_REPORT_PROMPT
from week_agent.agent.tools.agently_mail_tools import (
    AgentlyComposeMailTool,
    AgentlySendMailTool,
)
from week_agent.agent.tools.fill_excel_tool import FillExcelTool
from week_agent.agent.tools.flowus_weekly_tool import FlowUsFetchWeeklyTool
from week_agent.agent.tools.read_uploaded_doc_tool import ReadUploadedDocTool
from week_agent.agent.tools.flowus_tools import (
    FlowUsGetPageTool,
    FlowUsListPagesTool,
    FlowUsSearchTool,
)


def create_weekly_tool_registry() -> ToolRegistry:
    """创建周报 Agent 工具集"""
    registry = ToolRegistry()
    # 数据源 A：FlowUs
    registry.register_tool(FlowUsSearchTool())
    registry.register_tool(FlowUsListPagesTool())
    registry.register_tool(FlowUsGetPageTool())
    registry.register_tool(FlowUsFetchWeeklyTool())
    # 数据源 B：上传 Word
    registry.register_tool(ReadUploadedDocTool())
    # Excel 填写
    registry.register_tool(FillExcelTool())
    # 邮件
    registry.register_tool(AgentlyComposeMailTool())
    registry.register_tool(AgentlySendMailTool())
    return registry


def create_weekly_agent(max_steps: int = 8) -> FlowUsAgent:
    """创建周报 Agent 实例（FlowUsAgent 子类，支持多轮记忆）

    使用 FlowUsAgent 而非 ReActAgent，获得：
    - _build_messages 注入历史消息（LLM 能看到上一轮对话）
    - trace_logger 文件句柄自动重置（多次 run 不崩）
    - 智能摘要复用主 LLM

    Args:
        max_steps: 最大推理步数（周报生成步骤较多，默认 8）

    Returns:
        FlowUsAgent 实例
    """
    import os

    missing = []
    if not os.getenv("LLM_MODEL_ID"):
        missing.append("LLM_MODEL_ID")
    if not os.getenv("LLM_API_KEY"):
        missing.append("LLM_API_KEY")
    if not os.getenv("LLM_BASE_URL"):
        missing.append("LLM_BASE_URL")
    if missing:
        raise RuntimeError(
            f"LLM 配置缺失: {', '.join(missing)}。请在 .env 文件中填写。"
        )

    llm = HelloAgentsLLM()
    registry = create_weekly_tool_registry()
    config = Config(
        context_window=32768,
        compression_threshold=0.7,
        min_retain_rounds=6,
        enable_smart_compression=True,
        summary_max_tokens=800,
        summary_temperature=0.3,
        auto_save_enabled=False,
        trace_enabled=True,
    )

    return FlowUsAgent(
        name="周报助手",
        llm=llm,
        tool_registry=registry,
        system_prompt=WEEKLY_REPORT_PROMPT,
        config=config,
        max_steps=max_steps,
    )


def run_weekly_query(query: str, max_steps: int = 8, retries: int = 2) -> str:
    """便捷方法：创建周报 Agent 并运行一次查询

    Args:
        query: 用户问题
        max_steps: 最大推理步数
        retries: 失败重试次数

    Returns:
        Agent 的最终回答
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            agent = create_weekly_agent(max_steps=max_steps)
            return agent.run(query)
        except (TypeError, RuntimeError) as e:
            last_error = e
            if attempt <= retries:
                print(f"⚠️ 第 {attempt} 次尝试失败（{e}），重试中...")
            else:
                raise
    raise last_error  # type: ignore[misc]
