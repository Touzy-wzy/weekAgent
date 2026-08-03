# -*- coding: utf-8 -*-
"""日志监控配置

借鉴 QwenPaw 的配置风格：模块级常量 + 环境变量可覆盖（LOG_MONITOR_* 前缀）。
目前阶段只做控制台跑通 + 单次批处理，不做常驻调度。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（week_agent 的上级）
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# 要监控的日志文件（默认：用户指定的两个文件）
# ---------------------------------------------------------------------------
LOG_FILES: list[str] = [
    os.getenv("LOG_MONITOR_FILE_1", str(PROJECT_ROOT / "app.log.2026-07-21")),
    os.getenv("LOG_MONITOR_FILE_2", str(PROJECT_ROOT / "app.log")),
]

# 关注的日志级别（只要 WARNING 及以上 / ERROR）
# 排除了 INFO / DEBUG
WATCH_LEVELS: set[str] = {"WARNING", "ERROR"}

# 日志文件编码（实测为 UTF-8，可用 "; " 分隔多个候选）
LOG_ENCODINGS: list[str] = ["utf-8", "gbk"]

# ---------------------------------------------------------------------------
# 分析相关
# ---------------------------------------------------------------------------
# 单条记录允许进入 LLM 的最大字符数（超长截断，防上下文爆炸）
MAX_RECORD_CHARS: int = 2000
# 单次分析最多送入 LLM 的记录数
MAX_ANALYZE_RECORDS: int = 60

# ---------------------------------------------------------------------------
# 告警（多渠道：控制台 + 邮件 + 企业微信 webhook）
# ---------------------------------------------------------------------------
# 启用的告警渠道（逗号分隔），至少包含 console
# 可用: console / mail / wecom
ALERT_CHANNELS: list[str] = [
    c.strip()
    for c in os.getenv("LOG_ALERT_CHANNELS", "console,mail,wecom").split(",")
    if c.strip()
]

# 告警最小级别：只推送 severity 不低于此值的结果
ALERT_MIN_SEVERITY: str = os.getenv("LOG_MONITOR_MIN_SEVERITY", "warning")  # info/warning/critical

# 邮件渠道
# 收件人（逗号分隔）
MAIL_TO: str = os.getenv("LOG_ALERT_MAIL_TO", "wangzhaoyang@ieslab.cn")
# 邮件汇总频率: daily=每天只发一封汇总（默认）；also支持 single=每次运行都发
MAIL_FREQUENCY: str = os.getenv("LOG_ALERT_MAIL_FREQUENCY", "daily")

# 企业微信 webhook 渠道
# webhook 地址（敏感，放 .env）
WECOM_WEBHOOK_URL: str = os.getenv(
    "LOG_ALERT_WECOM_WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=51177e5e-9135-4bbb-a20e-7db400762748",
)
# webhook 只推不低于此级别的异常（每条 critical 实时推）
WECOM_MIN_SEVERITY: str = os.getenv("LOG_ALERT_WECOM_MIN_SEVERITY", "critical")

# 报告 / 告警落盘目录（每次运行生成一个带时间戳的 Markdown 文件）
REPORT_DIR: Path = Path(
    os.getenv("LOG_MONITOR_REPORT_DIR", str(PROJECT_ROOT / "reports"))
)