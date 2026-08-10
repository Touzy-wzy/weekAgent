# -*- coding: utf-8 -*-
"""游标状态机 - 记录每个文件已分析到的位置，支持增量读取

cursor.json 结构:
{
  "version": 1,
  "last_run": "2026-08-10 00:30:00",
  "files": {
    "generated_logs/app_20260807_161614.log": {
      "lines": 2394,            # 已分析到的行数（下次从该行继续）
      "mtime": "2026-08-07 16:56:11",
      "status": "active"        # active / rotated / deleted
    }
  }
}

边界处理:
  - 文件行数 > 游标   → 有增量，返回增量区间
  - 文件行数 < 游标   → 文件被轮转/截断，游标重置为 0（重新全量）
  - 文件不存在        → status=deleted，清理
  - 新文件            → 游标为 0（首次全量或采样）
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class CursorManager:
    """增量游标管理器（Agent 侧状态，MCP 服务保持无状态）"""

    def __init__(self, cursor_path: str | Path):
        self.cursor_path = Path(cursor_path)
        self.data = self._load()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self.cursor_path.exists():
            try:
                with open(self.cursor_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"version": 1, "last_run": "", "files": {}}

    def save(self):
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        self.data["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.cursor_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # 游标读写
    # ------------------------------------------------------------------

    def get_cursor(self, rel_path: str) -> int:
        """返回该文件已分析到的行数（无记录返回 0）"""
        return self.data.get("files", {}).get(rel_path, {}).get("lines", 0)

    def set_cursor(self, rel_path: str, lines: int, mtime: str = "", status: str = "active"):
        self.data.setdefault("files", {})[rel_path] = {
            "lines": lines,
            "mtime": mtime,
            "status": status,
        }

    def remove(self, rel_path: str):
        self.data.get("files", {}).pop(rel_path, None)

    def all_files(self) -> dict[str, dict]:
        return self.data.get("files", {})

    # ------------------------------------------------------------------
    # 增量计算
    # ------------------------------------------------------------------

    def compute_increments(self, file_infos: dict[str, dict]) -> list[dict]:
        """对比当前文件信息与游标，计算增量区间。

        Args:
            file_infos: {rel_path: {"lines": int, "mtime": str}}

        Returns:
            [{path, start, end, delta_lines, kind}] 按修改时间顺序
            kind: new（新文件）/ increment（增量）/ reset（截断重置）/ unchanged（无变化）
        """
        cursor_files = self.all_files()
        known_paths = set(cursor_files.keys())
        current_paths = set(file_infos.keys())

        result = []
        # 1. 新文件（不在游标中）
        for path in sorted(current_paths - known_paths):
            info = file_infos[path]
            result.append({
                "path": path,
                "start": 0,
                "end": info["lines"],
                "delta_lines": info["lines"],
                "kind": "new",
                "mtime": info.get("mtime", ""),
            })

        # 2. 已知文件：对比行数
        for path in sorted(known_paths & current_paths):
            info = file_infos[path]
            cursor_lines = cursor_files[path].get("lines", 0)
            cur_lines = info["lines"]
            if cur_lines > cursor_lines:
                result.append({
                    "path": path,
                    "start": cursor_lines,
                    "end": cur_lines,
                    "delta_lines": cur_lines - cursor_lines,
                    "kind": "increment",
                    "mtime": info.get("mtime", ""),
                })
            elif cur_lines < cursor_lines:
                # 被轮转/截断：重置游标重新全量
                result.append({
                    "path": path,
                    "start": 0,
                    "end": cur_lines,
                    "delta_lines": cur_lines,
                    "kind": "reset",
                    "mtime": info.get("mtime", ""),
                })
            # else: unchanged，跳过

        # 3. 已删除文件（标记，不返回增量）
        for path in sorted(known_paths - current_paths):
            cursor_files[path]["status"] = "deleted"

        return result


def demo():
    """快速自测"""
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "cursor.json"
    cm = CursorManager(tmp)

    # 新文件
    incs = cm.compute_increments({
        "generated_logs/app.log": {"lines": 100, "mtime": "2026-08-10 00:00:00"},
    })
    assert len(incs) == 1 and incs[0]["kind"] == "new" and incs[0]["start"] == 0 and incs[0]["end"] == 100

    # 模拟分析完 100 行后更新游标
    cm.set_cursor("generated_logs/app.log", 100, "2026-08-10 00:00:00")
    cm.save()

    # 又新增 50 行 → 增量 100~150
    incs = cm.compute_increments({
        "generated_logs/app.log": {"lines": 150, "mtime": "2026-08-10 00:10:00"},
    })
    assert len(incs) == 1 and incs[0]["kind"] == "increment" and incs[0]["start"] == 100 and incs[0]["end"] == 150

    # 文件被截断为 30 行 → reset
    incs = cm.compute_increments({
        "generated_logs/app.log": {"lines": 30, "mtime": "2026-08-10 01:00:00"},
    })
    assert len(incs) == 1 and incs[0]["kind"] == "reset" and incs[0]["start"] == 0 and incs[0]["end"] == 30

    # 文件删除 → 标记 deleted
    cm.compute_increments({})
    assert cm.all_files()["generated_logs/app.log"]["status"] == "deleted"

    print("cursor_manager 自测通过 ✅")


if __name__ == "__main__":
    demo()
