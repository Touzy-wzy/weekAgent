# -*- coding: utf-8 -*-
"""
三方案对比测试:
  A: LogAn 模板方案 (预处理+模板 → LLM)
  B: weekAgent 原始日志方案 (解析 → LLM)
  C: 完整 LogAn 管道 (预处理+模板+GS/FC分类+窗口合并 → LLM)

数据源: E:\weekAgent\app.log
模型: glm-4.5-air (智谱)
测试轮次: 5 次取平均
"""

import os
import sys
import json
import time
import statistics
import pandas as pd
import numpy as np
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "LogAn"))
sys.path.insert(0, os.path.dirname(__file__))
os.environ["LOGAN_DISABLE_PANDARALLEL"] = "1"

from openai import OpenAI

# ── 模型配置 ──────────────────────────────────────────────
LLM_MODEL = "glm-4.5-air"
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
LLM_API_KEY = "e2b2697a922b44719e41abf7fc91719c.pGNVtwOXY3Or1aj6"

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

INPUT_FILE = r"E:\weekAgent\app.log"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "logan_compare_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "developer_debug_files"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "metrics"), exist_ok=True)

# ── 公共分析 prompt 模板 ──────────────────────────────────
ANALYSIS_SYSTEM_PROMPT = """你是一个日志监控分析助手，负责分析日志中的异常记录，进行语义级判断并输出告警建议。

## 输出格式（严格按此格式输出）

```
【日志分析报告】
分析时间: {time}
日志文件: {file}

── 数据概况
总记录数: {total}
异常级别分布: {distribution}

── 异常分析
{analysis}

── 告警结论
需要告警: 是/否
严重级别: critical/warning/info
核心问题: {core_issue}
```

## 原则
- 只基于提供的日志内容判断，不要臆造
- 相同/重复异常应合并归类
- 关注真正影响系统的异常"""

# ── GS/FC 分类标签 ───────────────────────────────────────
GS_LABELS = ["information", "error", "availability", "latency", "saturation", "traffic"]
FC_LABELS = ["io", "authentication", "network", "application", "device", "other"]


def _llm_classify_gs(templates_dict):
    """用 LLM 对模板进行 Golden Signal 分类，返回 {template_id: gs_label}"""
    if not templates_dict:
        return {}

    # 构建分类 prompt
    lines = []
    for tid, (tmpl, sample) in templates_dict.items():
        sample_text = sample[:150] if sample else ""
        lines.append(f"[{tid}] 模板: {tmpl[:200]}\n    示例: {sample_text}")

    prompt = f"""请将以下每条日志模板分类为下列 Golden Signal 之一:
{json.dumps(GS_LABELS)}

分类规则:
- information: 普通信息日志，无异常
- error: 错误/异常日志
- availability: 服务可用性相关（宕机、重启、连接失败等）
- latency: 延迟/超时相关
- saturation: 资源饱和（内存、磁盘、CPU 满载等）
- traffic: 流量/请求量相关

模板列表:
{chr(10).join(lines)}

请严格按 JSON 格式返回，不要有其他文字:
{{"0": "information", "1": "error", ...}}"""

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        result_text = response.choices[0].message.content
        # 提取 JSON
        json_start = result_text.find("{")
        json_end = result_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(result_text[json_start:json_end])
            # 确保 key 是 int
            return {int(k): v for k, v in result.items()}
        return {}
    except Exception as e:
        print(f"    GS 分类失败: {e}")
        return {}


def _llm_classify_fc(templates_dict):
    """用 LLM 对非 Info 模板进行 Fault Category 分类，返回 {template_id: [fc_label]}"""
    if not templates_dict:
        return {}

    lines = []
    for tid, (tmpl, sample) in templates_dict.items():
        sample_text = sample[:150] if sample else ""
        lines.append(f"[{tid}] 模板: {tmpl[:200]}\n    示例: {sample_text}")

    prompt = f"""请将以下每条异常日志模板分类为下列 Fault Category 之一:
{json.dumps(FC_LABELS)}

分类规则:
- io: 磁盘 I/O、文件读写相关故障
- authentication: 认证、鉴权、权限相关故障
- network: 网络连接、通信相关故障
- application: 应用程序逻辑错误、异常
- device: 硬件/设备相关故障
- other: 无法归类到以上类别

模板列表:
{chr(10).join(lines)}

请严格按 JSON 格式返回，每个模板可以有多标签，不要有其他文字:
{{"0": ["network"], "1": ["application", "io"], ...}}"""

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        result_text = response.choices[0].message.content
        json_start = result_text.find("{")
        json_end = result_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(result_text[json_start:json_end])
            return {int(k): v for k, v in result.items()}
        return {}
    except Exception as e:
        print(f"    FC 分类失败: {e}")
        return {}


