# -*- coding: utf-8 -*-
"""MCP Server - 日志数据访问服务（Resource + Tool 双通道）

对外提供:
  Resource "log://files"               → 列出所有日志文件（兼容旧客户端）
  Resource Template "log://{path}"     → 读取指定文件（兼容旧客户端）
  Tool  list_roots / list_dir / list_files / file_info
  Tool  read_file / head / tail / sample / extract / stats

客户端标识符: log_generator
显示名称:     日志数据访问
"""

import os
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

try:
    from . import config
    from .engine import LogDataAccess
except ImportError:
    import config
    from engine import LogDataAccess

# ---------------------------------------------------------------------------
# FastMCP 实例
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "log_generator",
    instructions=(
        "日志数据访问服务（只读）。\n"
        "1) list_roots 查看可访问的根目录白名单；\n"
        "2) list_dir 浏览目录结构；\n"
        "3) read_file/head/tail/sample/extract 读取文件内容（所有 path 为相对根目录的相对路径）；\n"
        "4) stats/file_info 做轻量统计。\n"
        "路径示例: generated_logs/app_20260807_161614.log"
    ),
    stateless_http=True,  # 禁用 OAuth，纯数据访问无需认证
)

# 共享的数据访问器
_data = LogDataAccess()


# ---------------------------------------------------------------------------
# Resource: log://files - 列出所有日志文件（兼容旧客户端）
# ---------------------------------------------------------------------------

@mcp.resource("log://files")
def list_log_files() -> str:
    """列出所有可用的日志文件（名称、大小、修改时间）"""
    lines = [f"共 {len(config.ALLOWED_ROOTS)} 个根目录:"]
    for root in config.ALLOWED_ROOTS:
        files = sorted(root.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        lines.append(f"[{root.name}] ({len(files)} 个 .log 文件)")
        for f in files[:20]:
            try:
                stat = f.stat()
                size_mb = stat.st_size / (1024 * 1024)
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"  {f.name}  ({size_mb:.1f}MB, {mtime})")
            except OSError:
                lines.append(f"  {f.name}")
        if len(files) > 20:
            lines.append(f"  ... 等共 {len(files)} 个文件")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Resource Template: log://{path} - 读取指定文件（兼容旧客户端）
# ---------------------------------------------------------------------------

@mcp.resource("log://{path}")
def read_log_resource(path: str) -> str:
    """读取指定日志文件的内容（默认开头 500 行，带行号）"""
    return _data.read_file(path, offset=0, lines=config.MCP_READ_MAX_LINES)


# ---------------------------------------------------------------------------
# Tool: 目录与文件发现
# ---------------------------------------------------------------------------

@mcp.tool()
def list_roots() -> str:
    """列出所有可访问的根目录白名单（名称、路径、条目数）。

    Agent 应首先调用本工具了解数据访问范围，再进行目录浏览或文件读取。
    """
    roots = _data.list_roots()
    if not roots:
        return "（无可访问根目录，请检查服务端 ALLOWED_ROOTS 配置）"
    lines = [f"共 {len(roots)} 个根目录:"]
    for r in roots:
        if "error" in r:
            lines.append(f"  {r['name']}  ({r['path']})  [访问异常: {r['error']}]")
        else:
            lines.append(f"  {r['name']}  ({r['path']})  子目录 {r['dirs']} / 文件 {r['files']}")
    return "\n".join(lines)


@mcp.tool()
def list_dir(path: str = "", pattern: str = "*") -> str:
    """浏览指定目录的内容（子目录 + 文件）。

    Args:
        path: 相对根目录的路径；为空时列出所有根目录。示例: "generated_logs"、"log_files/sub"
        pattern: 文件匹配模式（glob），默认 * 全部
    """
    try:
        entries = _data.list_dir(path, pattern)
    except ValueError as e:
        return f"错误: {e}"

    if not path or path in (".", "/"):
        return "\n".join(f"  {e['name']}  ({e['path']})  子目录 {e['dirs']} / 文件 {e['files']}" for e in entries)

    lines = [f"目录 {path}（{len(entries)} 项）:"]
    for e in entries:
        if e["type"] == "dir":
            lines.append(f"  [目录] {e['name']}  ({e['path']})  {e['mtime']}")
        else:
            lines.append(f"  [文件] {e['name']}  ({e['size_mb']}MB, {e['mtime']})  -> {e['path']}")
    return "\n".join(lines)


