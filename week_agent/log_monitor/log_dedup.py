#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志去重模板工具 — 将日志消息归一化为模板，统计重复模式

功能：
1. 读取日志文件（支持多格式自动探测）
2. 正则归一化消息中的变量部分（时间戳、ID、路径、数字等）
3. 按模板聚类，统计每个模板的出现次数
4. 输出去重后的模板列表（含计数、示例、行号）

用法：
    python log_dedup.py --dir E:\\weekAgent\\logs --glob "*.log"
    python log_dedup.py --files app.log;qwenpaw.log --format json
    python log_dedup.py --dir /var/log --format summary
"""

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════

ENCODINGS = ["utf-8", "gbk", "latin-1"]
MAX_RECORD_CHARS = 2000
DEFAULT_MAX_FILES = 20

# ── 消息归一化规则（用于聚类）───────────────────────────────────────────

NORMALIZERS = [
    # 尝试次数
    (re.compile(r'attempt \d+/\d+'), 'attempt {N}/{N}'),
    # HTTP 状态码 [xxx]
    (re.compile(r'\[\d{3}\]'), '[{http_code}]'),
    # 错误码 Error code: xxx
    (re.compile(r'Error code: \d+'), 'Error code: {code}'),
    # UUID
    (re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'), '{uuid}'),
    # ISO 时间戳
    (re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?'), '{ts}'),
    # 带冒号的数字参数 :123] 或 :123) 或 :123,
    (re.compile(r':\d{3,6}[\],\);]'), ':{n}]'),
    # Windows/Unix 文件路径
    (re.compile(r'[A-Za-z]:\\[\w\\.-]+\.\w+'), '{path}'),
    (re.compile(r'/[\w/-]+\.\w+'), '{path}'),
    # C 日志 ThreadId=0x9F4 (2548)
    (re.compile(r'ThreadId=0x[\da-fA-F]+ \(\d+\)'), '{thread}'),
    # 纯数字 ID（长的）
    (re.compile(r'\b\d{6,}\b'), '{id}'),
    # 日期 2026-07-31
    (re.compile(r'\d{4}-\d{2}-\d{2}'), '{date}'),
    # C 日志相对时间戳 0.000000
    (re.compile(r'(?<!\d)\d+\.\d{4,6}(?!\d)'), '{rel_ts}'),
]


# ═══════════════════════════════════════════════════════════════════════════
# 日志记录模型
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LogRecord:
    """一条日志记录"""
    timestamp: str = ""
    level: str = "INFO"
    module: str = ""
    message: str = ""
    start_line: int = 0
    end_line: int = 0

    @property
    def truncated(self) -> str:
        """给 LLM 看的截断文本"""
        body = self.message
        if len(body) > MAX_RECORD_CHARS:
            body = body[:MAX_RECORD_CHARS] + f" ...(截断, 原文 {len(self.message)} 字符)"
        return f"{self.timestamp} | {self.level} | {self.module} | {body}"


# ═══════════════════════════════════════════════════════════════════════════
# 级别归一化
# ═══════════════════════════════════════════════════════════════════════════

LEVEL_ALIASES = {
    "error": "ERROR", "err": "ERROR", "failure": "ERROR", "fail": "ERROR",
    "failed": "ERROR", "severe": "ERROR", "fatal": "ERROR", "critical": "ERROR",
    "panic": "ERROR", "alert": "ERROR", "emergency": "ERROR", "emerg": "ERROR",
    "warn": "WARNING", "warning": "WARNING",
    "info": "INFO", "informational": "INFO", "notice": "INFO",
    "debug": "DEBUG", "dbug": "DEBUG", "trace": "DEBUG", "verbose": "DEBUG",
    # C 日志宏（MMS/IEC 61850）
    "slogalways": "INFO",
    "sx_log_err": "ERROR", "sx_log_nerr": "WARNING",
    "mvllog_err": "ERROR", "mvllog_nerr": "WARNING", "mvllog_msg": "INFO",
    "clnp_log_err": "ERROR", "clnp_log_nerr": "WARNING",
    "tp4_log_err": "ERROR", "tp4_log_nerr": "WARNING",
}

STD_LEVELS = {"INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL"}


def normalize_level(raw: str) -> str:
    """把任意原始级别词归一为标准级别"""
    stripped = (raw or "").strip()
    # 先尝试原始值（保留下划线，如 SX_LOG_ERR）
    low = stripped.lower()
    if low in LEVEL_ALIASES:
        return LEVEL_ALIASES[low]
    if stripped.upper() in STD_LEVELS:
        return stripped.upper()
    # 再尝试去掉分隔符后的值（如 error、err）
    key = re.sub(r'[\s_\-()\[\]\/]+', '', stripped).lower()
    if key in LEVEL_ALIASES:
        return LEVEL_ALIASES[key]
    head = stripped.upper()[:1]
    if head in ("E", "F"):
        return "ERROR"
    if head == "W":
        return "WARNING"
    if head == "D":
        return "DEBUG"
    return "INFO"


def normalize_message(msg: str) -> str:
    """把消息中的变量部分替换为占位符，用于聚类分组"""
    result = msg
    for pattern, replacement in NORMALIZERS:
        result = pattern.sub(replacement, result)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 多格式解析器（从 log_parser.py 精简而来）
# ═══════════════════════════════════════════════════════════════════════════

_TIMESTAMP_ISO = r'\d{4}[-\/]\d{1,2}[-\/]\d{1,2}[ T]\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,6})?'
_TIMESTAMP_SYSLOG = r'[A-Z][a-z]{2}\s+\d{1,2}\s+\d{1,2}:\d{2}:\d{2}'


class Parser:
    def __init__(self, name, detect, parse):
        self.name = name
        self.detect = detect
        self.parse = parse


def _parse_pipeline(line):
    # 标准管道格式: timestamp | level | module | message
    m = re.match(rf'^({_TIMESTAMP_ISO}) \| ([A-Za-z_]+) \| (.+)$', line)
    if m:
        ts, level, rest = m.group(1), m.group(2), m.group(3)
        module, _, message = rest.partition(" | ")
        return ts, level, module.strip(), message.strip()
    
    # 方括号格式: [timestamp] [task] [level] [logger] -message
    # 时间戳可能在方括号内: [2026-08-07 08:27:44.139]
    m = re.match(rf'^\[({_TIMESTAMP_ISO})\]\s*\[[^\]]*\]\s*\[([A-Za-z_]+)\]\s*\[[^\]]*\]\s*-\s*(.+)$', line)
    if m:
        ts, level, message = m.group(1), m.group(2), m.group(3)
        return ts, level, "", message.strip()
    
    # 简化格式: [timestamp] [level] message
    m = re.match(rf'^\[({_TIMESTAMP_ISO})\]\s*\[([A-Za-z_]+)\]\s*(.+)$', line)
    if m:
        ts, level, message = m.group(1), m.group(2), m.group(3)
        return ts, level, "", message.strip()
    
    return None


def _detect_pipeline(line):
    # 标准管道格式
    if re.match(rf'^{_TIMESTAMP_ISO} \| [A-Za-z_]', line):
        return True
    # 方括号格式: [timestamp] [task] [level] [logger]
    if re.match(r'^\[({_TIMESTAMP_ISO})\]\s*\[[^\]]*\]\s*\[[A-Za-z_]+\]', line):
        return True
    # 简化格式: [timestamp] [level]
    if re.match(r'^\[({_TIMESTAMP_ISO})\]\s*\[[A-Za-z_]+\]', line):
        return True
    # 包含时间戳和级别关键词的行
    if re.search(_TIMESTAMP_ISO, line) and re.search(r'\[(ERROR|WARNING|INFO|DEBUG)\]', line):
        return True
    return False


def _parse_python_logger(line):
    m = re.match(rf'^({_TIMESTAMP_ISO}) - ([^|-]+?) - ([A-Za-z_]+?) - (.*)$', line)
    if not m:
        return None
    ts, module, level, message = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
    return ts, level, module, message.strip()


def _detect_python_logger(line):
    return re.match(rf'^{_TIMESTAMP_ISO} - ', line) is not None


def _parse_syslog(line):
    m = re.match(rf'^({_TIMESTAMP_SYSLOG})\s+(\S+)\s+([\w./-]+\[?[^:]*\]?): (.*)$', line)
    if not m:
        return None
    ts, host, tag, message = m.group(1), m.group(2), m.group(3), m.group(4)
    return ts, "INFO", f"{host} {tag}".strip(), message.strip()


def _detect_syslog(line):
    return re.match(rf'^{_TIMESTAMP_SYSLOG}\s+', line) is not None


def _parse_jsonl(line):
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
    # JSONL 应该以 { 或 [ 开头，但 [ 后面应该是 JSON 内容，不是时间戳
    if s[:1] == "{":
        return True
    if s[:1] == "[":
        # 检查是否是 JSON 数组（不是方括号格式的日志）
        # 方括号格式的日志通常是 [timestamp] [level] ...
        if re.match(r'^\[\d{4}', s):
            return False  # 这是方括号格式的日志，不是 JSONL
        return True
    return False


# ── MMS/IEC 61850 C 日志解析器 ──────────────────────────────────────────

# 头部行：时间戳 + 级别宏 + (源码文件 行号 [ThreadId=...])
_MMS_TIMESTAMP = r'\d[\d:. -]*\d'  # 绝对时间 或 相对时间 0.000000
_MMS_LEVEL_MACROS = (
    r'SLOGALWAYS|SX_LOG_\w+|MVLLOG_\w+|CLNP_LOG_\w+|TP4_LOG_\w+'
)
# 匹配：时间戳 级别宏 (源码信息)
_MMS_HEADER_RE = re.compile(
    rf'^({_MMS_TIMESTAMP})\s+({_MMS_LEVEL_MACROS})\s+\((\S+\s+\d+)(?:\s+ThreadId=.*)?\)\s*$'
)
# 分隔符块行
_MMS_SEPARATOR_RE = re.compile(r'^\*{10,}')


def _detect_mms_c(line):
    """检测 MMS/IEC 61850 C 日志头部行"""
    return _MMS_HEADER_RE.match(line.strip()) is not None


def _parse_mms_c(line):
    """解析 MMS/IEC 61850 C 日志头部行，返回 (ts, level, module, message)"""
    m = _MMS_HEADER_RE.match(line.strip())
    if not m:
        return None
    ts = m.group(1).strip()
    level_raw = m.group(2).strip()
    module = m.group(3).strip()  # e.g. "scl_srvr.c 970"
    return ts, level_raw, module, ""


PARSERS = [
    Parser("mms_c", _detect_mms_c, _parse_mms_c),
    Parser("pipeline", _detect_pipeline, _parse_pipeline),
    Parser("python_logger", _detect_python_logger, _parse_python_logger),
    Parser("syslog", _detect_syslog, _parse_syslog),
    Parser("jsonl", _detect_jsonl, _parse_jsonl),
]


def _fallback_parse(line):
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


_DETECT_SAMPLE_LINES = 50
DETECT_THRESHOLD = 0.5


def detect_format(lines: list[str]) -> str:
    # 支持以数字开头的行（标准格式/MMS C）或以 [ 开头的行（方括号格式）
    support_lines = [l for l in lines if l.strip() and (re.match(r'^\d', l) or re.match(r'^\[', l))]
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
    return PARSERS[0]


_FALLBACK_PARSER = Parser("fallback", lambda line: False, _fallback_parse)


def _decode(path: Path) -> str:
    last_err = None
    for enc in ENCODINGS:
        try:
            text = path.read_text(encoding=enc)
            # 移除 BOM 字符
            if text.startswith('\ufeff'):
                text = text[1:]
            return text
        except (UnicodeDecodeError, LookupError) as e:
            last_err = e
    raise ValueError(f"无法解码日志文件 {path}: {last_err}")


def _is_stacktrace_line(line: str) -> bool:
    """检测是否为 Java 堆栈跟踪行"""
    stripped = line.strip()
    # Java 堆栈行通常以 "at " 或 "Caused by: " 开头
    if stripped.startswith("at ") or stripped.startswith("Caused by: "):
        return True
    # 或者包含典型的堆栈模式（带缩进）
    if re.match(r'^\s+at\s+[\w.$]+\(', stripped):
        return True
    # Java 异常类名（以 .Exception 或 .Error 结尾，可选后跟 : 消息）
    if re.match(r'^[\w.$]+(?:Exception|Error)(?:[:\s]|$)', stripped):
        return True
    # 包含 "Exception" 或 "Error" 的行（但不是以 at 开头）
    if ('Exception' in stripped or 'Error' in stripped) and not stripped.startswith('at '):
        # 可能是异常消息行（如 feign.FeignException$NotFound: ...）
        if re.match(r'^[\w.$]+\$[\w.]+:', stripped) or re.match(r'^[\w.$]+(?:Exception|Error)(?:[:\s]|$)', stripped):
            return True
    return False


def _parse_text(text: str, watch_levels: set[str] | None) -> list[LogRecord]:
    lines = text.splitlines()
    fmt = detect_format(lines)
    parser = _get_parser(fmt) if fmt else _FALLBACK_PARSER

    records: list[LogRecord] = []
    cur: LogRecord | None = None

    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        # 跳过分隔符块（MMS C 日志的会话开始标记）
        if _MMS_SEPARATOR_RE.match(line.strip()):
            continue

        # 堆栈跟踪行和异常类名行 → 直接追加到当前记录，不尝试解析为新记录
        if cur is not None and _is_stacktrace_line(line):
            cur.end_line = lineno
            cur.message += "\n" + line
            continue

        # 检查是否是新的日志记录（匹配解析器）
        m = parser.parse(line)
        if m:
            if cur is not None:
                records.append(cur)
            ts, level_raw, module, message = m
            cur = LogRecord(
                timestamp=ts,
                level=normalize_level(level_raw),
                module=module,
                message=message.strip(),
                start_line=lineno,
                end_line=lineno,
            )
        else:
            # 不是新记录，也不是堆栈行 → 作为续行追加到当前记录
            if cur is not None:
                cur.end_line = lineno
                # 对于空消息的记录（如 MMS C 解析器），直接用 strip 后的内容作为消息
                if not cur.message.strip():
                    cur.message = line.strip()
                else:
                    cur.message += "\n" + line

    if cur is not None:
        records.append(cur)

    if watch_levels is None:
        return records
    return [r for r in records if r.level in watch_levels]


def parse_file(file_path: str, watch_levels: set[str] | None = None) -> list[LogRecord]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"日志文件不存在: {path}")
    text = _decode(path)
    return _parse_text(text, watch_levels)


def resolve_log_files(
    glob_pattern: str,
    log_dir: str | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> list[Path]:
    base = Path(log_dir) if log_dir else Path.cwd()
    patterns = [p.strip() for p in glob_pattern.split(";") if p.strip()]

    seen: set[str] = set()
    candidates: list[Path] = []

    for pat in patterns:
        full_pattern = str(base / pat) if not Path(pat).is_absolute() else pat
        for match in glob.glob(full_pattern, recursive=True):
            p = Path(match).resolve()
            if p.is_file() and str(p) not in seen:
                seen.add(str(p))
                candidates.append(p)

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:max_files]


# ═══════════════════════════════════════════════════════════════════════════
# 核心：去重模板聚类
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TemplateCluster:
    """一个去重后的模板聚类"""
    template: str           # 归一化后的消息模板（第一行）
    count: int              # 出现次数
    level: str              # 日志级别
    module: str             # 模块
    first_time: str         # 首次出现时间
    last_time: str          # 末次出现时间
    lines: list[int]        # 所有原始行号
    examples: list[str]     # 最多3条完整原文示例
    has_stacktrace: bool = False  # 是否包含堆栈跟踪


def _extract_first_line_for_template(message: str) -> str:
    """
    提取消息的第一行用于模板归一化。
    对于 Java 堆栈跟踪，只用第一行（错误消息）来生成模板，
    忽略后续的堆栈行。
    """
    lines = message.split('\n')
    first_line = lines[0].strip()
    
    # 如果第一行是堆栈跟踪行，继续找非堆栈行
    if _is_stacktrace_line(first_line):
        for line in lines:
            stripped = line.strip()
            if stripped and not _is_stacktrace_line(stripped):
                return stripped
    
    return first_line


def dedup_logs(records: list[LogRecord]) -> list[TemplateCluster]:
    """
    将日志记录去重为模板聚类。

    三层漏斗：
    1. 精确去重：完全相同的消息合并计数
    2. 模板归一化：正则剥离变量（时间戳、ID、UUID、路径等）
    3. 聚类输出：按模板分组，保留行号和示例

    对于多行消息（如 Java 堆栈跟踪），只用第一行生成模板。

    Returns:
        按 count 降序排列的 TemplateCluster 列表
    """
    # key: (normalized_msg, level, module) → 聚类桶
    buckets: dict[tuple, dict] = defaultdict(lambda: {
        "template": "",
        "count": 0,
        "level": "",
        "module": "",
        "first_ts": None,
        "last_ts": None,
        "lines": [],
        "examples_raw": [],
    })

    for r in records:
        # 提取第一行用于模板生成
        first_line = _extract_first_line_for_template(r.message)
        norm = normalize_message(first_line)
        key = (norm, r.level, r.module)
        b = buckets[key]
        b["template"] = norm
        b["count"] += 1
        b["level"] = r.level
        b["module"] = r.module
        b["lines"].append(r.start_line)

        # 记录时间范围
        ts = r.timestamp
        if ts:
            if b["first_ts"] is None or ts < b["first_ts"]:
                b["first_ts"] = ts
            if b["last_ts"] is None or ts > b["last_ts"]:
                b["last_ts"] = ts

        # 保留最多3条完整原文作为示例
        if len(b["examples_raw"]) < 3:
            b["examples_raw"].append(r.truncated)

    # 组装输出，按 count 降序
    clusters = []
    for b in buckets.values():
        # 检查是否包含堆栈跟踪（通过示例判断）
        has_stacktrace = any('\n' in ex for ex in b["examples_raw"])
        
        clusters.append(TemplateCluster(
            template=b["template"],
            count=b["count"],
            level=b["level"],
            module=b["module"],
            first_time=b["first_ts"] or "",
            last_time=b["last_ts"] or "",
            lines=b["lines"],
            examples=b["examples_raw"],
            has_stacktrace=has_stacktrace,
        ))

    clusters.sort(key=lambda c: c.count, reverse=True)
    return clusters


def format_clusters_text(clusters: list[TemplateCluster], top_n: int = 20) -> str:
    """格式化聚类结果为可读文本"""
    lines = [f"=== 日志去重模板分析 ({len(clusters)} 个模板) ==="]
    lines.append(f"按出现次数降序，显示 Top {min(top_n, len(clusters))} 个模板\n")

    for i, c in enumerate(clusters[:top_n], 1):
        # 标记是否包含堆栈
        stack_flag = " [含堆栈]" if c.has_stacktrace else ""
        lines.append(f"━━━ 模板 #{i} [级别: {c.level} | 模块: {c.module} | 出现: {c.count}次]{stack_flag} ━━━")
        lines.append(f"模板: {c.template}")
        lines.append(f"时间: {c.first_time} ~ {c.last_time}")
        lines.append(f"行号: {c.lines[:10]}{'...' if len(c.lines) > 10 else ''}")
        lines.append(f"示例:")
        for j, ex in enumerate(c.examples[:2]):
            # 对于多行示例，只显示第一行，后面的缩进显示
            ex_lines = ex.split('\n')
            lines.append(f"  [{j+1}] {ex_lines[0]}")
            if len(ex_lines) > 1:
                lines.append(f"      (+ {len(ex_lines)-1} 行堆栈)")
        lines.append("")

    if len(clusters) > top_n:
        lines.append(f"... 还有 {len(clusters) - top_n} 个模板未显示")

    return "\n".join(lines)


def format_clusters_json(clusters: list[TemplateCluster]) -> dict:
    """格式化聚类结果为 JSON 结构"""
    # 统计汇总
    total_count = sum(c.count for c in clusters)
    by_level = defaultdict(int)
    by_module = defaultdict(int)
    stacktrace_count = 0
    for c in clusters:
        by_level[c.level] += c.count
        by_module[c.module] += c.count
        if c.has_stacktrace:
            stacktrace_count += c.count

    return {
        "summary": {
            "total_records": total_count,
            "template_count": len(clusters),
            "by_level": dict(by_level),
            "by_module": dict(sorted(by_module.items(), key=lambda x: x[1], reverse=True)),
            "stacktrace_records": stacktrace_count,
        },
        "templates": [
            {
                "rank": i + 1,
                "template": c.template,
                "count": c.count,
                "level": c.level,
                "module": c.module,
                "has_stacktrace": c.has_stacktrace,
                "time_range": f"{c.first_time} ~ {c.last_time}",
                "line_count": len(c.lines),
                "lines": c.lines,
                "examples": c.examples[:2],
            }
            for i, c in enumerate(clusters)
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="日志去重模板工具 — 将日志消息归一化为模板，统计重复模式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python log_dedup.py --dir E:\\weekAgent\\logs --glob "*.log"
  python log_dedup.py --files app.log;qwenpaw.log --format json
  python log_dedup.py --dir /var/log --format summary --top 10
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", help="日志目录路径")
    group.add_argument("--files", help="分号分隔的日志文件路径")

    parser.add_argument("--glob", default="*.log;**/*.log", help="glob 模式 (默认: *.log;**/*.log，递归子目录)")
    parser.add_argument("--levels", default="WARNING,ERROR", help="要提取的级别 (默认: WARNING,ERROR)")
    parser.add_argument("--format", choices=["text", "json", "summary"], default="text", help="输出格式 (默认: text)")
    parser.add_argument("--top", type=int, default=20, help="显示前N个模板 (默认: 20)")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help="最多扫描文件数 (默认: 20)")

    args = parser.parse_args()

    # 解析文件列表
    if args.files:
        files = [Path(f.strip()) for f in args.files.split(";") if f.strip()]
    else:
        files = resolve_log_files(args.glob, args.dir, args.max_files)

    if not files:
        print(json.dumps({"status": "error", "message": "未发现任何日志文件"}, ensure_ascii=False))
        sys.exit(1)

    # 解析级别
    watch_levels = {l.strip().upper() for l in args.levels.split(",") if l.strip()}

    # 解析所有文件
    all_records: list[LogRecord] = []
    files_info = {}

    for fp in files:
        if not fp.exists():
            files_info[str(fp)] = {"status": "missing"}
            continue
        try:
            recs = parse_file(str(fp), watch_levels)
            all_records.extend(recs)
            files_info[str(fp)] = {
                "status": "ok",
                "file_name": fp.name,
                "file_size_kb": fp.stat().st_size // 1024,
                "record_count": len(recs),
            }
        except Exception as e:
            files_info[str(fp)] = {"status": "error", "message": str(e)}

    if not all_records:
        print(json.dumps({"status": "error", "message": "未发现任何符合条件的日志记录"}, ensure_ascii=False))
        sys.exit(1)

    # 去重聚类
    clusters = dedup_logs(all_records)

    # 输出
    if args.format == "json":
        output = {
            "status": "ok",
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": files_info,
            "clusters": format_clusters_json(clusters)["templates"],
            "summary": format_clusters_json(clusters)["summary"],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif args.format == "summary":
        # 紧凑摘要
        summary = format_clusters_json(clusters)["summary"]
        print(f"日志去重分析: {summary['total_records']}条 → {summary['template_count']}个模板")
        print(f"级别分布: {summary['by_level']}")
        print(f"模块分布: {summary['by_module']}")
        print("\nTop 5 模板:")
        for c in clusters[:5]:
            print(f"  [{c.level}] {c.count}次: {c.template[:80]}")
    else:
        # 文本格式
        result = format_clusters_text(clusters, top_n=args.top)
        # 附加文件信息
        files_text = "\n=== 文件信息 ===\n"
        for fp, info in files_info.items():
            if info["status"] == "ok":
                files_text += f"✅ {info['file_name']} ({info['file_size_kb']}KB): {info['record_count']}条记录\n"
            else:
                files_text += f"❌ {fp}: {info.get('message', '未知错误')}\n"
        print(files_text)
        print(result)


if __name__ == "__main__":
    main()
