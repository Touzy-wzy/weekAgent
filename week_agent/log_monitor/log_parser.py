# -*- coding: utf-8 -*-
"""日志解析器（P0：多格式自适应）

之前只认固定管道格式 `时间戳|级别|模块|消息`（且强制毫秒位），遇到
`qwenpaw.log`（无毫秒）就整文件解析失败。本次 P0 引入三层分层能力，同时
保持对外接口（``LogRecord`` / ``parse_file`` / ``parse_all`` /
``extract_watch_records`` 等）完全不变：

    1. FormatDetector —— 采样若干行，评估各解析器的命中率，自动选最优；
    2. 多解析器注册表 PARSERS —— pipeline / python_logger / syslog / jsonl；
    3. 级别归一化 LEVEL_ALIASES —— 不同格式的 error/warn/severe/fatal 等统一为标准；
    4. fallback —— 未知格式降级为"整行一条记录 + 级别关键词猜测"。

解析逻辑统一：以"新记录首行"判断是否开启新记录，其余挂为续行（多行 traceback
自动聚合）。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config

# 保留旧的正则名，避免破坏外部 import（内部已由解析器注册表接管）。
_RECORD_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+) \| (.+)$'
)

# 通用 ISO 时间戳：毫秒可选（pipeline / python logging / JSON 等）
_TIMESTAMP_ISO = r'\d{4}[-\/]\d{1,2}[-\/]\d{1,2}[ T]\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,6})?'
# 系统日志时间戳：Jul 21 08:44:55
_TIMESTAMP_SYSLOG = r'[A-Z][a-z]{2}\s+\d{1,2}\s+\d{1,2}:\d{2}:\d{2}'


# ---------------------------------------------------------------------------
# 级别归一化
# ---------------------------------------------------------------------------
LEVEL_ALIASES = {
    # error 族
    "error": "ERROR", "err": "ERROR", "failure": "ERROR", "fail": "ERROR",
    "failed": "ERROR", "severe": "ERROR", "fatal": "ERROR", "critical": "ERROR",
    "panic": "ERROR", "alert": "ERROR", "emergency": "ERROR", "emerg": "ERROR",
    # warning 族
    "warn": "WARNING", "warning": "WARNING",
    # info 族
    "info": "INFO", "informational": "INFO", "notice": "INFO",
    # debug 族
    "debug": "DEBUG", "dbug": "DEBUG", "trace": "DEBUG", "verbose": "DEBUG",
}

STD_LEVELS = {"INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL"}


def normalize_level(raw: str) -> str:
    """把任意原始级别词归一为标准级别（INFO/WARNING/ERROR/DEBUG/CRITICAL）。"""
    key = re.sub(r'[\s_\-()\[\]\/]+', '', (raw or "")).lower()
    if key in LEVEL_ALIASES:
        return LEVEL_ALIASES[key]
    if (raw or "").strip().upper() in STD_LEVELS:
        return raw.strip().upper()
    head = (raw or "").strip().upper()[:1]
    if head in ("E", "F"):
        return "ERROR"
    if head == "W":
        return "WARNING"
    if head == "D":
        return "DEBUG"
    return "INFO"


# ---------------------------------------------------------------------------
# 日志记录模型（与旧版字段一致，仅追加 level_raw 便于溯源）
# ---------------------------------------------------------------------------
@dataclass
class LogRecord:
    """一条日志记录"""

    timestamp: str      # 2026-07-21 08:44:55,240
    level: str          # 归一化后的级别 INFO / WARNING / ERROR / ...
    module: str         # app.api.public_api
    message: str = ""     # 聚合后的消息正文（含续行）
    raw_lines: list[str] = field(default_factory=list)  # 原始行（便于展示）
    # 该记录在日志文件中的位置（1-based 行号，含续行）
    start_line: int = 0
    end_line: int = 0
    level_raw: str = ""    # 原始级别词（未归一化前，便于检索 / 溯源）

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


# ---------------------------------------------------------------------------
# 解析器注册表
# ---------------------------------------------------------------------------
class Parser:
    def __init__(self, name, detect, parse):
        self.name = name
        self.detect = detect      # line -> bool      是否像该格式的首行
        self.parse = parse        # line -> tuple|None (timestamp, level_raw, module, message)


def _parse_pipeline(line):
    # 时间戳 | LEVEL | module | message
    m = re.match(rf'^({_TIMESTAMP_ISO}) \| ([A-Za-z_]+) \| (.+)$', line)
    if not m:
        return None
    ts, level, rest = m.group(1), m.group(2), m.group(3)
    module, _, message = rest.partition(" | ")
    return ts, level, module.strip(), message.strip()


def _detect_pipeline(line):
    return bool(re.match(rf'^{_TIMESTAMP_ISO} \| [A-Za-z_]', line))


def _parse_python_logger(line):
    # standard python logging:  time - name - LEVEL - message
    m = re.match(rf'^({_TIMESTAMP_ISO}) - ([^|-]+?) - ([A-Za-z_]+?) - (.*)$', line)
    if not m:
        return None
    ts, module, level, message = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
    return ts, level, module, message.strip()


def _detect_python_logger(line):
    return re.match(rf'^{_TIMESTAMP_ISO} - ', line) is not None


def _parse_syslog(line):
    # Jul 21 21:23:11 host app[pid]: msg
    m = re.match(rf'^({_TIMESTAMP_SYSLOG})\s+(\S+)\s+([\w./-]+\[?[^:]*\]?): (.*)$', line)
    if not m:
        return None
    ts, host, tag, message = m.group(1), m.group(2), m.group(3), m.group(4)
    return ts, "INFO", f"{host} {tag}".strip(), message.strip()


def _detect_syslog(line):
    return re.match(rf'^{_TIMESTAMP_SYSLOG}\s+', line) is not None


def _parse_jsonl(line):
    # 单行 JSON；字段名兼容常见命名，不限定大小写。
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    ts = (obj.get('ts') or obj.get('time') or obj.get('timestamp') or obj.get('datetime') or "")
    message = (obj.get('msg') or obj.get('message') or "")
    level = (obj.get('lvl') or obj.get('level') or obj.get('levelname') or 'info')
    module = obj.get('logger') or obj.get('module') or obj.get('source') or ""
    ts, module, message = str(ts).strip(), str(module).strip(), str(message).strip()
    if not ts and not module and not message:
        return None
    return ts, level, module, message


def _detect_jsonl(line):
    s = line.lstrip()
    return s[:1] in ("{", "[")


PARSERS = [
    Parser("pipeline", _detect_pipeline, _parse_pipeline),
    Parser("python_logger", _detect_python_logger, _parse_python_logger),
    Parser("syslog", _detect_syslog, _parse_syslog),
    Parser("jsonl", _detect_jsonl, _parse_jsonl),
]

_DEFAULT_PARSER = PARSERS[0]


def _fallback_parse(line):
    """兜底：每行一条记录，级别从行内关键词猜测。"""
    ts = ""
    m = re.search(_TIMESTAMP_ISO, line)
    if not m:
        m = re.search(_TIMESTAMP_SYSLOG, line)
    ts = m.group(0) if m else ""
    low = line.lower()
    level = "INFO"
    if any(w in low for w in ("fatal", "critical", "panic", "severe", "exception",
                              "traceback", "error")):
        level = "ERROR"
    elif any(w in low for w in ("warn", "fail", "failed")):
        level = "WARNING"
    elif any(w in low for w in ("debug", "trace")):
        level = "DEBUG"
    return ts, level, "", line.strip()


# ---------------------------------------------------------------------------
# 格式探测
# ---------------------------------------------------------------------------
_DETECT_SAMPLE_LINES = 50
DETECT_THRESHOLD = 0.5   # 命中率阈值（> 才选它；否则 fallback）


def detect_format(lines: list[str]) -> str:
    """从若干行采样中评估各格式命中率，返回获胜 parser 名；否则返回 ''。"""
    # 只取以年份数字开头的行，排除缩进续行和纯文本续行
    support_lines = [l for l in lines if l.strip() and re.match(r'^\d{4}', l)]
    if not support_lines:
        return ""
    n = min(len(support_lines), _DETECT_SAMPLE_LINES)
    scores = {}
    for p in PARSERS:
        ok = sum(1 for l in support_lines[:n] if p.detect(l))
        scores[p.name] = ok / n
    best = max(scores, key=scores.get)
    if scores[best] >= DETECT_THRESHOLD:
        return best
    return ""


def _get_parser(name: str) -> Parser:
    for p in PARSERS:
        if p.name == name:
            return p
    return _DEFAULT_PARSER


# 兜底解析器：detect 恒返回 False（避免被探测选中），parse 时逐行成记录。
_FALLBACK_PARSER = Parser("fallback", lambda line: False, _fallback_parse)


# ---------------------------------------------------------------------------
# 核心解析
# ---------------------------------------------------------------------------
def _decode(path: Path) -> str:
    """按候选编码读取文件，返回解码后的文本"""
    last_err: Exception | None = None
    for enc in config.LOG_ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError) as e:
            last_err = e
    raise ValueError(f"无法解码日志文件 {path}: {last_err}")


def _parse_text(text: str, watch_levels: set[str] | None) -> list[LogRecord]:
    lines = text.splitlines()
    fmt = detect_format(lines)
    # 识别不到任何已知格式 → 用逐行兜底解析，避免整文件被当成续行丢弃
    parser = _get_parser(fmt) if fmt else _FALLBACK_PARSER

    records: list[LogRecord] = []
    cur: LogRecord | None = None

    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        m = parser.parse(line)
        if m:
            # 新记录开始
            if cur is not None:
                records.append(cur)
            ts, level_raw, module, message = m
            cur = LogRecord(
                timestamp=ts,
                level=normalize_level(level_raw),
                module=module,
                message=message.strip(),
                raw_lines=[line],
                start_line=lineno,
                end_line=lineno,
                level_raw=level_raw,
            )
        else:
            # 续行：挂到当前记录（若存在），扩展结束行号
            if cur is not None:
                cur.raw_lines.append(line)
                cur.end_line = lineno
                cur.message += "\n" + line

    if cur is not None:
        records.append(cur)

    if watch_levels is None:
        return records
    return [r for r in records if r.level in watch_levels]


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
    return _parse_text(text, watch)


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

    返回 Markdown 风格文本：
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
