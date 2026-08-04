"""DreamProcessor 定时任务脚本

用法：
    python -m week_agent.memory.run_dream [--dry-run]

功能：
    扫描 memory/*.md 文件，提取关键信息，生成摘要并追加到 MEMORY.md
"""

import argparse
import sys

from week_agent.memory.dream import DreamProcessor


def main():
    parser = argparse.ArgumentParser(description="运行 DreamProcessor 定时任务")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只生成摘要，不写入 MEMORY.md"
    )
    parser.add_argument(
        "--memory-dir",
        default="memory",
        help="memory 目录路径（默认: memory）"
    )
    parser.add_argument(
        "--memory-file",
        default="MEMORY.md",
        help="MEMORY.md 文件路径（默认: MEMORY.md）"
    )
    
    args = parser.parse_args()
    
    # 创建 DreamProcessor 实例
    processor = DreamProcessor()
    
    # 扫描 daily notes
    print(f"📂 扫描 {args.memory_dir} 目录...")
    notes = processor.scan_daily_notes(args.memory_dir)
    
    if not notes:
        print("ℹ️ 未找到 daily notes 文件")
        return
    
    print(f"📝 找到 {len(notes)} 个 daily notes 文件")
    
    # 提取关键信息
    print("🔍 提取关键信息...")
    facts = processor.extract_facts(notes)
    
    if not facts:
        print("ℹ️ 未提取到关键信息")
        return
    
    print(f"📋 提取到 {len(facts)} 条关键信息")
    
    # 生成摘要
    print("✍️ 生成摘要...")
    summary = processor.generate_summary(facts)
    
    if args.dry_run:
        print("\n" + "=" * 60)
        print("🔍 DRY RUN 模式 - 以下内容将写入 MEMORY.md：")
        print("=" * 60)
        print(summary)
        print("=" * 60)
    else:
        # 写入 MEMORY.md
        print(f"💾 写入 {args.memory_file}...")
        processor.update_memory(summary, args.memory_file)
        print("✅ 完成！")


if __name__ == "__main__":
    main()
