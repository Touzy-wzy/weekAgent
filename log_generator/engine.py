# -*- coding: utf-8 -*-
"""日志生成引擎 - 模板驱动 + 随机参数化，模拟生产环境日志"""

import os
import random
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from . import config, templates
except ImportError:
    import config
    import templates


class LogGenerator:
    """日志生成器

    用法:
        gen = LogGenerator(output_dir="generated_logs")
        gen.start()                             # 启动（后台线程）
        gen.generate_batch(count=100)           # 批量生成 100 条
        gen.stop()                              # 停止
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        error_ratio: Optional[float] = None,
        warning_ratio: Optional[float] = None,
        max_file_size_mb: Optional[int] = None,
        rotate_hours: Optional[int] = None,
    ):
        self.output_dir = Path(output_dir or config.LOG_OUTPUT_DIR)
        self.error_ratio = error_ratio if error_ratio is not None else config.DEFAULT_ERROR_RATIO
        self.warning_ratio = warning_ratio if warning_ratio is not None else config.DEFAULT_WARNING_RATIO
        self.max_file_size = (max_file_size_mb or config.DEFAULT_MAX_FILE_SIZE_MB) * 1024 * 1024
        self.rotate_hours = rotate_hours or config.DEFAULT_ROTATE_HOURS

        self._running = False
        self._current_file: Optional[Path] = None
        self._current_file_start: Optional[datetime] = None
        self._base_time = datetime(2026, 8, 7, 9, 0, 0)  # 起始时间

        # 模块列表及其权重（模拟不同模块的日志产出比例）
        self._module_weights: dict[str, float] = {
            "app.api.public_api": 0.20,
            "app.services.agent_runtime.runtime": 0.25,
            "app.services.async_runner": 0.15,
            "ies_agents.memory.manager": 0.10,
            "app.services.database": 0.08,
            "app.services.cache": 0.05,
            "app.services.file_storage": 0.05,
            "app.middleware.auth": 0.05,
            "app.middleware.rate_limiter": 0.02,
            "uvicorn.access": 0.03,
            "app.services.skill_loader": 0.02,
        }

        os.makedirs(self.output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 变量替换
    # ------------------------------------------------------------------

    def _fill_vars(self, template_str: str) -> str:
        """替换模板中的 {变量} 为随机值"""
        replacements = {
            "agent_id": random.choice(templates.AGENT_IDS),
            "uuid": uuid.uuid4().hex[:16],
            "task_id": uuid.uuid4().hex[:12],
            "callback_url": random.choice(templates.CALLBACK_URLS),
            "step": str(random.randint(1, 10)),
            "n": str(random.randint(1, 20)),
            "tool_name": random.choice(templates.TOOL_NAMES),
            "error_msg": random.choice(templates.ERROR_MESSAGES),
            "http_status": random.choice(["200", "301", "400", "403", "404", "500", "502", "503"]),
            "user_id": f"user_{uuid.uuid4().hex[:8]}",
            "thought": random.choice(templates.THOUGHTS),
            "result": random.choice(templates.RESULTS),
            "duration": str(random.randint(10, 5000)),
            "size": str(random.randint(1024, 10485760)),
            "name": random.choice(templates.FILE_NAMES),
            "type": random.choice(templates.FILE_TYPES),
            "path": f"/app/uploads/ext_api_{uuid.uuid4().hex[:12]}/{uuid.uuid4().hex[:8]}",
            "db_table": random.choice(templates.DB_TABLES),
            "query_time": str(random.randint(5, 3000)),
            "cache_key": f"cache:{uuid.uuid4().hex[:8]}:{random.choice(['user', 'session', 'config', 'data'])}",
            "endpoint": random.choice(templates.ENDPOINTS),
            "method": random.choice(templates.HTTP_METHODS),
            "ip": random.choice(templates.IPS),
            "session_id": f"sess_{uuid.uuid4().hex[:12]}",
            "memory_type": random.choice(templates.MEMORY_TYPES),
            "skill_name": random.choice(templates.SKILL_NAMES),
            "contract_name": f"产品销售协议_{uuid.uuid4().hex[:6]}",
            "timestamp": datetime.now().strftime("%d/%b/%Y:%H:%M:%S +0800"),
        }
        result = template_str
        for key, val in replacements.items():
            result = result.replace("{" + key + "}", val)
        return result

    # ------------------------------------------------------------------
    # 单条日志生成
    # ------------------------------------------------------------------

    def _pick_level(self) -> str:
        """按概率选取日志级别"""
        r = random.random()
        if r < self.error_ratio:
            return "ERROR"
        elif r < self.error_ratio + self.warning_ratio:
            return "WARNING"
        return "INFO"

    def _pick_module(self) -> str:
        """按权重选取模块"""
        modules = list(self._module_weights.keys())
        weights = list(self._module_weights.values())
        return random.choices(modules, weights=weights, k=1)[0]

    def _pick_template(self, module: str, level: str) -> str:
        """从模块+级别中选取一条模板"""
        t = templates.TEMPLATES.get(module, {})
        level_templates = t.get(level)
        if not level_templates:
            # 如果该模块没有该级别的模板，回退到 INFO
            level_templates = t.get("INFO", [])
        if not level_templates:
            return "日志记录"
        return random.choice(level_templates)

    def generate_one(self) -> str:
        """生成单条日志行"""
        module = self._pick_module()
        level = self._pick_level()
        template_str = self._pick_template(module, level)
        message = self._fill_vars(template_str)

        # 时间戳推进（随机间隔 50ms ~ 5s）
        advance_ms = random.randint(50, 5000)
        self._base_time += timedelta(milliseconds=advance_ms)

        ts = self._base_time.strftime(config.TIMESTAMP_FORMAT)
        ms = self._base_time.microsecond // 1000

        return config.LOG_LINE_FORMAT.format(
            timestamp=ts, ms=ms, level=level, module=module, message=message
        )

    # ------------------------------------------------------------------
    # 文件轮转
    # ------------------------------------------------------------------

    def _rotate_if_needed(self):
        """检查是否需要轮转日志文件"""
        if self._current_file is None:
            self._open_new_file()
            return

        # 按时间轮转
        if self._current_file_start is not None:
            elapsed = (datetime.now() - self._current_file_start).total_seconds()
            if elapsed >= self.rotate_hours * 3600:
                self._open_new_file()
                return

        # 按大小轮转
        try:
            if self._current_file.stat().st_size >= self.max_file_size:
                self._open_new_file()
        except OSError:
            self._open_new_file()

    def _open_new_file(self):
        """打开新的日志文件"""
        self._current_file_start = datetime.now()
        ts = self._current_file_start.strftime("%Y%m%d_%H%M%S")
        self._current_file = self.output_dir / f"app_{ts}.log"

    # ------------------------------------------------------------------
    # 批量生成
    # ------------------------------------------------------------------

    def generate_batch(self, count: int = 100) -> list[str]:
        """批量生成日志行，返回生成的行列表"""
        lines = []
        for _ in range(count):
            self._rotate_if_needed()
            line = self.generate_one()
            lines.append(line)
            self._write_line(line)
        return lines

    def _write_line(self, line: str):
        """写入一行日志到当前文件"""
        if self._current_file is None:
            self._open_new_file()
        with open(self._current_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------------
    # 持续运行（后台线程）
    # ------------------------------------------------------------------

    def start(self, rate: Optional[float] = None):
        """启动持续生成（后台线程）"""
        import threading

        if self._running:
            return

        self._running = True
        self._rate = rate or config.DEFAULT_RATE

        def _loop():
            interval = 1.0 / self._rate
            while self._running:
                self._rotate_if_needed()
                line = self.generate_one()
                self._write_line(line)
                time.sleep(interval)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止持续生成"""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # 列出已生成的日志文件
    # ------------------------------------------------------------------

    def list_files(self, pattern: str = "*.log") -> list[Path]:
        """列出 output_dir 下的日志文件，按修改时间倒序"""
        files = sorted(
            self.output_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files

    def read_file(self, filename: str, lines: int = 200, offset: int = 0) -> str:
        """读取日志文件末尾指定行数"""
        filepath = self.output_dir / filename
        if not filepath.is_file():
            return ""

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        if offset >= total:
            return ""

        start = offset
        end = min(start + lines, total)
        return "".join(all_lines[start:end])

# ===========================================================================
# 数据访问层（MCP 工具后端）
# ---------------------------------------------------------------------------
# 支持多个白名单根目录，所有 path 参数为相对根目录的相对路径。
# 提供：目录浏览 / 文件信息 / 分页读取 / head / tail / 采样 / 筛选 / 统计
# ===========================================================================


class LogDataAccess:
    """多根目录日志数据访问器（只读，无副作用）

    用法:
        da = LogDataAccess()
        da.list_roots()                        # ['generated_logs', 'log_files']
        da.list_dir("log_files")               # 目录条目
        da.file_info("generated_logs/app.log") # 行数/大小/mtime
        da.read_file("generated_logs/app.log", offset=100, lines=200)
    """

    def __init__(self, roots: Optional[list[Path]] = None):
        self.roots = [r.resolve() for r in (roots if roots is not None else config.ALLOWED_ROOTS)]

    # ------------------------------------------------------------------
    # 路径解析与安全校验
    # ------------------------------------------------------------------

    def resolve_path(self, path: str) -> Path:
        """将相对路径解析到某个白名单根目录下的绝对路径。

        规则:
          - path 为空 → 根目录列表本身（调用方需自行判断）
          - 相对路径第一段若匹配某个根目录名 → 从该根目录解析
          - 否则尝试从唯一的根目录解析（仅当只有一个根目录时）
          - 禁止 .. 穿越、禁止绝对路径、禁止超出根目录
        """
        if not path or path in (".", "/"):
            raise ValueError("path 不能为空，请使用 list_roots() 查看可用根目录")

        # 绝对路径直接拒绝（只接受相对路径）
        p = Path(path)
        if p.is_absolute():
            raise ValueError(f"只接受相对路径，拒绝绝对路径: {path}")

        # 探测 path 第一段是否为根目录名
        parts = p.parts
        for root in self.roots:
            if parts and parts[0] == root.name:
                candidate = root.joinpath(*parts[1:]).resolve()
                if self._is_within_root(candidate, root):
                    return candidate
                raise ValueError(f"路径超出根目录 {root.name}: {path}")

        # 未匹配根目录名：仅当只有一个根目录时按该根目录解析
        if len(self.roots) == 1:
            candidate = self.roots[0].joinpath(p).resolve()
            if self._is_within_root(candidate, self.roots[0]):
                return candidate
            raise ValueError(f"路径超出根目录: {path}")

        raise ValueError(
            f"无法确定根目录，请以根目录名开头: {path} "
            f"（可用根目录: {', '.join(r.name for r in self.roots)}）"
        )

    @staticmethod
    def _is_within_root(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    def _find_root(self, path: str) -> tuple[Path, Path]:
        """返回 (root, 相对root的子路径)"""
        if not path or path in (".", "/"):
            raise ValueError("path 不能为空")

        p = Path(path)
        if p.is_absolute():
            raise ValueError(f"只接受相对路径，拒绝绝对路径: {path}")

        parts = p.parts
        for root in self.roots:
            if parts and parts[0] == root.name:
                return root, Path(*parts[1:]) if len(parts) > 1 else Path(".")
        if len(self.roots) == 1:
            return self.roots[0], p
        raise ValueError(f"无法确定根目录: {path}")

    # ------------------------------------------------------------------
    # 目录浏览
    # ------------------------------------------------------------------

    def list_roots(self) -> list[dict]:
        """列出所有可访问的根目录"""
        result = []
        for root in self.roots:
            try:
                entries = list(root.iterdir())
                dirs = sum(1 for e in entries if e.is_dir())
                files = sum(1 for e in entries if e.is_file())
                result.append({
                    "name": root.name,
                    "path": str(root),
                    "dirs": dirs,
                    "files": files,
                    "total_entries": len(entries),
                })
            except OSError as e:
                result.append({"name": root.name, "path": str(root), "error": str(e)})
        return result

    def list_dir(self, path: str = "", pattern: str = "*") -> list[dict]:
        """浏览指定目录（相对路径），返回子目录与文件条目。

        path 为空时列出所有根目录（等价 list_roots 的目录视角）。
        """
        if not path or path in (".", "/"):
            return self.list_roots()

        root, sub = self._find_root(path)
        target = root.joinpath(sub).resolve()
        if not self._is_within_root(target, root):
            raise ValueError(f"路径超出根目录 {root.name}: {path}")
        if not target.is_dir():
            raise ValueError(f"不是目录: {path}")

        entries = []
        for e in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                if e.is_dir():
                    entries.append({
                        "type": "dir",
                        "name": e.name,
                        "path": f"{root.name}/{e.relative_to(root).as_posix()}",
                        "size": None,
                        "mtime": datetime.fromtimestamp(e.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    })
                elif e.is_file() and Path(e.name).match(pattern):
                    st = e.stat()
                    entries.append({
                        "type": "file",
                        "name": e.name,
                        "path": f"{root.name}/{e.relative_to(root).as_posix()}",
                        "size": st.st_size,
                        "size_mb": round(st.st_size / (1024 * 1024), 2),
                        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    })
            except OSError:
                continue
        return entries

    # ------------------------------------------------------------------
    # 文件信息
    # ------------------------------------------------------------------

    def file_info(self, path: str) -> dict:
        """返回文件基本信息（行数/大小/修改时间），增量读取用行数对比"""
        filepath = self.resolve_path(path)
        if not filepath.is_file():
            raise ValueError(f"文件不存在: {path}")

        st = filepath.stat()
        # 行数统计（按文本行）
        line_count = 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for _ in f:
                    line_count += 1
        except OSError:
            pass

        return {
            "path": path,
            "abs_path": str(filepath),
            "size": st.st_size,
            "size_mb": round(st.st_size / (1024 * 1024), 2),
            "lines": line_count,
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ------------------------------------------------------------------
    # 行级读取
    # ------------------------------------------------------------------

    def _read_lines(self, path: str, offset: int = 0, lines: int = 200) -> tuple[list[str], int]:
        """读取文件指定行区间，返回 (行列表, 文件总行数)"""
        filepath = self.resolve_path(path)
        if not filepath.is_file():
            raise ValueError(f"文件不存在: {path}")

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        if offset < 0:
            offset = 0
        start = offset
        end = min(start + lines, total)
        if start >= total:
            return [], total
        return all_lines[start:end], total

    def read_file(self, path: str, offset: int = 0, lines: int = 200, max_bytes: int = 0) -> str:
        """分页读取文件（带行号），支持 offset 游标增量。

        max_bytes > 0 时限制返回文本字节数（UTF-8 近似），超限截断并标注。
        """
        max_bytes = max_bytes or config.MCP_READ_MAX_BYTES
        chunk, total = self._read_lines(path, offset, lines)
        if not chunk:
            return f"# {path}: 无更多内容（总行数 {total}，offset={offset}）\n"

        out = []
        used = 0
        truncated = False
        for i, line in enumerate(chunk, start=offset + 1):
            numbered = f"[{i}] {line.rstrip(chr(10)).rstrip(chr(13))}"
            used += len(numbered.encode("utf-8", errors="replace")) + 1
            if max_bytes > 0 and used > max_bytes:
                truncated = True
                break
            out.append(numbered)
        result = "\n".join(out)
        if truncated:
            result += f"\n# ... 响应体超限（>{max_bytes//1024}KB），已截断，请用 offset={offset + len(out)} 继续读取"
        result += f"\n# --- 共返回 {len(out)} 行 / 文件总 {total} 行（offset={offset}）---"
        return result

    def head(self, path: str, lines: int = 50) -> str:
        """读取文件开头 N 行（带行号）"""
        return self.read_file(path, offset=0, lines=lines)

    def tail(self, path: str, lines: int = 50) -> str:
        """读取文件末尾 N 行（带行号）"""
        _, total = self._read_lines(path, 0, 1)
        offset = max(0, total - lines)
        return self.read_file(path, offset=offset, lines=lines)

    def sample(self, path: str, strategy: str = "head", count: int = 50) -> str:
        """多策略采样，供 LLM 快速了解全貌。

        strategy:
          - head   开头 N 行
          - tail   末尾 N 行
          - random 随机 N 行
          - evenly 均匀取 N 行（覆盖整个文件）
        """
        _, total = self._read_lines(path, 0, 1)
        if total <= count:
            return self.read_file(path, 0, count)

        if strategy == "head":
            return self.read_file(path, 0, count)
        if strategy == "tail":
            return self.tail(path, count)
        if strategy == "random":
            indices = sorted(random.sample(range(total), count))
        elif strategy == "evenly":
            step = total / count
            indices = [int(i * step) for i in range(count)]
        else:
            raise ValueError(f"未知采样策略: {strategy}（可选 head/tail/random/evenly）")

        chunk, _ = self._read_lines(path, 0, total)
        out = []
        for idx in indices:
            if idx < total:
                line = chunk[idx]
                out.append(f"[{idx + 1}] {line.rstrip(chr(10)).rstrip(chr(13))}")
        return "\n".join(out) + f"\n# --- 采样 {len(out)} 行 / 文件总 {total} 行（strategy={strategy}）---"

    def sample_range(self, path: str, start: int, lines: int, count: int = 200) -> str:
        """对指定行区间均匀采样 count 行（带行号）。

        用于超大增量（delta >> max_lines）时快速覆盖整个增量区间的全貌，
        而非只读区间开头的 N 行。区间行数 <= count 时全部返回。
        """
        filepath = self.resolve_path(path)
        if not filepath.is_file():
            raise ValueError(f"文件不存在: {path}")
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        if start < 0:
            start = 0
        end = min(start + lines, total)
        if start >= total:
            return f"# {path}: 无更多内容（总行数 {total}）\n"

        span = end - start
        if span <= count:
            out = []
            for i in range(start, end):
                line = all_lines[i]
                out.append(f"[{i + 1}] {line.rstrip(chr(10)).rstrip(chr(13))}")
            return "\n".join(out) + f"\n# --- 区间 [{start},{end}) 共 {span} 行，全部返回 ---"

        step = span / count
        out = []
        for k in range(count):
            idx = start + int(k * step)
            if idx < end:
                line = all_lines[idx]
                out.append(f"[{idx + 1}] {line.rstrip(chr(10)).rstrip(chr(13))}")
        return "\n".join(out) + \
            f"\n# --- 区间 [{start},{end}) 共 {span} 行，均匀采样 {len(out)} 行（strategy=evenly）---"

    # ------------------------------------------------------------------
    # 筛选与统计
    # ------------------------------------------------------------------

    LEVELS = ("ERROR", "WARNING", "INFO", "DEBUG", "TRACE")

    def extract(self, path: str, level: str = "", pattern: str = "", lines: int = 200) -> str:
        """按级别/正则筛选原始行（不做聚类，返回带行号原文）"""
        # 直接读取全部行进行筛选
        filepath = self.resolve_path(path)
        if not filepath.is_file():
            raise ValueError(f"文件不存在: {path}")
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        level_re = None
        if level:
            lvl = level.upper()
            if lvl not in self.LEVELS:
                raise ValueError(f"未知级别: {level}（可选 {', '.join(self.LEVELS)}）")
            level_re = re.compile(rf"\|\s*{lvl}\s*\|")
        pat_re = None
        if pattern:
            try:
                pat_re = re.compile(pattern)
            except re.error as e:
                raise ValueError(f"正则表达式错误: {e}")

        matches = []
        for i, line in enumerate(all_lines, start=1):
            if level_re and not level_re.search(line):
                continue
            if pat_re and not pat_re.search(line):
                continue
            matches.append(f"[{i}] {line.rstrip(chr(10)).rstrip(chr(13))}")
            if len(matches) >= lines:
                break

        if not matches:
            return f"# {path}: 无匹配（level={level or 'ALL'}, pattern={pattern or 'ALL'}），共扫描 {len(all_lines)} 行\n"
        return "\n".join(matches) + f"\n# --- 匹配 {len(matches)} 行 / 文件总 {len(all_lines)} 行（level={level or 'ALL'}）---"

    # 多格式级别识别（支持 Python logging / logback 方括号 / mms SLOGALWAYS）
    _LEVEL_PATTERNS = {
        "pipe": re.compile(r"\|\s*([A-Z]+)\s*\|"),          # | ERROR |
        "bracket": re.compile(r"\[(ERROR|WARN|WARNING|INFO|DEBUG|TRACE)\s*\]"),  # [ERROR] [WARN ]
    }
    # 异常关键词（不受级别标记限制，用于识别 mms 等自定义级别格式中的失败线索）
    ANOMALY_KEYWORDS = (
        "failed", "not found", "exception", "traceback", "error", "timeout",
        "refused", "violates", "失败", "异常", "超时", "错误", "拒绝",
    )

    @classmethod
    def _detect_level(cls, line: str) -> str:
        """多格式级别识别，返回标准化级别名或空串。

        - '| ERROR |' → ERROR（Python logging）
        - '[ERROR]' / '[WARN ]' → ERROR / WARNING（logback）
        - 'SLOGALWAYS' → WARNING（mms 固定告警级别，映射为 WARNING 便于统一告警）
        """
        m = cls._LEVEL_PATTERNS["pipe"].search(line)
        if m:
            return m.group(1)
        m = cls._LEVEL_PATTERNS["bracket"].search(line)
        if m:
            lvl = m.group(1)
            if lvl == "WARN":
                return "WARNING"
            return lvl
        if "SLOGALWAYS" in line:
            return "WARNING"
        return ""

    @classmethod
    def _has_anomaly_keyword(cls, line: str) -> bool:
        """判断是否命中异常关键词（不依赖级别标记）"""
        low = line.lower()
        return any(k in low for k in cls.ANOMALY_KEYWORDS)

    @classmethod
    def _pattern_of(cls, line: str) -> str:
        """从一行日志提取可聚合的消息模式。

        优先级:
          1. '-->>' 后的消息（logback 业务错误，如 '查询训练状态失败'）
          2. FeignException 行 → 提取 [METHOD] to [URL] 与调用方法
          3. Python logging '| LEVEL | module | message' → module + message
          4. 关键词失败行（failed/not found 等）→ 去掉行号/时间戳后的前 80 字符
          5. 兜底：去掉行号/时间戳后的前 60 字符
        """
        # 1. -->> 消息
        m = re.search(r'-->>(.+)$', line)
        if m:
            return m.group(1).strip()[:80] or "EMPTY_MSG"
        # 2. FeignException
        if "FeignException" in line:
            m = re.search(r'\[(GET|POST|PUT|DELETE|PATCH)\] to \[([^\]]+)\]', line)
            if m:
                return f"Feign{m.group(1)} {m.group(2)[:70]}"
            return "FeignException"
        # 3. Python logging 格式
        m = re.search(r'\|\s*[A-Z]+\s*\|\s*([^\s|]+)\s*\|(.+)$', line)
        if m:
            return f"{m.group(1)}: {m.group(2).strip()[:70]}"
        # 4. 去掉行号/时间戳（并归一化 32 位 hash，让带随机 id 的同类消息可聚合）
        t = re.sub(r'^\[\d+\]\s*', '', line)
        t = re.sub(r'^\S+\s+\S+\s+', '', t)
        t = re.sub(r'^\s+', '', t).strip()
        t = re.sub(r'[0-9a-f]{32}', '<hash>', t)
        if t:
            return t[:80]
        return "EMPTY_LINE"

    @classmethod
    def _is_noise_line(cls, line: str) -> bool:
        """判断是否为噪音行（堆栈帧/JSON 字段等），聚类时跳过"""
        t = line.strip()
        if not t:
            return True
        if t.startswith("at ") or t.startswith("at\t"):      # Java 堆栈帧
            return True
        if t.startswith('File "'):                            # Python 堆栈帧
            return True
        if "Traceback" in t or "recent call last" in t:       # 异常头/堆栈提示
            return True
        if "was the direct cause of" in t:                    # Python 异常链提示
            return True
        if t.startswith('"errors"'):                          # JSON 响应字段噪音
            return True
        return False

    def cluster_anomalies(self, path: str, levels: str = "ERROR,WARNING", top: int = 10) -> str:
        """对文件中的异常行按消息模式聚类（多格式级别识别 + 模式提取）。

        返回文本摘要（含级别、模式、计数、样例行号），供增量分析附注使用，
        解决单一模式刷屏时逐行告警/阅读效率低的问题。
        """
        filepath = self.resolve_path(path)
        if not filepath.is_file():
            raise ValueError(f"文件不存在: {path}")

        wanted = {l.strip().upper() for l in levels.split(",") if l.strip()}
        agg: dict[tuple[str, str], list[int]] = {}  # (level, pattern) -> [行号...]
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                lvl = self._detect_level(line)
                if lvl in wanted:
                    # SLOGALWAYS 级别行本身无信息量，跳过（下一行才是具体失败）
                    if "SLOGALWAYS" in line:
                        continue
                    pat = self._pattern_of(line)
                    agg.setdefault((lvl, pat), []).append(i)
                elif self._has_anomaly_keyword(line) and not line.lstrip().startswith('#'):
                    # 无级别标记但命中异常关键词（如 mms 失败行），归类为「未标记」
                    if self._is_noise_line(line):
                        continue
                    # 明确 INFO/DEBUG 级别的业务日志（如含"超时检测"字样），不算异常
                    if re.search(r'\[(INFO|DEBUG|TRACE)\s*\]', line):
                        continue
                    pat = self._pattern_of(line)
                    agg.setdefault(("未标记", pat), []).append(i)

        ranked = sorted(agg.items(), key=lambda kv: -len(kv[1]))[:top]
        if not ranked:
            return "# 异常模式聚类: 无\n"

        out = ["# 异常模式聚类 (级别 x 模式 x 计数):"]
        for (lvl, pat), lines in ranked:
            example = lines[0]
            out.append(f"#   [{lvl}] {pat} x{len(lines)} (例: 行{example})")
        return "\n".join(out) + "\n"

    def stats(self, path: str, levels: str = "ERROR,WARNING") -> str:
        """轻量统计：文件级 + 级别计数 + 模块分布 + 异常关键词计数（只数数，不下结论）

        级别识别支持多格式：Python logging(| ERROR |)、logback([ERROR]/[WARN ])、
        mms SLOGALWAYS（映射为 WARNING）。另统计异常关键词（failed/exception/失败等），
        避免自定义级别格式的失败日志漏报。
        """
        filepath = self.resolve_path(path)
        if not filepath.is_file():
            raise ValueError(f"文件不存在: {path}")

        wanted = {l.strip().upper() for l in levels.split(",") if l.strip()}
        invalid = wanted - set(self.LEVELS)
        if invalid:
            raise ValueError(f"未知级别: {', '.join(sorted(invalid))}（可选 {', '.join(self.LEVELS)}）")

        count_by_level = {l: 0 for l in wanted}
        count_by_module: dict[str, int] = {}
        anomaly_count = 0
        total_lines = 0
        module_pattern = re.compile(r"\|\s*[A-Z]+\s*\|\s*([\w.]+)")

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                total_lines += 1
                lvl = self._detect_level(line)
                if lvl in wanted:
                    count_by_level[lvl] += 1
                if self._has_anomaly_keyword(line):
                    anomaly_count += 1
                mod = module_pattern.search(line)
                if mod:
                    module = mod.group(1)
                    count_by_module[module] = count_by_module.get(module, 0) + 1

        top_modules = sorted(count_by_module.items(), key=lambda x: -x[1])[:10]
        result = [
            f"# {path} 统计",
            f"总行数: {total_lines}",
            f"级别计数: {', '.join(f'{k}={v}' for k, v in count_by_level.items())}",
            f"异常关键词命中: {anomaly_count}（failed/exception/失败/超时等）",
        ]
        if top_modules:
            result.append("Top 模块: " + ", ".join(f"{m}({c})" for m, c in top_modules))
        return "\n".join(result)