def _merge_sim_windows(windows):
    """
    合并具有相似错误 TID 集合的窗口（union-find 算法）
    输入: [(start_epoch, end_epoch, error_tids, text_output, file_names), ...]
    输出: 合并后的窗口列表
    """
    if len(windows) <= 1:
        return windows

    n = len(windows)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # 按 error_tids 集合大小降序排列
    indices = sorted(range(n), key=lambda i: len(windows[i][2]), reverse=True)
    error_sets = [set(w[2]) for w in windows]

    for i_idx, i in enumerate(indices):
        ri = find(i)
        for j_idx in range(i_idx + 1, len(indices)):
            j = indices[j_idx]
            rj = find(j)
            if ri == rj:
                continue
            if error_sets[rj].issubset(error_sets[ri]):
                parent[rj] = ri
            elif error_sets[ri].issubset(error_sets[rj]):
                parent[ri] = rj
                ri = rj

    # 收集合并结果
    groups = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(windows[i])

    merged = []
    for root, group in groups.items():
        group.sort(key=lambda x: x[0])  # 按时间排序
        start_epoch = group[0][0]
        end_epoch = group[-1][1]
        all_error_tids = set()
        all_text = []
        all_files = []
        for w in group:
            all_error_tids.update(w[2])
            all_text.append(w[3])
            all_files.append(w[4])
        merged.append((start_epoch, end_epoch, all_error_tids, "\n".join(all_text), "\n".join(all_files)))

    merged.sort(key=lambda x: x[0], reverse=True)
    return merged


# ═══════════════════════════════════════════════════════════
#  Approach A: LogAn 模板方案
# ═══════════════════════════════════════════════════════════

