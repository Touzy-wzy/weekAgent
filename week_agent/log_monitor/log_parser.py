# -*- coding: utf-8 -*-
"""日志解析器

解析格式：
    YYYY-MM-DD HH:MM:SS,mmm | LEVEL | module | message
      continuation line 1      ← 缩进开头的行是上一条消息的续行
      continuation line 2

关键点：
1. 日志可能有多行续行结构，按"时间戳开头"聚合为一条完整记录。
2. 只提取配置的关注级别（WARNING / ERROR）。
3. 关注级别之外的记录直接丢弃，避免把几千条 INFO 塞进 LLM（借鉴 QwenPaw
   "先粗筛再语义分析" 的成本控制思路）。
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config

# 记录行首：时间戳 | 级别 | 模块 | 消息
# 时间: 2026-07-21 08:44:55,240
_RECORD_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+) \| (.+)$'
)


@dataclass
class LogRecord:
    """一条日志记录"""

    timestamp: str      # 2026-07-21 08:44:55,240
    level: str          # INFO / WARNING / ERROR / ...
    module: str         # app.api.public_api
    message: str = ""     # 聚合后的消息正文（含续行）
    raw_lines: list[str] = field(default_factory=list)  # 原始行（便于展示）
    # 该记录在日志文件中的位置（1-based 行号，含续行）
    # 多行记录 start_line .. end_line 即为"长篇幅日志的开始/结束位置"
    start_line: int = 0
    end_line: int = 0

    @property
    def text(self) -> str:
        """紧凑单行文本（内部使用）"""
        return f"{self.timestamp} | {self.level} | {self.module} | {self.message}"

    @property
    def truncated(self) -> str:
        """给 LLM 看的截断文本（防上下文爆炸）"""
        body = self.message
        if len(body) > config.MAX_RECORD_CHARS:
            body = body[: config.MAX_RECORD_CHARS] + f" ...(截断, 原文 {len(self.message)} 字符)"
        return f"{self.timestamp} | {self.level} | {self.module} | {body}"


def _decode(path: Path) -> str:
    """按候选编码读取文件，返回解码后的文本"""
    last_err: Exception | None = None
    for enc in config.LOG_ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError) as e:
            last_err = e
    raise ValueError(f"无法解码日志文件 {path}: {last_err}")


def parse_file(file_path: str, watch_levels: set[str] | None = None) -> list[LogRecord]:
    """解析单个日志文件，返回全部结构化记录（未按级别过滤）

    Args:
        file_path: 日志文件路径
        watch_levels: 仅返回这些级别的记录；None 表示全部返回

    Returns:
        按时间先后排序的 LogRecord 列表
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"日志文件不存在: {path}")

    text = _decode(path)
    watch = watch_levels if watch_levels is not None else config.WATCH_LEVELS

    records: list[LogRecord] = []
    cur: LogRecord | None = None

    for lineno, line in enumerate(text.splitlines(), start=1):
        # 空行跳过（但仍占用行号）
        if not line.strip():
            continue
        m = _RECORD_RE.match(line)
        if m:
            # 新记录开始
            if cur is not None:
                records.append(cur)
            # group(3) 捕获到 "module | message"（消息里可能还有 | 分隔的字段）
            rest = m.group(3)
            if " | " in rest:
                module, _, message = rest.partition(" | ")
            else:
                module, message = rest, ""
            cur = LogRecord(
                timestamp=m.group(1),
                level=m.group(2),
                module=module.strip(),
                message=message.strip(),
                raw_lines=[line],
                start_line=lineno,
                end_line=lineno,
            )
        else:
            # 续行：挂到当前记录（若存在），扩展结束行号
            if cur is not None:
                cur.raw_lines.append(line)
                cur.end_line = lineno
                cur.message += "\n" + line

    if cur is not None:
        records.append(cur)

    if watch is None:
        return records
    return [r for r in records if r.level in watch]


def parse_all(files: list[str] | None = None, watch_levels: set[str] | None = None) -> dict[str, list[LogRecord]]:
    """解析多个文件，返回 {文件路径: 关注级别的记录列表}"""
    files = files or config.LOG_FILES
    result: dict[str, list[LogRecord]] = {}
    for fp in files:
        result[fp] = parse_file(fp, watch_levels)
    return result


def count_stat(records: list[LogRecord]) -> dict[str, int]:
    """统计记录按级别分布"""
    from collections import Counter

    return dict(Counter(r.level for r in records))


def summarize(by_file: dict[str, list[LogRecord]]) -> str:
    """把按文件组织的结果转成概览文本（供 LLM / 用户阅读）"""
    lines: list[str] = []
    for fp, recs in by_file.items():
        lines.append(f"文件: {fp}")
        lines.append(f"  异常记录数: {len(recs)}  分布: {count_stat(recs)}")
    return "\n".join(lines)


def location_manifest(by_file: dict[str, list[LogRecord]], max_msg: int = 80) -> str:
    """生成「异常位置索引」文本：每条记录的行号区间（长日志只记起止行）。

    供写入报告 / 观察信息使用。返回 Markdown 风格文本：
        - 文件: xxx
          - 行 12-35 | ERROR | module | 摘要
    """
    lines: list[str] = []
    for fp, recs in by_file.items():
        lines.append(f"- 文件: {fp}")
        if not recs:
            lines.append(f"  - （无异常）")
            continue
        for r in recs:
            span = f"{r.start_line}" if r.start_line == r.end_line else f"{r.start_line}-{r.end_line}"
            head = r.message.strip().splitlines()
            head = head[0] if head else ""
            if len(head) > max_msg:
                head = head[:max_msg] + "…"
            lines.append(f"  - 行 {span} | {r.level} | {r.module} | {head}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 给工具 / agent 使用的便捷函数
# ---------------------------------------------------------------------------
def extract_watch_records(filepath: str, max_records: int | None = None) -> list[LogRecord]:
    """读取文件并仅返回关注级别的记录（供 LogReadTool 使用）

    Args:
        filepath: 日志文件路径
        max_records: 最多返回多少条（超出截断，控制 LLM 输入）
    """
    recs = parse_file(filepath, watch_levels=config.WATCH_LEVELS)
    if max_records is None:
        max_records = config.MAX_ANALYZE_RECORDS
    if len(recs) > max_records:
        # 保留最近的 max_records 条（时间最新）
        recs = recs[-max_records:]
    return recs