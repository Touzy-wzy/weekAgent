# -*- coding: utf-8 -*-
"""日志监控配置

借鉴 QwenPaw 的配置风格：模块级常量 + 环境变量可覆盖（LOG_MONITOR_* 前缀）。

支持 glob 模式自动发现日志文件，适用于：
- 实时产生的日志（应用运行中自动产生新文件）
- 定时任务场景（每次运行自动扫描最新文件）
"""

import glob as _glob
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# 项目根目录（week_agent 的上级）
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# 日志文件发现（glob 模式）
# ---------------------------------------------------------------------------
# 优先级：环境变量 > glob 模式 > 默认扫描
#
# 环境变量 LOG_MONITOR_GLOB 支持分号分隔多个 glob 模式，例如：
#   LOG_MONITOR_GLOB="app.log*;app1.log*;logs/*.log"
#
# 默认模式：扫描项目根目录下所有 .log 文件（含旋转日志 app.log.2026-07-21）
LOG_MONITOR_GLOB: str = os.getenv(
    "LOG_MONITOR_GLOB",
    "*.log",
)

# 默认扫描目录（glob 的根目录）
LOG_DIR: Path = Path(
    os.getenv("LOG_MONITOR_DIR", str(PROJECT_ROOT))
)


def resolve_log_files(
    glob_pattern: str | None = None,
    log_dir: Path | None = None,
    max_files: int = 20,
) -> List[Path]:
    """根据 glob 模式展开为实际的日志文件列表。

    特性：
    - 支持分号分隔多个 glob 模式（如 "app.log*;logs/*.log"）
    - 自动去重
    - 按修改时间倒序排列（最新的在前）
    - 过滤掉空文件和不存在的路径

    Args:
        glob_pattern: glob 模式字符串，None 则用 LOG_MONITOR_GLOB
        log_dir: 扫描根目录，None 则用 LOG_DIR
        max_files: 最多返回的文件数（防止目录爆炸）

    Returns:
        按修改时间倒序排列的 Path 列表
    """
    pattern = glob_pattern or LOG_MONITOR_GLOB
    base = log_dir or LOG_DIR

    # 支持分号分隔多个模式
    patterns = [p.strip() for p in pattern.split(";") if p.strip()]

    seen: set[str] = set()
    candidates: list[Path] = []

    for pat in patterns:
        # 如果模式是相对路径，拼上 base
        full_pattern = str(base / pat) if not Path(pat).is_absolute() else pat
        for match in _glob.glob(full_pattern):
            p = Path(match).resolve()
            if p.is_file() and str(p) not in seen:
                seen.add(str(p))
                candidates.append(p)

    # 按修改时间倒序（最新在前）
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return candidates[:max_files]


def list_log_files_as_text(
    glob_pattern: str | None = None,
    log_dir: Path | None = None,
    max_files: int = 20,
) -> str:
    """返回格式化的日志文件列表文本（供 LLM 阅读）。

    Returns:
        类似：
        共发现 3 个日志文件（按修改时间倒序）：
        1. app.log (2.3 MB, 2026-08-04 10:30)
        2. app1.log (156 KB, 2026-08-03 18:00)
        3. qwenpaw.log (45 KB, 2026-08-04 09:15)
    """
    files = resolve_log_files(glob_pattern, log_dir, max_files)
    if not files:
        return "未发现任何日志文件。"

    lines = [f"共发现 {len(files)} 个日志文件（按修改时间倒序）："]
    for i, p in enumerate(files, 1):
        size = p.stat().st_size
        mtime = p.stat().st_mtime
        from datetime import datetime
        mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

        # 人类可读的大小
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.0f} KB"
        else:
            size_str = f"{size} B"

        lines.append(f"{i}. {p.name} ({size_str}, {mtime_str})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 关注的日志级别（只要 WARNING 及以上 / ERROR）
# ---------------------------------------------------------------------------
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
ALERT_CHANNELS: list[str] = [
    c.strip()
    for c in os.getenv("LOG_ALERT_CHANNELS", "console,mail,wecom").split(",")
    if c.strip()
]

ALERT_MIN_SEVERITY: str = os.getenv("LOG_MONITOR_MIN_SEVERITY", "warning")

# 邮件渠道
MAIL_TO: str = os.getenv("LOG_ALERT_MAIL_TO", "wangzhaoyang@ieslab.cn")
MAIL_FREQUENCY: str = os.getenv("LOG_ALERT_MAIL_FREQUENCY", "daily")

# 企业微信 webhook 渠道
WECOM_WEBHOOK_URL: str = os.getenv(
    "LOG_ALERT_WECOM_WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=51177e5e-9135-4bbb-a20e-7db400762748",
)
WECOM_MIN_SEVERITY: str = os.getenv("LOG_ALERT_WECOM_MIN_SEVERITY", "critical")

# 报告 / 告警落盘目录
REPORT_DIR: Path = Path(
    os.getenv("LOG_MONITOR_REPORT_DIR", str(PROJECT_ROOT / "reports"))
)

# ---------------------------------------------------------------------------
# 向后兼容：LOG_FILES 列表（由 resolve_log_files 动态生成）
# ---------------------------------------------------------------------------
LOG_FILES: list[str] = [str(p) for p in resolve_log_files()]