def approach_a_logan():
    """LogAn 预处理 + Drain3 模板 → LLM 分析"""
    from logan.preprocessing.preprocessing import Preprocessing
    from logan.drain.run_drain import Templatizer

    DRAIN_CONFIG = os.path.join(os.path.dirname(__file__), "LogAn", "logan", "drain", "drain3.ini")

    t_start = time.time()
    t_read_start = time.time()

    preprocessor = Preprocessing(debug_mode="false", quiet=True)
    preprocessor.preprocess(
        input_files=[INPUT_FILE],
        time_range="all-data",
        output_dir=OUTPUT_DIR,
        process_all_files=False,
        process_log_files=True,
        process_txt_files=False,
    )
    df = preprocessor.df
    t_preprocess_done = time.time()

    if df is None or len(df) == 0:
        return {"error": "预处理后无数据", "t_read_parse": t_preprocess_done - t_read_start}

    templatizer = Templatizer(debug_mode="false", config_path=DRAIN_CONFIG)
    templatizer.miner(df, OUTPUT_DIR)
    df_t = templatizer.df
    t_template_done = time.time()

    template_counts = df_t['test_ids'].value_counts().to_dict()
    unique_count = len(template_counts)

    template_summary_lines = []
    sorted_templates = sorted(template_counts.items(), key=lambda x: x[1], reverse=True)

    for tid, count in sorted_templates:
        subset = df_t[df_t['test_ids'] == tid]
        tmpl = str(subset['template_str'].iloc[0])[:200]
        sample = str(subset['original_text'].iloc[0])[:200] if 'original_text' in df_t.columns else ""
        line = f"模板#{tid} (出现{count}次): {tmpl}"
        if sample:
            line += f"\n  示例: {sample}"
        template_summary_lines.append(line)

    template_summary_text = "\n\n".join(template_summary_lines)

    level_dist = {}
    for _, row in df_t.iterrows():
        orig = str(row.get('original_text', ''))
        if '| ERROR' in orig or '| ERROR ' in orig:
            level_dist['ERROR'] = level_dist.get('ERROR', 0) + 1
        elif '| WARNING' in orig or '| WARNING ' in orig:
            level_dist['WARNING'] = level_dist.get('WARNING', 0) + 1
        elif '| INFO' in orig or '| INFO ' in orig:
            level_dist['INFO'] = level_dist.get('INFO', 0) + 1

    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    user_prompt = f"""以下是通过 Drain3 模板聚类算法对日志文件进行预处理后提取的模板摘要。

原始日志: {INPUT_FILE}
原始日志行数: 1919
预处理后记录数: {len(df_t)}
唯一模板数: {unique_count}
日志级别分布: {json.dumps(level_dist)}

── 模板列表（按出现次数降序）──

{template_summary_text}

请分析以上模板，判断哪些属于异常模式，给出告警结论。"""

    system_prompt = ANALYSIS_SYSTEM_PROMPT.format(
        time=now_str, file=INPUT_FILE,
        total=f"{len(df_t)}条 (原始1919行 → {unique_count}个模板)",
        distribution=json.dumps(level_dist), analysis="", core_issue=""
    )

    prompt_chars = len(system_prompt) + len(user_prompt)

    t_llm_start = time.time()
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.3, max_tokens=2048,
        )
        t_llm_done = time.time()
        usage = response.usage
        llm_result = response.choices[0].message.content

        return {
            "approach": "A-LogAn模板方案",
            "t_read_parse": t_preprocess_done - t_read_start,
            "t_template": t_template_done - t_preprocess_done,
            "t_llm": t_llm_done - t_llm_start,
            "t_total": t_llm_done - t_start,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
            "prompt_chars": prompt_chars,
            "template_count": unique_count,
            "record_count": len(df_t),
            "result_preview": (llm_result or "")[:500],
            "result_full": llm_result or "",
        }
    except Exception as e:
        return {
            "approach": "A-LogAn模板方案", "error": str(e),
            "t_read_parse": t_preprocess_done - t_read_start,
            "t_template": t_template_done - t_preprocess_done,
            "t_llm": time.time() - t_llm_start,
            "t_total": time.time() - t_start,
            "prompt_chars": prompt_chars,
            "template_count": unique_count, "record_count": len(df_t),
        }


# ═══════════════════════════════════════════════════════════
#  Approach B: weekAgent 原始日志方案
# ═══════════════════════════════════════════════════════════

def approach_b_weekagent():
    """weekAgent log_parser 解析 → 原始 WARNING/ERROR 记录 → LLM 分析"""
    from week_agent.log_monitor import log_parser

    t_start = time.time()
    t_read_start = time.time()

    recs = log_parser.parse_file(INPUT_FILE)
    warn_err_recs = [r for r in recs if r.level in ('WARNING', 'ERROR')]
    t_parse_done = time.time()

    level_dist = dict(Counter(r.level for r in warn_err_recs))

    max_records = 60
    selected = warn_err_recs[-max_records:] if len(warn_err_recs) > max_records else warn_err_recs

    log_lines = []
    for i, r in enumerate(selected):
        body = r.message
        if len(body) > 500:
            body = body[:500] + f" ...(截断, 原文{len(r.message)}字符)"
        log_lines.append(f"[{i+1}] {r.timestamp} | {r.level} | {r.module} | {body}")

    log_text = "\n".join(log_lines)

    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    user_prompt = f"""以下是从日志文件中提取的 WARNING/ERROR 级别异常记录。

日志文件: {INPUT_FILE}
原始日志行数: 1919
解析后记录数: {len(recs)}
WARNING/ERROR 记录数: {len(warn_err_recs)}（已截取最近{len(selected)}条）
级别分布: {json.dumps(level_dist)}

── 异常记录 ──

{log_text}

请逐条分析以上异常，判断严重程度，给出告警结论。"""

    system_prompt = ANALYSIS_SYSTEM_PROMPT.format(
        time=now_str, file=INPUT_FILE,
        total=f"{len(warn_err_recs)}条 WARNING/ERROR（共{len(recs)}条记录）",
        distribution=json.dumps(level_dist), analysis="", core_issue=""
    )

    prompt_chars = len(system_prompt) + len(user_prompt)

    t_llm_start = time.time()
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.3, max_tokens=2048,
        )
        t_llm_done = time.time()
        usage = response.usage
        llm_result = response.choices[0].message.content

        return {
            "approach": "B-weekAgent原始日志",
            "t_read_parse": t_parse_done - t_read_start,
            "t_llm": t_llm_done - t_llm_start,
            "t_total": t_llm_done - t_start,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
            "prompt_chars": prompt_chars,
            "record_count": len(warn_err_recs),
            "sent_count": len(selected),
            "result_preview": (llm_result or "")[:500],
            "result_full": llm_result or "",
        }
    except Exception as e:
        return {
            "approach": "B-weekAgent原始日志", "error": str(e),
            "t_read_parse": t_parse_done - t_read_start,
            "t_llm": time.time() - t_llm_start,
            "t_total": time.time() - t_start,
            "prompt_chars": prompt_chars,
            "record_count": len(warn_err_recs), "sent_count": len(selected),
        }


