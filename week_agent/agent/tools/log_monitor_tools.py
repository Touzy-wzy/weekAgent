# -*- coding: utf-8 -*-
"""日志监控工具集（hello-agents Tool）

将现有的 week_agent.log_monitor 能力封装为 Agent 可调用的工具。
复用 FlowUsAgent 的 ReAct 循环与多轮记忆能力。
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.errors import ToolErrorCode
from hello_agents.tools.response import ToolResponse

# 复用现有 log_monitor 模块（保留所有底层逻辑：解析、告警、报告、位置索引）
from week_agent.log_monitor import config as _lm_config
from week_agent.log_monitor.log_parser import parse_all, location_manifest, extract_watch_records
from week_agent.log_monitor.agent import run_log_check as _run_log_check
from week_agent.log_monitor.alerter import format_alert_payload, dispatch_channels


class LogReadAnomaliesTool(Tool):
    """读取日志文件并提取 WARNING/ERROR 级别的异常记录"""

    def __init__(self):
        super().__init__(
            name="log_read_anomalies",
            description=(
                "读取本地监控日志文件，提取 WARNING 和 ERROR 级别的异常记录。"
                "返回每条记录的时间戳、级别、模块、消息正文（自动聚合多行续行、"
                "自动规避超长消息）。用于日志异常分析与告警判断。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filepath",
                type="string",
                description=(
                    "可选的日志文件路径。不填则读取全部默认监控文件。"
                    "可用 ; 分隔多个文件。"
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="max_records",
                type="integer",
                description="每个文件最多返回的异常记录条数（默认 60，取最新）",
                required=False,
                default=_lm_config.MAX_ANALYZE_RECORDS,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        filepath = str(parameters.get("filepath") or "").strip()
        max_records = int(parameters.get("max_records") or _lm_config.MAX_ANALYZE_RECORDS)

        if filepath and ";" in filepath:
            files = [f.strip() for f in filepath.split(";") if f.strip()]
        elif filepath:
            files = [filepath]
        else:
            files = list(_lm_config.LOG_FILES)

        print(f"📄 [log_read_anomalies] files={files} max={max_records}")
        try:
            sections: list[str] = []
            total = 0
            for fp in files:
                path = Path(fp)
                if not path.exists():
                    sections.append(f"[缺失] {fp}：文件不存在")
                    continue
                recs = extract_watch_records(fp, max_records=max_records)
                total += len(recs)
                if not recs:
                    sections.append(f"[{fp}] 无 WARNING/ERROR 记录")
                    continue
                body = "\n".join(r.truncated for r in recs)
                sections.append(f"===== {fp}（{len(recs)} 条）=====\n{body}")

            text = "\n\n".join(sections)
            if not text:
                text = "未读取到任何异常日志记录。"
            text = f"共提取 {total} 条 WARNING/ERROR 异常记录：\n\n{text}"

            # 附一行位置索引，便于 LLM / 调试定位
            pos_lines = []
            for fp in files:
                path = Path(fp)
                if not path.exists():
                    continue
                recs = extract_watch_records(fp, max_records=max_records)
                for r in recs:
                    span = (
                        f"{r.start_line}"
                        if r.start_line == r.end_line
                        else f"{r.start_line}-{r.end_line}"
                    )
                    pos_lines.append(f"    {Path(fp).name}: 行 {span} | {r.level} | {r.module}")
            if pos_lines:
                text += "\n\n[位置索引]\n" + "\n".join(pos_lines)

            print(f"  ✅ 提取 {total} 条异常记录")
            return ToolResponse.success(
                text=text,
                data={"files": files, "total_records": total},
            )
        except Exception as e:
            print(f"  ❌ 读取日志失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"读取日志失败: {str(e)}",
                context={"filepath": filepath, "files": files},
            )


class LogPositionLookupTool(Tool):
    """查询某条日志在源文件中的行号区间（用于定位源码/排查）"""

    def __init__(self):
        super().__init__(
            name="log_position_lookup",
            description=(
                "给定日志文件路径和关键字（或时间戳/级别/模块），返回匹配记录在原始文件中的起止行号。"
                "多行 traceback 会聚合为一条记录，输出首尾行号即为长日志的开始/结束位置。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filepath",
                type="string",
                description="日志文件路径",
                required=True,
            ),
            ToolParameter(
                name="keyword",
                type="string",
                description="要查找的关键字（支持级别/模块/消息片段/时间戳）",
                required=True,
            ),
            ToolParameter(
                name="max_matches",
                type="integer",
                description="最多返回多少条匹配（默认 10）",
                required=False,
                default=10,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        filepath = str(parameters.get("filepath") or "").strip()
        keyword = str(parameters.get("keyword") or "").strip().lower()
        max_matches = int(parameters.get("max_matches") or 10)

        if not filepath or not keyword:
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="filepath 和 keyword 都不能为空",
            )

        path = Path(filepath)
        if not path.exists():
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message=f"日志文件不存在: {filepath}",
            )

        try:
            by_file = parse_all(files=[filepath], watch_levels={"WARNING", "ERROR", "INFO", "DEBUG"})
            recs = by_file.get(filepath, [])
            kw = keyword.lower()
            matches = []
            for r in recs:
                hay = f"{r.level} {r.module} {r.message} {r.timestamp}".lower()
                if kw in hay:
                    matches.append(r)
                    if len(matches) >= max_matches:
                        break

            if not matches:
                return ToolResponse.success(
                    text=f"在 {filepath} 中未找到包含关键字 '{keyword}' 的记录",
                    data={"matches": []},
                )

            lines = [f"在 {filepath} 中找到 {len(matches)} 条匹配记录（显示行区间）："]
            for r in matches:
                span = (
                    f"{r.start_line}"
                    if r.start_line == r.end_line
                    else f"{r.start_line}-{r.end_line}"
                )
                head = r.message.strip().splitlines()[0][:80] if r.message else ""
                lines.append(f"  行 {span} | {r.level} | {r.module} | {head}")

            return ToolResponse.success(
                text="\n".join(lines),
                data={
                    "file": filepath,
                    "keyword": keyword,
                    "matches": [
                        {
                            "start_line": r.start_line,
                            "end_line": r.end_line,
                            "level": r.level,
                            "module": r.module,
                            "timestamp": r.timestamp,
                            "message_preview": r.message[:200],
                        }
                        for r in matches
                    ],
                },
            )
        except Exception as e:
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"位置查询失败: {str(e)}",
                context={"filepath": filepath, "keyword": keyword},
            )


class RunLogCheckTool(Tool):
    """触发一次完整的日志检查与告警（解析 → LLM 分析 → 多渠道推送 → 报告落盘）"""

    def __init__(self):
        super().__init__(
            name="run_log_check",
            description=(
                "执行一次完整的日志监控检查："
                "1) 读取所有监控文件中的 WARNING/ERROR 异常记录\n"
                "2) LLM 语义分析：判断异常类型、严重级别、影响面、处置建议\n"
                "3) 多渠道告警推送（控制台 + 邮件每日汇总 + 企业微信 critical 实时）\n"
                "4) 生成带位置索引的 Markdown 报告落盘到 reports/\n\n"
                "返回：分析结论 + 报告文件路径 + 各渠道推送结果。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="max_steps",
                type="integer",
                description="Agent 最大推理步数（默认 8）",
                required=False,
                default=8,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        max_steps = int(parameters.get("max_steps") or 8)
        print(f"[run_log_check] 开始完整日志检查，max_steps={max_steps}")

        try:
            # 复用现有完整流程（包含解析、LLM 分析、告警、落盘）
            result = _run_log_check(max_steps=max_steps)

            # 找到最新生成的报告路径（报告落盘在 save_report 内部）
            # run_log_check 内部已经打印了报告路径，这里再找一次返回
            import glob
            report_files = sorted(
                glob.glob(str(_lm_config.REPORT_DIR / "log_alert_*.md")),
                key=lambda p: Path(p).stat().st_mtime,
            )
            latest_report = report_files[-1] if report_files else None

            text = (
                f"✅ 完整日志检查完成\n\n"
                f"【分析结论】\n{result}\n\n"
                f"【报告文件】\n{latest_report or '未找到'}"
            )
            return ToolResponse.success(
                text=text,
                data={
                    "analysis": result,
                    "report_path": latest_report,
                },
            )
        except Exception as e:
            print(f"  ❌ 完整日志检查失败: {e}")
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"完整日志检查失败: {str(e)}",
            )


class LogPreviewTool(Tool):
    """仅预览异常记录（不调用 LLM，快速统计）"""

    def __init__(self):
        super().__init__(
            name="log_preview",
            description=(
                "快速预览监控日志文件中的 WARNING/ERROR 记录，不调用 LLM，不发送告警，不生成报告。"
                "适合快速确认当前异常分布。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="limit",
                type="integer",
                description="每个文件最多显示的异常记录条数（默认 5）",
                required=False,
                default=5,
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        limit = int(parameters.get("limit") or 5)
        try:
            by_file = parse_all()
            total = sum(len(r) for r in by_file.values())
            err = sum(1 for r in by_file.values() for x in r if x.level == "ERROR")

            lines = [
                "=" * 60,
                "日志监控 Agent - 预览模式",
                "=" * 60,
            ]
            for fp, recs in by_file.items():
                from pathlib import Path
                lines.append(f"  {Path(fp).name}: {len(recs)} 条异常 (ERROR {sum(1 for r in recs if r.level=='ERROR')})")
            lines.append(f"  合计: {total} 条（WARNING + ERROR）\n")

            for fp, recs in by_file.items():
                from pathlib import Path
                lines.append(f"\n===== {Path(fp).name} =====")
                for r in recs[:limit]:
                    span = f"{r.start_line}" if r.start_line == r.end_line else f"{r.start_line}-{r.end_line}"
                    lines.append(f"  [{r.level}] {r.timestamp} | {r.module} | 行 {span} | {r.message[:100]}")

            lines.append("\n预览完成（未调用 LLM，未告警，未生成报告）。")
            return ToolResponse.success(
                text="\n".join(lines),
                data={"by_file": {fp: len(r) for fp, r in by_file.items()}, "total": total, "error": err},
            )
        except Exception as e:
            return ToolResponse.error(
                code=ToolErrorCode.EXECUTION_ERROR,
                message=f"预览失败: {str(e)}",
            )