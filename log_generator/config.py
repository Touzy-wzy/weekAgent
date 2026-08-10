# -*- coding: utf-8 -*-
"""日志生成器共享配置（环境变量可覆盖）"""

import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ---------------------------------------------------------------------------
# 日志输出目录
# ---------------------------------------------------------------------------
LOG_OUTPUT_DIR: Path = Path(
    os.getenv("LOG_GEN_DIR", str(PROJECT_ROOT / "generated_logs"))
)

# ---------------------------------------------------------------------------
# 日志格式
# ---------------------------------------------------------------------------
# 时间戳格式（毫秒）
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志行格式模板
LOG_LINE_FORMAT = "{timestamp},{ms:03d} | {level} | {module} | {message}"

# ---------------------------------------------------------------------------
# 生成器默认参数
# ---------------------------------------------------------------------------
DEFAULT_RATE: float = float(os.getenv("LOG_GEN_RATE", "1"))          # 条/秒
DEFAULT_ERROR_RATIO: float = float(os.getenv("LOG_GEN_ERROR_RATIO", "0.05"))  # 错误率 5%
DEFAULT_WARNING_RATIO: float = float(os.getenv("LOG_GEN_WARN_RATIO", "0.10"))  # 警告率 10%
DEFAULT_MAX_FILE_SIZE_MB: int = int(os.getenv("LOG_GEN_MAX_FILE_MB", "50"))   # 单文件最大 50MB
DEFAULT_ROTATE_HOURS: int = int(os.getenv("LOG_GEN_ROTATE_HOURS", "1"))       # 小时轮转

# ---------------------------------------------------------------------------
# MCP Server 参数
# ---------------------------------------------------------------------------
MCP_HOST: str = os.getenv("LOG_GEN_MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.getenv("LOG_GEN_MCP_PORT", "8899"))
MCP_READ_MAX_LINES: int = int(os.getenv("LOG_GEN_READ_MAX_LINES", "500"))  # 单次读取最多行数
MCP_READ_MAX_BYTES: int = int(os.getenv("LOG_GEN_READ_MAX_BYTES", str(500 * 1024)))  # 单次读取响应体上限（默认 500KB）

# ---------------------------------------------------------------------------
# 数据访问白名单根目录
# ---------------------------------------------------------------------------
# 说明：
#   - 支持多个根目录，MCP 只能访问这些目录内的文件（只读，无副作用）
#   - 每个根目录可以是绝对路径或相对 PROJECT_ROOT 的路径
#   - 环境变量 LOG_GEN_ROOTS 用分号(;)分隔覆盖默认值
#   - 所有相对路径参数都相对于这些根目录解析，且禁止路径穿越（..）
# ---------------------------------------------------------------------------
ALLOWED_ROOTS: list[Path] = [
    LOG_OUTPUT_DIR,                          # 默认日志生成目录
    Path(os.getenv("LOG_GEN_EXTRA_ROOT", "")).resolve()
    if os.getenv("LOG_GEN_EXTRA_ROOT")
    else PROJECT_ROOT / "log_files",         # 业务日志目录（存在则挂载）
]

_env_roots = os.getenv("LOG_GEN_ROOTS")
if _env_roots:
    ALLOWED_ROOTS = [
        (p if Path(p).is_absolute() else PROJECT_ROOT / p).resolve()
        for p in _env_roots.split(";")
        if p.strip()
    ]

# 去重并保留存在的目录（不存在则忽略，避免 list_roots 暴露无效路径）
_seen: set[str] = set()
_roots_dedup: list[Path] = []
for r in ALLOWED_ROOTS:
    key = str(r)
    if key in _seen:
        continue
    _seen.add(key)
    if r.is_dir():
        _roots_dedup.append(r)
ALLOWED_ROOTS = _roots_dedup