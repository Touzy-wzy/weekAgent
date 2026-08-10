# -*- coding: utf-8 -*-
"""增量分析运行器 - cron 定时任务入口

流程:
  1. 读取游标状态（cursor.json）
  2. 调用 LogDataAccess 获取当前文件信息（行数/mtime）
  3. 计算增量区间（新文件/增量/重置）
  4. 输出增量文本（供 LLM 分析）
  5. 可选: 将增量落盘，供 Agent 后续读取分析
  6. 更新游标并保存

用法（Agent 在 cron 任务中调用）:
  python incremental_runner.py --cursor <cursor.json> --out <dir> [--dry-run]
  python incremental_runner.py --cursor cursor.json --out inc/ --levels ERROR,WARNING

cron 示例（QwenPaw）:
  qwenpaw cron create --agent-id log-agent --schedule "*/30 * * * *" \
    "执行日志增量分析"
  → Agent 调用本脚本 + LLM 分析增量 + 告警
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from . import config
    from .cursor_manager import CursorManager
    from .engine import LogDataAccess
except ImportError:
    import config
    from cursor_manager import CursorManager
    from engine import LogDataAccess


def cleanup_old_batches(out_dir: Path, keep: int) -> int:
    """保留最近 keep 批增量文件，删除更旧批次（按文件名时间戳前缀分组）。

    返回删除的文件数。keep <= 0 时不清理。
    文件名格式: <YYYYmmdd_HHMMSS>_<relpath>.inc.txt
    """
    if keep <= 0 or not out_dir.is_dir():
        return 0
    import re
    batch_re = re.compile(r"^(\d{8}_\d{6})_")
    batches: dict[str, list[Path]] = {}
    for f in sorted(out_dir.glob("*.inc.txt")):
        m = batch_re.match(f.name)
        if m:
            batches.setdefault(m.group(1), []).append(f)
    sorted_keys = sorted(batches.keys())
    if len(sorted_keys) <= keep:
        return 0
    removed = 0
    for old in sorted_keys[:-keep]:
        for f in batches[old]:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    print(f"  已清理旧批次 {len(sorted_keys) - keep} 批 / {removed} 个文件（保留最近 {keep} 批）")
    return removed


def main():
    parser = argparse.ArgumentParser(description="增量日志分析运行器")
    parser.add_argument("--cursor", default="cursor.json", help="游标文件路径")
    parser.add_argument("--out", default="", help="增量输出目录（留空则不落盘）")
    parser.add_argument("--dry-run", action="store_true", help="只计算增量不更新游标")
    parser.add_argument("--max-lines", type=int, default=5000, help="单文件增量行数上限")
    parser.add_argument("--keep-batches", type=int, default=0,
                        help="落盘目录只保留最近 N 批增量文件（按时间戳批次，0=不清理）")
    parser.add_argument("--catch-up-strategy", choices=["sequential", "sample", "hybrid"],
                        default="hybrid",
                        help="超大增量(截断)时的追赶策略: "
                             "sequential=顺序读前 max-lines 行(不丢数据但可能追不上); "
                             "sample=对增量区间均匀采样 max-lines 行且游标直接推进到区间末尾(防积压, 只给全貌); "
                             "hybrid=增量 > max-lines*3 时自动用 sample, 否则 sequential(默认)")
    args = parser.parse_args()

    da = LogDataAccess()
    cm = CursorManager(args.cursor)

    # 1. 收集所有根目录下的 .log 文件信息（递归子目录）
    file_infos = {}
    for root in config.ALLOWED_ROOTS:
        for f in sorted(root.rglob("*.log")):
            rel = f"{root.name}/{f.relative_to(root).as_posix()}"
            try:
                info = da.file_info(rel)
            except ValueError:
                continue
            file_infos[rel] = {"lines": info["lines"], "mtime": info["mtime"]}

    # 2. 计算增量
    increments = cm.compute_increments(file_infos)
    active = [i for i in increments if i["kind"] != "unchanged"]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 扫描 {len(file_infos)} 个文件, "
          f"增量 {len(active)} 个")

    if not active:
        print("无新增内容，跳过")
        if not args.dry_run:
            cm.save()
        return

    # 3. 输出/落盘增量
    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for inc in active:
        rel = inc["path"]
        delta = inc["delta_lines"]
        if delta <= 0:
            continue
        truncated = False
        if delta > args.max_lines:
            print(f"  ⚠️ {rel}: 增量 {delta} 行超上限 {args.max_lines}，截断读取")
            delta = args.max_lines
            truncated = True

        # 追赶策略：超大增量时决定顺序读 or 区间均匀采样
        use_sample = False
        if truncated:
            if args.catch_up_strategy == "sample":
                use_sample = True
            elif args.catch_up_strategy == "hybrid" and inc["delta_lines"] > args.max_lines * 3:
                use_sample = True
                print(f"      → hybrid: 增量远超上限，改用区间均匀采样覆盖全貌，游标推进到区间末尾")

        if use_sample:
            text = da.sample_range(rel, start=inc["start"], lines=inc["delta_lines"],
                                   count=args.max_lines)
            cursor_end = inc["end"]
        else:
            try:
                text = da.read_file(rel, offset=inc["start"], lines=delta)
            except ValueError as e:
                print(f"  ❌ {rel}: {e}")
                continue
            cursor_end = inc["start"] + delta

        print(f"  [{inc['kind']}] {rel}: 行 {inc['start']}~{cursor_end} "
              f"({inc['delta_lines']} 行)")

        if truncated:
            # 截断时附加统计提示，避免 LLM 误以为已读完全部增量
            try:
                stat = da.stats(rel, levels="ERROR,WARNING")
                if use_sample:
                    note = f"# ⚠️ 增量共 {inc['delta_lines']} 行，本批为区间均匀采样 {delta} 行（游标已推进到区间末尾 {cursor_end}，防积压）\n# 全量统计参考:\n"
                else:
                    note = f"# ⚠️ 增量共 {inc['delta_lines']} 行，本批仅读取前 {delta} 行（游标只推进到 {cursor_end}，剩余下轮继续）\n# 全量统计参考:\n"
                text += note
                for line in stat.splitlines():
                    text += f"# {line}\n"
                # 异常模式聚类：解决单一模式刷屏时逐行阅读/告警效率低的问题
                try:
                    text += da.cluster_anomalies(rel, levels="ERROR,WARNING", top=10) + "\n"
                except ValueError:
                    pass
            except ValueError:
                pass

        if out_dir:
            # 文件名安全化
            safe = rel.replace("/", "__").replace("\\", "__")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = out_dir / f"{ts}_{safe}.inc.txt"
            out_file.write_text(text, encoding="utf-8")
            print(f"      → 已落盘 {out_file} ({len(text)} 字符)")

        # 更新游标（注意：sequential 只推进到实际读取的行数 start+delta，
        # 截断时剩余部分下轮继续读；sample 直接推进到区间末尾防止积压）
        if not args.dry_run:
            cm.set_cursor(rel, cursor_end, inc["mtime"])

    if not args.dry_run:
        cm.save()
        print(f"游标已更新: {args.cursor}")

    # 4. 清理旧批次（保留最近 N 批，防止 inc/ 无限增长）
    if out_dir:
        cleanup_old_batches(out_dir, args.keep_batches)


if __name__ == "__main__":
    main()
