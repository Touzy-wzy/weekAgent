#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志监控智能体 - 命令行入口（路线 A 单次批处理）

用法:
    python -m week_agent.log_monitor.run_log_check            # 完整分析并告警
    python -m week_agent.log_monitor.run_log_check --preview  # 仅预览提取的异常日志（不调 LLM）
    python -m week_agent.log_monitor.run_log_check --max-steps 8
"""

import argparse
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from week_agent.log_monitor.log_parser import parse_all, summarize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="日志监控智能体 - 单次批处理")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="仅预览提取到的异常日志记录，不调用 LLM",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=6,
        help="Agent 最大推理步数（默认 6）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="每个文件最多显示的异常记录条数（preview 用）",
    )
    args = parser.parse_args()

    # 先解析并统计（不依赖 LLM，保证至少能拿到异常集合）
    by_file = parse_all()
    total = sum(len(r) for r in by_file.values())
    err = sum(1 for r in by_file.values() for x in r if x.level == "ERROR")

    print("=" * 60)
    print("日志监控 Agent")
    print("=" * 60)
    for fp, recs in by_file.items():
        print(f"  {Path(fp).name}: {len(recs)} 条异常 (ERROR {sum(1 for r in recs if r.level=='ERROR')})")
    print(f"  合计: {total} 条（WARNING + ERROR）\n")

    if args.preview:
        # 仅预览，不调用 LLM
        from week_agent.log_monitor.log_parser import extract_watch_records

        for fp in by_file:
            print(f"\n===== {Path(fp).name} =====")
            recs = extract_watch_records(fp, max_records=args.limit)
            for r in recs:
                print(f"  [{r.level}] {r.timestamp} | {r.module} | {r.message[:100]}")
        print("\n预览完成（未调用 LLM）。")
        return 0

    # 完整分析
    try:
        from week_agent.log_monitor.agent import run_log_check

        print("\n开始 LLM 语义分析...\n")
        result = run_log_check(max_steps=args.max_steps)
        return 0
    except RuntimeError as e:
        print(f"\n❌ {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 分析失败: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())