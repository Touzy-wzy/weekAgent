# -*- coding: utf-8 -*-
"""LogAgent - 日志监控智能体（基于 hello-agents ReActAgent）

借鉴 QwenPaw 的实现方式：Agent 持有工具（Toolkit），通过 ReAct 循环由
LLM 自主决策调用工具、进行语义级异常判断，最终产出告警。
与现有 FlowUsAgent 同框架（hello-agents），结构一致、可复用 Runner 模式。

当前阶段能力（路线 A，控制台单次跑通）：
1. 读取本地日志文件并提取 WARNING/ERROR 异常记录（log_read_anomalies 工具）
2. LLM 对异常记录做语义级判断：是否真异常、严重级别、异常类型、处置建议
3. 告警按需发送（当前为控制台）
"""

import json
import os
from datetime import datetime
from pathlib import Path

from hello_agents.agents.react_agent import ReActAgent
from hello_agents.core.config import Config
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.tools.registry import ToolRegistry

from . import config as _config
from .alerter import format_alert_payload
from .tools import LogReadTool
from .log_parser import location_manifest, parse_all

# 日志分析 agent 的系统提示词
SYSTEM_PROMPT = """你是一个日志监控分析助手，负责读取本地日志文件中的 WARNING / ERROR 异常记录，
进行语义级判断，并输出告警建议。

## 可用工具

1. **log_read_anomalies**：读取日志文件并提取 WARNING / ERROR 级别的异常记录
   - 参数 filepath：可选，不填则读取全部默认监控文件；可用 `;` 分隔多个文件
   - 返回：每条记录的时间戳、级别、模块、消息正文

## 工作流程

1. **读取**：调用 `log_read_anomalies` 提取异常记录（默认先读全部文件）
2. **分析**：对每条（或每类）异常记录做语义判断，重点识别：
   - 是什么错误类型（业务错误 / 运行时异常 / 网络失败 / 鉴权失败 / 数据问题等）
   - 严重程度：critical（致命/需立即处理） / warning（需要关注） / info（提示）
   - 影响面：是否影响核心功能
   - 处置建议：如何排查 / 修复
3. **汇总**：给出结论——本次共发现哪些问题、各自严重级别、是否需要告警。

## 输出格式（最终回答）

请用如下结构化格式输出，便于直接作为告警内容：

```
【日志分析报告】
分析时间
共发现 N 个异常（WARNING X 个，ERROR Y 个）

── 异常 1 [级别: critical/warning/info]
现象: ...
影响: ...
建议: ...

── 异常 2 ...

【告警建议】
需要立即告警: 是/否
```

## 原则
- 只基于日志内容判断，不要臆造；信息不足时明确说明
- 相同/重复异常应合并，不要把同一时间反复出现的同一错误当多个异常
- 关注真正影响系统的 ERROR 和值得警惕的 WARNING，普通业务日志说明即可
"""


class LogAlertAgent(ReActAgent):
    """日志分析与告警智能体"""

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        tool_registry: ToolRegistry | None = None,
        system_prompt: str | None = None,
        config: Config | None = None,
        max_steps: int = 6,
    ):
        registry = tool_registry or ToolRegistry()
        registry.register_tool(LogReadTool())
        super().__init__(
            name=name,
            llm=llm,
            tool_registry=registry,
            system_prompt=system_prompt or SYSTEM_PROMPT,
            config=config,
            max_steps=max_steps,
        )


def check_llm_config() -> list[str]:
    """检查 LLM 配置是否完整（与 FlowUs runner 一致）"""
    missing = []
    for k in ("LLM_MODEL_ID", "LLM_API_KEY", "LLM_BASE_URL"):
        if not os.getenv(k):
            missing.append(k)
    return missing


def create_log_agent(max_steps: int = 6) -> LogAlertAgent:
    """创建日志分析 Agent 实例

    Raises:
        RuntimeError: 若 LLM 配置缺失
    """
    missing = check_llm_config()
    if missing:
        raise RuntimeError(
            f"LLM 配置缺失: {', '.join(missing)}。请检查项目的 .env 文件。"
        )
    llm = HelloAgentsLLM(temperature=0.3)
    # 复用项目调试/输出目录
    cfg = Config(trace_dir=str(_config.PROJECT_ROOT / "memory" / "traces"))
    return LogAlertAgent(
        name="日志分析助手",
        llm=llm,
        config=cfg,
        max_steps=max_steps,
    )


def save_report(result: str, total: int, err: int, manifest: str = "") -> Path:
    """把完整的分析报告/告警落盘为带时间戳的 Markdown 文件。

    Args:
        result: LLM 分析结论文本
        total: 异常总数
        err: ERROR 数
        manifest: 异常位置索引文本（追加在报告末尾）

    Returns:
        生成的报告文件路径
    """
    _config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _config.REPORT_DIR / f"log_alert_{stamp}.md"
    header = (
        "# 日志监控分析报告\n\n"
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 异常总量: {total}（WARNING{total - err}，ERROR {err}）\n\n"
        "---\n\n"
    )
    body = header + result
    if manifest:
        body += (
            "\n\n---\n\n## 附：异常位置索引\n"
            "（多行/长篇幅日志仅记录起止行号）\n\n"
            + manifest
            + "\n"
        )
    path.write_text(body, encoding="utf-8")
    return path


def run_log_check(max_steps: int = 6, silent_summary: bool = False) -> str:
    """执行一次日志检查（单次批处理）

    流程：读取异常记录 → 交给 agent 语义分析 → 构造告警 → 控制台输出 + 落盘

    Returns:
        agent 的分析结论文本
    """
    now = datetime.now()
    # 先做一次快速统计（供最终告警摘要使用）
    by_file = parse_all()
    total = sum(len(r) for r in by_file.values())
    err = sum(1 for r in by_file.values() for x in r if x.level == "ERROR")

    agent = create_log_agent(max_steps=max_steps)
    query = (
        f"当前系统时间: {now.strftime('%Y-%m-%d %H:%M:%S')}。\n"
        f"请读取全部监控日志文件中的 WARNING / ERROR 异常记录并分析。"
        f"（当前共 {total} 条异常记录，其中 ERROR {err} 条）"
        f"请判断哪些是真正的异常、严重级别，并给出处置建议与告警结论。"
        f"报告中的\"分析时间\"请使用我给出的当前系统时间，不要自行编造。"
    )
    result = agent.run(query)

    # 构造统一告警数据结构（time 由 format_alert_payload 自动填当前时间）
    severity = "critical" if err > 0 else "warning"
    if total == 0:
        severity = "info"
    summary = f"共发现 {total} 条日志异常（ERROR {err} 条）。"
    alert = format_alert_payload(
        severity=severity,
        title=("日志异常告警" if total else "日志检查完成（无异常）"),
        summary=summary,
        body=result,
    )

    # 落盘报告：追加异常位置索引（机器读取，不依赖 LLM）
    manifest = location_manifest(by_file)
    path = save_report(result, total, err, manifest=manifest)
    print(f"\n📄 报告已落盘: {path}")
    alert["report_path"] = str(path)

    # 多渠道分发（console + mail + wecom），每个渠道独立降级
    from .alerter import dispatch_channels

    results = dispatch_channels(alert)
    print("[渠道推送汇总]", {k: ("✅" if v else "❌") for k, v in results.items()})
    return result