# ═══════════════════════════════════════════════════════════
#  Approach C: 完整 LogAn 管道 (预处理+模板+GS/FC分类+窗口合并 → LLM)
# ═══════════════════════════════════════════════════════════

def approach_c_logan_full():
    """完整 LogAn 管道: 预处理 + 模板 + GS/FC分类 + 窗口合并 → LLM 分析"""
    from logan.preprocessing.preprocessing import Preprocessing
    from logan.drain.run_drain import Templatizer

    DRAIN_CONFIG = os.path.join(os.path.dirname(__file__), "LogAn", "logan", "drain", "drain3.ini")

    t_start = time.time()

    # ── Step 1: 预处理 ──
    t_read_start = time.time()
    preprocessor = Preprocessing(debug_mode="false", quiet=True)
    preprocessor.preprocess(
        input_files=[INPUT_FILE],
        time_range="all-data",
        output_dir=OUTPUT_DIR,
        process_all_files=False,
        process_log_files=True,
        process_txt_files=False,
    )
    df = preprocessor.df
    t_preprocess_done = time.time()

    if df is None or len(df) == 0:
        return {"error": "预处理后无数据", "t_read_parse": t_preprocess_done - t_read_start}

    # ── Step 2: 模板生成 ──
    templatizer = Templatizer(debug_mode="false", config_path=DRAIN_CONFIG)
    templatizer.miner(df, OUTPUT_DIR)
    df_t = templatizer.df
    t_template_done = time.time()

    unique_count = df_t['test_ids'].nunique()

    # ── Step 3: GS 分类 (LLM 零样本) ──
    t_gs_start = time.time()
    # 为每个模板取代表性日志
    representative = df_t.groupby('test_ids').agg({
        'template_str': 'first',
        'original_text': 'first',
        'preprocessed_text': 'first',
    })
    templates_dict_gs = {}
    for tid, row in representative.iterrows():
        templates_dict_gs[tid] = (str(row['template_str']), str(row.get('original_text', '')))

    gs_map = _llm_classify_gs(templates_dict_gs)
    t_gs_done = time.time()

    # ── Step 4: FC 分类 (仅非 Info 模板) ──
    t_fc_start = time.time()
    non_info_templates = {}
    for tid, gs in gs_map.items():
        if gs != 'information' and gs != 'Info':
            if tid in templates_dict_gs:
                non_info_templates[tid] = templates_dict_gs[tid]

    fc_map = _llm_classify_fc(non_info_templates) if non_info_templates else {}
    t_fc_done = time.time()

    # ── Step 5: 构建 GS/FC 标签映射 ──
    # 为每条日志记录打上 GS/FC 标签
    gs_col = df_t['test_ids'].map(lambda tid: gs_map.get(tid, 'information'))
    fc_col = df_t['test_ids'].map(lambda tid: fc_map.get(tid, ['other']))

    # 确保 epoch 列存在
    if 'epoch' not in df_t.columns:
        return {"error": "缺少 epoch 列", "t_read_parse": t_preprocess_done - t_read_start}

    # ── Step 6: 30秒窗口分组 ──
    df_t = df_t.copy()
    df_t['gs'] = gs_col
    df_t['fc'] = fc_col
    df_t['group'] = (df_t['epoch'] // 30).astype(int)

    # 按窗口聚合
    window_groups = df_t.groupby('group').agg({
        'test_ids': lambda x: ' '.join(map(str, x)),
        'original_text': '\n'.join,
        'epoch': 'first',
        'gs': lambda x: ' '.join(x),
        'file_names': lambda x: '\n'.join(x) if 'file_names' in df_t.columns else '',
    }).reset_index()

    # 分离 Info 窗口和异常窗口
    window_groups['all_info'] = window_groups['gs'].apply(
        lambda gs: all(s.strip() in ('information', 'Info') for s in gs.split())
    )

    normal_windows = window_groups[window_groups['all_info'] == True]
    anomaly_windows_df = window_groups[window_groups['all_info'] != True].copy()

    # ── Step 7: 相似窗口合并 ──
    if len(anomaly_windows_df) > 0:
        windows = []
        for _, row in anomaly_windows_df.iterrows():
            error_tids = set()
            gs_list = row['gs'].split()
            tid_list = row['test_ids'].split()
            for tid_str, gs in zip(tid_list, gs_list):
                if gs.strip() not in ('information', 'Info'):
                    error_tids.add(tid_str)
            windows.append((
                row['epoch'], row['epoch'] + 30,
                error_tids,
                str(row['original_text']),
                str(row.get('file_names', ''))
            ))

        merged_windows = _merge_sim_windows(windows)
    else:
        merged_windows = []

    t_merge_done = time.time()

    # ── Step 8: 构建 GS 分布和 FC 分布 ──
    gs_dist = dict(Counter(gs_col.tolist()))
    fc_dist = {}
    for fcs in fc_col:
        for fc in (fcs if isinstance(fcs, list) else [fcs]):
            fc_dist[fc] = fc_dist.get(fc, 0) + 1

    # ── Step 9: 构建结构化的 LLM prompt ──
    from datetime import datetime
    # epoch 转时间字符串
    def epoch_to_str(ep):
        if pd.isna(ep):
            return "N/A"
        return datetime.utcfromtimestamp(float(ep)).strftime('%Y-%m-%d %H:%M:%S')

    # 异常窗口摘要
    anomaly_lines = []
    for i, (start_ep, end_ep, error_tids, text, files) in enumerate(merged_windows[:30]):  # 最多30个窗口
        anomaly_lines.append(
            f"异常窗口#{i+1} [{epoch_to_str(start_ep)} ~ {epoch_to_str(end_ep)}]\n"
            f"  涉及错误模板: {', '.join(sorted(error_tids)[:10])}\n"
            f"  代表性日志:\n    {text[:500]}"
        )

    anomaly_text = "\n\n".join(anomaly_lines) if anomaly_lines else "无异常窗口"

    # 模板 GS 摘要
    gs_summary_lines = []
    for tid, gs in sorted(gs_map.items(), key=lambda x: (x[1], x[0])):
        fc = fc_map.get(tid, ['other'])
        tmpl = templates_dict_gs.get(tid, ('', ''))[0][:150]
        sample = templates_dict_gs.get(tid, ('', ''))[1][:150]
        gs_summary_lines.append(f"  模板#{tid} [{gs}] FC:{fc} | {tmpl}")
        if sample:
            gs_summary_lines.append(f"    示例: {sample}")

    # 限制长度
    gs_summary_text = "\n".join(gs_summary_lines[:100])

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    user_prompt = f"""以下是通过完整 LogAn 管道处理后的日志分析摘要，包含 Golden Signal 分类、Fault Category 分类和异常窗口合并。

原始日志: {INPUT_FILE}
预处理后记录数: {len(df_t)}
唯一模板数: {unique_count}
正常窗口数: {len(normal_windows)}
异常窗口数: {len(merged_windows)}
Golden Signal 分布: {json.dumps(gs_dist)}
Fault Category 分布: {json.dumps(fc_dist)}

── Golden Signal 分类摘要 ──

{gs_summary_text}

── 异常窗口（已合并相似窗口）──

{anomaly_text}

请基于以上结构化分析结果，给出最终告警结论。"""

    system_prompt = ANALYSIS_SYSTEM_PROMPT.format(
        time=now_str, file=INPUT_FILE,
        total=f"{len(df_t)}条 → {unique_count}模板 → {len(merged_windows)}异常窗口",
        distribution=json.dumps(gs_dist), analysis="", core_issue=""
    )

    prompt_chars = len(system_prompt) + len(user_prompt)

    # ── Step 10: LLM 分析 ──
    t_llm_start = time.time()
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.3, max_tokens=2048,
        )
        t_llm_done = time.time()
        usage = response.usage
        llm_result = response.choices[0].message.content

        return {
            "approach": "C-完整LogAn管道",
            "t_read_parse": t_preprocess_done - t_read_start,
            "t_template": t_template_done - t_preprocess_done,
            "t_gs_classify": t_gs_done - t_gs_start,
            "t_fc_classify": t_fc_done - t_fc_start,
            "t_merge": t_merge_done - t_fc_done,
            "t_llm": t_llm_done - t_llm_start,
            "t_total": t_llm_done - t_start,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
            "prompt_chars": prompt_chars,
            "template_count": unique_count,
            "record_count": len(df_t),
            "gs_dist": gs_dist,
            "fc_dist": fc_dist,
            "normal_windows": len(normal_windows),
            "anomaly_windows": len(merged_windows),
            "result_preview": (llm_result or "")[:500],
            "result_full": llm_result or "",
        }
    except Exception as e:
        return {
            "approach": "C-完整LogAn管道", "error": str(e),
            "t_read_parse": t_preprocess_done - t_read_start,
            "t_template": t_template_done - t_preprocess_done,
            "t_gs_classify": t_gs_done - t_gs_start,
            "t_fc_classify": t_fc_done - t_fc_start,
            "t_merge": t_merge_done - t_fc_done,
            "t_llm": time.time() - t_llm_start,
            "t_total": time.time() - t_start,
            "prompt_chars": prompt_chars,
            "template_count": unique_count, "record_count": len(df_t),
        }


