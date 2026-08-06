# -*- coding: utf-8 -*-
"""
LogAn 预处理 + 模板生成 测试脚本
数据源: E:\weekAgent\qwenpaw.log
"""

import os
import sys
import json
import time
import pandas as pd

# 添加 LogAn 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "LogAn"))

# 禁用 pandarallel 避免 Windows 多进程问题
os.environ["LOGAN_DISABLE_PANDARALLEL"] = "1"

from logan.preprocessing.preprocessing import Preprocessing
from logan.drain.run_drain import Templatizer

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
INPUT_FILE = r"E:\weekAgent\qwenpaw.log"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "logan_test_output")
DRAIN_CONFIG = os.path.join(os.path.dirname(__file__), "LogAn", "logan", "drain", "drain3.ini")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "developer_debug_files"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "metrics"), exist_ok=True)

print("=" * 70)
print("  LogAn 预处理 + 模板生成 测试")
print("=" * 70)
print(f"\n输入文件: {INPUT_FILE}")
print(f"输出目录: {OUTPUT_DIR}")
print(f"Drain3 配置: {DRAIN_CONFIG}")

# ---------------------------------------------------------------------------
# Step 1: 预处理 (Preprocessing)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  Step 1: 预处理 - 日志解析、时间戳提取、文本清洗")
print("=" * 70)

t0 = time.time()

preprocessor = Preprocessing(debug_mode="true", quiet=False)
preprocessor.preprocess(
    input_files=[INPUT_FILE],
    time_range="all-data",
    output_dir=OUTPUT_DIR,
    process_all_files=False,
    process_log_files=True,
    process_txt_files=False,
)

df = preprocessor.df
t1 = time.time()

print(f"\n预处理耗时: {(t1 - t0) * 1000:.0f} ms")
print(f"预处理后日志条数: {len(df)}")

if df is None or len(df) == 0:
    print("错误: 预处理后无数据！")
    sys.exit(1)

# 展示 DataFrame 列信息
print(f"\nDataFrame 列: {list(df.columns)}")
print(f"数据概况:")
print(f"  - 时间范围: {df['epoch'].min():.0f} ~ {df['epoch'].max():.0f}")
from datetime import datetime
min_ts = datetime.fromtimestamp(df['epoch'].min()).strftime('%Y-%m-%d %H:%M:%S')
max_ts = datetime.fromtimestamp(df['epoch'].max()).strftime('%Y-%m-%d %H:%M:%S')
print(f"  - 可读时间: {min_ts} ~ {max_ts}")

# 展示预处理后的样本数据
print(f"\n预处理后样本 (前5条):")
print("-" * 70)
for i, row in df.head(5).iterrows():
    text = str(row.get('text', ''))[:120]
    pp_text = str(row.get('preprocessed_text', ''))[:100]
    print(f"[{i}] 原始: {text}")
    print(f"    预处理后: {pp_text}")
    print()

# ---------------------------------------------------------------------------
# Step 2: 模板生成 (Drain3 Templatizer)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  Step 2: 模板生成 - Drain3 聚类")
print("=" * 70)

t2 = time.time()

templatizer = Templatizer(debug_mode="true", config_path=DRAIN_CONFIG)
templatizer.miner(df, OUTPUT_DIR)

t3 = time.time()
print(f"\n模板生成耗时: {(t3 - t2) * 1000:.0f} ms")

df_templated = templatizer.df
print(f"模板化后记录数: {len(df_templated)}")

# ---------------------------------------------------------------------------
# Step 3: 结果分析
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  Step 3: 模板聚类结果分析")
print("=" * 70)

# 统计模板
if 'test_ids' in df_templated.columns:
    template_counts = df_templated['test_ids'].value_counts()
    unique_templates = template_counts.index.tolist()
    print(f"\n唯一模板数: {len(unique_templates)}")
    print(f"模板聚类覆盖率: {len(df_templated[df_templated['test_ids'] != -1])}/{len(df_templated)}")

    # 按出现次数排序展示模板
    print(f"\n{'='*70}")
    print(f"  模板明细 (按出现次数降序，最多展示30个)")
    print(f"{'='*70}")

    if 'template_str' in df_templated.columns:
        # 构建模板摘要
        template_summary = {}
        for tid in unique_templates:
            subset = df_templated[df_templated['test_ids'] == tid]
            template_str = subset['template_str'].iloc[0] if len(subset) > 0 else "N/A"
            count = len(subset)
            # 取一条原始日志作为示例
            sample_text = subset['text'].iloc[0][:200] if 'text' in subset.columns else "N/A"
            template_summary[tid] = {
                'template': template_str,
                'count': count,
                'sample': sample_text,
            }

        # 按出现次数排序
        sorted_templates = sorted(template_summary.items(), key=lambda x: x[1]['count'], reverse=True)

        for rank, (tid, info) in enumerate(sorted_templates[:30], 1):
            print(f"\n--- 模板 #{rank} | Cluster ID: {tid} | 出现次数: {info['count']} ---")
            print(f"  模板: {info['template'][:150]}")
            print(f"  示例: {info['sample'][:150]}")

    # 统计模板频次分布
    print(f"\n{'='*70}")
    print(f"  模板频次分布")
    print(f"{'='*70}")
    freq_dist = template_counts.value_counts().sort_index()
    for freq, count in freq_dist.items():
        bar = "#" * min(count, 60)
        print(f"  出现{freq:>4}次的模板: {count:>3}个  {bar}")

    # 展示 Top 10 高频模板的变量信息
    if 'variables' in df_templated.columns:
        print(f"\n{'='*70}")
        print(f"  Top 10 高频模板 - 变量示例")
        print(f"{'='*70}")
        for rank, (tid, info) in enumerate(sorted_templates[:10], 1):
            subset = df_templated[df_templated['test_ids'] == tid]
            sample_vars = subset['variables'].iloc[0] if len(subset) > 0 else "[]"
            try:
                vars_parsed = json.loads(sample_vars) if isinstance(sample_vars, str) else sample_vars
                vars_str = ", ".join(vars_parsed[:5]) if vars_parsed else "(无变量)"
            except:
                vars_str = str(sample_vars)[:100]
            print(f"  #{rank} | ID={tid} | 次数={info['count']} | 变量: {vars_str}")

else:
    print("模板列 'test_ids' 不存在于 DataFrame 中")
    print(f"可用列: {list(df_templated.columns)}")

# ---------------------------------------------------------------------------
# 总结
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print(f"  测试总结")
print(f"{'='*70}")
print(f"  输入文件: {INPUT_FILE}")
print(f"  原始日志行数: 5890")
print(f"  预处理后日志条数: {len(df)}")
print(f"  唯一模板数: {len(unique_templates) if 'test_ids' in df_templated.columns else 'N/A'}")
print(f"  预处理耗时: {(t1 - t0) * 1000:.0f} ms")
print(f"  模板生成耗时: {(t3 - t2) * 1000:.0f} ms")
print(f"  总耗时: {(t3 - t0) * 1000:.0f} ms")
print(f"\n输出文件目录: {OUTPUT_DIR}")