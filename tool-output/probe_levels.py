# -*- coding: utf-8 -*-
"""探测 app.log 的级别分布与记录结构"""
import os, re, collections

LOG_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+) \| (.+)'
)

for fn in ['app.log.2026-07-21', 'app.log']:
    p = os.path.join(r'E:\weekAgent', fn)
    with open(p, 'r', encoding='utf-8') as f:
        text = f.read()
    lines = text.splitlines()

    counter = collections.Counter()
    records = 0
    for l in lines:
        m = LOG_RE.match(l)
        if m:
            records += 1
            counter[m.group(2)] += 1
    print('=====', fn, '总行数=', len(lines), '记录数(匹配行首)=', records)
    print('  级别分布:', dict(counter))
    # 抽样几个 WARNING/ERROR
    shown = {'WARNING': 0, 'ERROR': 0}
    for l in lines:
        for lv in ['WARNING', 'ERROR']:
            if lv in l and shown[lv] < 2:
                print('  [', lv, ']', l[:120])
                shown[lv] += 1
    print()