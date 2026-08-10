# -*- coding: utf-8 -*-
"""日志生成器 - 独立后台进程

模拟生产环境持续产生日志，与 MCP Server 完全解耦。

用法:
    python run_generator.py                          # 默认 5条/秒
    python run_generator.py --rate 10                # 10条/秒
    python run_generator.py --rate 20 --error 0.1    # 20条/秒，10%错误率
    python run_generator.py --batch 1000             # 一次性生成 1000 条后退出
    python run_generator.py --output ./my_logs       # 输出到指定目录
"""

import argparse
import signal
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中（方便直接运行此脚本）
_project_root = Path(__file__).parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from log_generator.engine import LogGenerator
from log_generator import config


def main():
    parser = argparse.ArgumentParser(
        description="日志生成器 - 模拟生产环境持续产出日志",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_generator.py                             # 持续运行，5条/秒
  python run_generator.py --rate 10                   # 10条/秒
  python run_generator.py --batch 1000                # 生成 1000 条后退出
  python run_generator.py --rate 20 --error 0.1        # 20条/秒，10%错误率
        """,
    )
    parser.add_argument(
        "--rate", "-r",
        type=float,
        default=config.DEFAULT_RATE,
        help=f"每秒生成条数 (默认: {config.DEFAULT_RATE})",
    )
    parser.add_argument(
        "--error", "-e",
        type=float,
        default=config.DEFAULT_ERROR_RATIO,
        help=f"错误率 0.0-1.0 (默认: {config.DEFAULT_ERROR_RATIO})",
    )
    parser.add_argument(
        "--warning", "-w",
        type=float,
        default=config.DEFAULT_WARNING_RATIO,
        help=f"警告率 0.0-1.0 (默认: {config.DEFAULT_WARNING_RATIO})",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=str(config.LOG_OUTPUT_DIR),
        help=f"日志输出目录 (默认: {config.LOG_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--batch", "-b",
        type=int,
        default=0,
        help="批量生成指定条数后退出（0=持续运行）",
    )
    parser.add_argument(
        "--rotate-hours",
        type=int,
        default=config.DEFAULT_ROTATE_HOURS,
        help=f"文件轮转间隔/小时 (默认: {config.DEFAULT_ROTATE_HOURS})",
    )

    args = parser.parse_args()

    # 参数校验
    if not (0 <= args.error <= 1):
        print("错误: --error 必须在 0.0-1.0 之间", file=sys.stderr)
        sys.exit(1)
    if not (0 <= args.warning <= 1):
        print("错误: --warning 必须在 0.0-1.0 之间", file=sys.stderr)
        sys.exit(1)
    if args.error + args.warning > 1.0:
        print("警告: error + warning > 1.0，所有日志都将是 ERROR 或 WARNING", file=sys.stderr)

    # 创建生成器
    gen = LogGenerator(
        output_dir=args.output,
        error_ratio=args.error,
        warning_ratio=args.warning,
        rotate_hours=args.rotate_hours,
    )

    print(f"[日志生成器]")
    print(f"  速率:      {args.rate} 条/秒")
    print(f"  错误率:    {args.error*100:.1f}%")
    print(f"  警告率:    {args.warning*100:.1f}%")
    print(f"  输出目录:  {Path(args.output).resolve()}")
    print(f"  轮转间隔:  {args.rotate_hours} 小时")

    if args.batch > 0:
        # 批量模式
        print(f"  模式:      批量生成 {args.batch} 条")
        print()
        start = time.time()
        gen.generate_batch(args.batch)
        elapsed = time.time() - start
        print(f"完成! 生成 {args.batch} 条日志，耗时 {elapsed:.1f}s")
        files = gen.list_files()
        if files:
            print(f"输出文件: {files[0].name} ({files[0].stat().st_size / 1024:.1f} KB)")
    else:
        # 持续模式
        print(f"  模式:      持续运行 (Ctrl+C 停止)")
        print()

        def _handle_signal(sig, frame):
            print("\n正在停止日志生成器...")
            gen.stop()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        gen.start(rate=args.rate)
        print("日志生成器已启动，按 Ctrl+C 停止...")

        try:
            while gen.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            gen.stop()
            print("日志生成器已停止。")
            files = gen.list_files()
            if files:
                print(f"最新输出: {files[0].name} ({files[0].stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()