@mcp.tool()
def list_files(pattern: str = "*.log", recursive: bool = False) -> str:
    """列出所有根目录下的日志文件（按修改时间倒序）。

    Args:
        pattern: glob 匹配模式，默认 *.log
        recursive: 是否递归子目录（如 log_files/mms 下的文件），默认 False
    """
    lines = []
    for root in config.ALLOWED_ROOTS:
        if recursive:
            files = sorted(root.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        else:
            files = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        lines.append(f"[{root.name}] 共 {len(files)} 个匹配文件:")
        for f in files[:30]:
            try:
                stat = f.stat()
                size_mb = stat.st_size / (1024 * 1024)
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                rel = f.relative_to(root).as_posix()
                lines.append(f"  {rel}  ({size_mb:.2f}MB, {mtime})")
            except OSError:
                lines.append(f"  {f.name}")
        if len(files) > 30:
            lines.append(f"  ... 等共 {len(files)} 个文件")
    return "\n".join(lines) or "（无匹配文件）"


@mcp.tool()
def file_info(path: str) -> str:
    """返回文件基本信息（行数/大小/修改时间）。

    增量读取的关键工具：先 file_info 拿当前总行数，与游标对比得出增量区间，
    再用 read_file(offset=游标, lines=增量) 读取新增部分。

    Args:
        path: 相对根目录的路径，如 "generated_logs/app_20260807_161614.log"
    """
    try:
        info = _data.file_info(path)
    except ValueError as e:
        return f"错误: {e}"
    return (
        f"文件: {info['path']}\n"
        f"绝对路径: {info['abs_path']}\n"
        f"大小: {info['size']} bytes ({info['size_mb']}MB)\n"
        f"总行数: {info['lines']}\n"
        f"修改时间: {info['mtime']}"
    )


# ---------------------------------------------------------------------------
# Tool: 行级读取
# ---------------------------------------------------------------------------

@mcp.tool()
def read_file(path: str, offset: int = 0, lines: int = 200, max_bytes: int = 0) -> str:
    """分页读取文件内容（带行号）。

    增量读取核心：offset 作为游标，只读取该位置之后的行；返回带行号便于溯源。

    Args:
        path: 相对根目录的路径
        offset: 起始行号（0-based），默认 0
        lines: 读取行数，默认 200，最大 5000
        max_bytes: 响应体字节上限（0 表示用服务端默认 500KB）
    """
    if lines > 5000:
        lines = 5000
    try:
        return _data.read_file(path, offset=offset, lines=lines, max_bytes=max_bytes)
    except ValueError as e:
        return f"错误: {e}"


@mcp.tool()
def head(path: str, lines: int = 50) -> str:
    """读取文件开头 N 行（带行号），用于理解日志格式与上下文。"""
    if lines > 5000:
        lines = 5000
    try:
        return _data.head(path, lines)
    except ValueError as e:
        return f"错误: {e}"


@mcp.tool()
def tail(path: str, lines: int = 50) -> str:
    """读取文件末尾 N 行（带行号），用于查看最新日志。"""
    if lines > 5000:
        lines = 5000
    try:
        return _data.tail(path, lines)
    except ValueError as e:
        return f"错误: {e}"


@mcp.tool()
def sample(path: str, strategy: str = "head", count: int = 50) -> str:
    """多策略采样，供 LLM 在文件较大时快速了解全貌。

    Args:
        path: 相对根目录的路径
        strategy: head（开头）/ tail（末尾）/ random（随机）/ evenly（均匀覆盖）
        count: 采样行数，默认 50
    """
    if count > 1000:
        count = 1000
    try:
        return _data.sample(path, strategy=strategy, count=count)
    except ValueError as e:
        return f"错误: {e}"


# ---------------------------------------------------------------------------
# Tool: 筛选与统计
# ---------------------------------------------------------------------------

@mcp.tool()
def extract(path: str, level: str = "", pattern: str = "", lines: int = 200) -> str:
    """按级别/正则筛选原始行（返回带行号原文，不做聚类）。

    Args:
        path: 相对根目录的路径
        level: 级别过滤，如 ERROR / WARNING / INFO（留空 = 全部）
        pattern: 正则表达式过滤（留空 = 全部）
        lines: 最多返回行数，默认 200
    """
    if lines > 5000:
        lines = 5000
    try:
        return _data.extract(path, level=level, pattern=pattern, lines=lines)
    except ValueError as e:
        return f"错误: {e}"


@mcp.tool()
def stats(path: str, levels: str = "ERROR,WARNING") -> str:
    """轻量统计：总行数 + 级别计数 + Top 模块（只数数，不下结论）。"""
    try:
        return _data.stats(path, levels=levels)
    except ValueError as e:
        return f"错误: {e}"