# ═══════════════════════════════════════════════════════════
#  主测试流程
# ═══════════════════════════════════════════════════════════

ROUNDS = 5


def calc_stats(results, key):
    values = [r[key] for r in results if key in r and r.get(key) is not None]
    if not values:
        return {"avg": 0, "min": 0, "max": 0}
    return {"avg": statistics.mean(values), "min": min(values), "max": max(values)}


def run_benchmark():
    results_a = []
    results_b = []
    results_c = []

    print("=" * 80)
    print(f"  三方案对比测试: A-模板 / B-原始日志 / C-完整LogAn管道")
    print(f"  数据: {INPUT_FILE}  |  模型: {LLM_MODEL}  |  轮次: {ROUNDS}")
    print("=" * 80)

    for r in range(1, ROUNDS + 1):
        print(f"\n{'─' * 80}")
        print(f"  第 {r}/{ROUNDS} 轮")
        print(f"{'─' * 80}")

        # ── Approach A ──
        print("\n  [A] LogAn 模板方案...")
        res_a = approach_a_logan()
        if "error" not in res_a:
            print(f"    预处理: {res_a['t_read_parse']:.2f}s | 模板: {res_a['t_template']:.2f}s | LLM: {res_a['t_llm']:.2f}s | 总计: {res_a['t_total']:.2f}s")
            print(f"    模板数: {res_a['template_count']} | Token: {res_a['total_tokens']} (prompt:{res_a['prompt_tokens']} comp:{res_a['completion_tokens']})")
            print(f"    结果预览: {res_a['result_preview'][:120]}...")
        else:
            print(f"    ❌ 错误: {res_a['error']}")
        results_a.append(res_a)

        # ── Approach B ──
        print("\n  [B] weekAgent 原始日志方案...")
        res_b = approach_b_weekagent()
        if "error" not in res_b:
            print(f"    解析: {res_b['t_read_parse']:.2f}s | LLM: {res_b['t_llm']:.2f}s | 总计: {res_b['t_total']:.2f}s")
            print(f"    记录数: {res_b['record_count']} (送入{res_b['sent_count']}条) | Token: {res_b['total_tokens']} (prompt:{res_b['prompt_tokens']} comp:{res_b['completion_tokens']})")
            print(f"    结果预览: {res_b['result_preview'][:120]}...")
        else:
            print(f"    ❌ 错误: {res_b['error']}")
        results_b.append(res_b)

        # ── Approach C ──
        print("\n  [C] 完整 LogAn 管道...")
        res_c = approach_c_logan_full()
        if "error" not in res_c:
            print(f"    预处理: {res_c['t_read_parse']:.2f}s | 模板: {res_c['t_template']:.2f}s | GS: {res_c['t_gs_classify']:.2f}s | FC: {res_c['t_fc_classify']:.2f}s | 合并: {res_c['t_merge']:.2f}s | LLM: {res_c['t_llm']:.2f}s | 总计: {res_c['t_total']:.2f}s")
            print(f"    模板: {res_c['template_count']} | 正常窗口: {res_c['normal_windows']} | 异常窗口: {res_c['anomaly_windows']}")
            print(f"    GS分布: {res_c['gs_dist']}")
            print(f"    Token: {res_c['total_tokens']} (prompt:{res_c['prompt_tokens']} comp:{res_c['completion_tokens']})")
            print(f"    结果预览: {res_c['result_preview'][:120]}...")
        else:
            print(f"    ❌ 错误: {res_c['error']}")
        results_c.append(res_c)

    # ═══════════════════════════════════════════════
    #  汇总统计
    # ═══════════════════════════════════════════════
    print("\n\n" + "=" * 100)
    print("  三方案对比汇总报告")
    print("=" * 100)

    # 基础指标对比
    print(f"\n{'指标':<22} {'A-模板方案':>22} {'B-原始日志':>22} {'C-完整LogAn':>22}")
    print("-" * 90)

    compare_keys = [
        ("总耗时(s)", "t_total", "t_total", "t_total"),
        ("读取+预处理(s)", "t_read_parse", "t_read_parse", "t_read_parse"),
        ("LLM分析(s)", "t_llm", "t_llm", "t_llm"),
        ("Prompt Tokens", "prompt_tokens", "prompt_tokens", "prompt_tokens"),
        ("Completion Tokens", "completion_tokens", "completion_tokens", "completion_tokens"),
        ("Total Tokens", "total_tokens", "total_tokens", "total_tokens"),
    ]

    for label, ka, kb, kc in compare_keys:
        sa = calc_stats(results_a, ka)
        sb = calc_stats(results_b, kb)
        sc = calc_stats(results_c, kc)
        print(f"{label:<22} {sa['avg']:>8.2f} ({sa['min']:.1f}-{sa['max']:.1f})  {sb['avg']:>8.2f} ({sb['min']:.1f}-{sb['max']:.1f})  {sc['avg']:>8.2f} ({sc['min']:.1f}-{sc['max']:.1f})")

    # C 特有指标
    print(f"\n── 完整 LogAn 管道特有指标 ──")
    for label, key in [
        ("模板生成(s)", "t_template"),
        ("GS分类(s)", "t_gs_classify"),
        ("FC分类(s)", "t_fc_classify"),
        ("窗口合并(s)", "t_merge"),
        ("异常窗口数", "anomaly_windows"),
        ("正常窗口数", "normal_windows"),
    ]:
        s = calc_stats(results_c, key)
        print(f"  {label}: 平均 {s['avg']:.2f} ({s['min']:.1f}-{s['max']:.1f})")

    # 保存详细结果
    output_path = os.path.join(OUTPUT_DIR, "benchmark_results_full.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "config": {"model": LLM_MODEL, "file": INPUT_FILE, "rounds": ROUNDS},
            "results_a": [{k: v for k, v in r.items() if k not in ("result_full", "gs_dist", "fc_dist")} for r in results_a],
            "results_b": [{k: v for k, v in r.items() if k != "result_full"} for r in results_b],
            "results_c": [{k: v for k, v in r.items() if k != "result_full"} for r in results_c],
        }, f, ensure_ascii=False, indent=2)

    print(f"\n详细结果已保存至: {output_path}")

    return results_a, results_b, results_c


if __name__ == "__main__":
    run_benchmark()