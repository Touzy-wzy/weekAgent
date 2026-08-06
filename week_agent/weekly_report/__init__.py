"""周报智能体模块 - 基于 hello-agents 二次开发

注意：Web 端的周报会话状态机（session.py）已移除，周报流程现由通用 Agent 对话驱动。
本模块保留模板、Excel 填写、docx 解析等被工具调用的能力。

`create_weekly_agent` / `run_weekly_query` 不在此处 eager 导入，
因其依赖 `week_agent.agent.tools.fill_excel_tool`，会与该工具模块形成循环导入。
需要时请直接 `from week_agent.weekly_report.agent import create_weekly_agent`。
"""

from .templates import (
    WEEKLY_TEMPLATE_PATH,
    WEEKLY_REPORT_SCHEMA,
    CATEGORY_ENUM,
    THIS_WEEK_STATUS_ENUM,
    NEXT_WEEK_STATUS_ENUM,
)
from .excel_filler import fill_weekly_report
from .doc_parser import parse_docx_to_text

__all__ = [
    "WEEKLY_TEMPLATE_PATH",
    "WEEKLY_REPORT_SCHEMA",
    "CATEGORY_ENUM",
    "THIS_WEEK_STATUS_ENUM",
    "NEXT_WEEK_STATUS_ENUM",
    "fill_weekly_report",
    "parse_docx_to_text",
]


def __getattr__(name):
    """惰性导入 create_weekly_agent / run_weekly_query，避免循环导入"""
    if name in ("create_weekly_agent", "run_weekly_query"):
        from week_agent.weekly_report.agent import create_weekly_agent, run_weekly_query
        return {"create_weekly_agent": create_weekly_agent, "run_weekly_query": run_weekly_query}[name]
    raise AttributeError(f"module 'week_agent.weekly_report' has no attribute {name!r}")

