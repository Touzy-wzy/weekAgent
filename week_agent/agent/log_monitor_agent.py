# -*- coding: utf-8 -*-
"""LogMonitorAgent - 日志监控智能体

继承 FlowUsAgent，获得：
- 多轮对话记忆（历史注入 + 智能摘要）
- TraceLogger 文件句柄自动修复
- ReAct 循环能力

专注日志监控领域，注册日志相关工具：
- log_read_anomalies：读取异常记录
- log_position_lookup：定位日志在源文件的行号
- run_log_check：触发完整检查+告警+报告
- log_preview：快速预览（不调 LLM）
"""

from hello_agents import HelloAgentsLLM, ToolRegistry
from hello_agents.core.config import Config

from week_agent.agent.flowus_agent import FlowUsAgent
from week_agent.agent.tools import (
    LogReadAnomaliesTool,
    LogPositionLookupTool,
    RunLogCheckTool,
    LogPreviewTool,
)


SYSTEM_PROMPT = """你是一个日志监控分析助手，专注于本地日志文件的异常检测、语义分析与告警推送。

## 可用工具

1. **log_read_anomalies** - 读取监控日志文件中的 WARNING/ERROR 异常记录
   - 参数 filepath（可选，默认全部监控文件），max_records（默认 60）
   - 返回：时间戳、级别、模块、消息正文、自动聚合多行、附带位置索引

2. **log_position_lookup** - 查询某条日志在源文件中的行号区间
   - 参数 filepath（必填），keyword（关键字/级别/模块/时间戳），max_matches（默认 10）
   - 返回：匹配记录的起止行号（多行 traceback 只记首尾行）

3. **run_log_check** - 执行一次完整的日志检查与告警（推荐入口）
   - 参数 max_steps（默认 8）
   - 流程：读取异常 → LLM 语义分析（类型/严重度/影响/建议） → 多渠道告警（控制台 + 邮件每日汇总 + 企业微信 critical 实时） → 生成带位置索引的 Markdown 报告落盘
   - 返回：分析结论 + 报告文件路径 + 推送结果

4. **log_preview** - 快速预览异常记录（不调 LLM，不告警，不落盘）
   - 参数 limit（默认 5）

## 工作流程建议

用户提问时：
- 只要确认当前异常分布 → 用 `log_preview` 快速统计
- 需要语义分析/判断哪些是真异常 → 用 `log_read_anomalies` 读取后自行分析
- 需要完整监测+告警+报告 → 直接用 `run_log_check` 一步到位
- 需要定位具体报错在源文件第几行 → 用 `log_position_lookup`

## 输出风格
- 直接、简洁、不废话
- 关键结论前置（几条 critical、几条 warning、需不需要立即处理）
- 如有报告路径、推送结果，务必附上
"""

def check_llm_config() -> list[str]:
    """检查 LLM 配置是否完整（复用 FlowUs 相同逻辑）"""
    import os
    missing = []
    for k in ("LLM_MODEL_ID", "LLM_API_KEY", "LLM_BASE_URL"):
        if not os.getenv(k):
            missing.append(k)
    return missing


def create_log_monitor_agent(max_steps: int = 8) -> FlowUsAgent:
    """创建日志监控 Agent 实例（继承 FlowUsAgent）

    Args:
        max_steps: 最大推理步数（默认 8，日志分析通常需要多步）

    Returns:
        FlowUsAgent 实例，已注册日志监控工具集

    Raises:
        RuntimeError: 若 LLM 配置缺失
    """
    missing = check_llm_config()
    if missing:
        raise RuntimeError(
            f"LLM 配置缺失: {', '.join(missing)}。请检查项目的 .env 文件。"
        )

    llm = HelloAgentsLLM(temperature=0.3)
    registry = ToolRegistry()
    # 只注册日志监控相关工具（专注单一职责）
    registry.register_tool(LogReadAnomaliesTool())
    registry.register_tool(LogPositionLookupTool())
    registry.register_tool(RunLogCheckTool())
    registry.register_tool(LogPreviewTool())

    # 复用 FlowUsAgent 的配置（含智能摘要、历史注入、TraceLogger 修复）
    cfg = Config(
        context_window=32768,
        compression_threshold=0.7,
        min_retain_rounds=6,
        enable_smart_compression=True,
        summary_max_tokens=800,
        summary_temperature=0.3,
        auto_save_enabled=False,
        trace_enabled=True,
        trace_dir=str(__import__("week_agent.log_monitor.config", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT / "memory" / "traces"),
    )

    return FlowUsAgent(
        name="日志监控助手",
        llm=llm,
        tool_registry=registry,
        system_prompt=SYSTEM_PROMPT,
        config=cfg,
        max_steps=max_steps,
    )


def run_log_query(query: str, max_steps: int = 8, retries: int = 2) -> str:
    """便捷方法：创建日志监控 Agent 并运行一次查询（单次会话，无记忆保持）

    注意：此函数每次创建新 Agent，不保留历史。
    多轮对话场景请直接使用 create_log_monitor_agent() 获取持久实例。

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
            agent = create_log_monitor_agent(max_steps=max_steps)
            return agent.run(query)
        except (TypeError, RuntimeError) as e:
            last_error = e
            if attempt <= retries:
                print(f"⚠️ 第 {attempt} 次尝试失败（{e}），重试中...")
            else:
                raise
    raise last_error  # type: ignore[misc]