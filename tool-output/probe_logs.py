# -*- coding: utf-8 -*-
"""临时探测 app.log 结构"""
import os

for fn in ['app.log.2026-07-21', 'app.log']:
    p = os.path.join(r'E:\weekAgent', fn)
    size = os.path.getsize(p)
    with open(p, 'rb') as f:
        raw = f.read()
    textenc = '?'
    text = None
    for enc in ['utf-8', 'gbk', 'utf-8-sig']:
        try:
            text = raw.decode(enc)
            textenc = enc
            break
        except Exception:
            pass
    lines = text.splitlines()
    print('=====', fn, 'size=', size, 'enc=', textenc, 'lines=', len(lines))
    print('  first3:')
    for l in lines[:3]:
        print('    ', repr(l[:95]))
    print('  last3:')
    for l in lines[-3:]:
        print('    ', repr(l[:95]))