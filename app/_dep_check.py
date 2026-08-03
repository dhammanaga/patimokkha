# -*- coding: utf-8 -*-
"""只读校验：全表 manifest.words 首词 vs data.words 首词匹配率，按章统计。"""
import re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 载入 data.js ---
data_src = open('data.js', encoding='utf-8').read()
m = re.search(r'window\.PM_DATA\s*=\s*(\{.*?\});\s*\n?\s*(?:/\*|window)', data_src, re.S)
if not m:
    # 尝试宽松匹配到文件尾
    m = re.search(r'window\.PM_DATA\s*=\s*(\{.*)', data_src, re.S)
data_txt = m.group(1)
# 解析 rules 数组
rm = re.search(r'"rules"\s*:\s*\[', data_txt)
# 用简单方式：找所有 {"idx":N,...} 对象的 key
# 更好：node 解析
import json, subprocess
code = f"""
const s = {repr_to_js(data_src)};
// find window.PM_DATA
const i = s.indexOf('window.PM_DATA = ');
const j = s.indexOf(';', i);
const obj = eval('(' + s.slice(i+'window.PM_DATA = '.length, j) + ')');
const rules = obj.rules;
const meta = obj.meta;
process.stdout.write(JSON.stringify({{count: rules.length, meta}}));
"""
def repr_to_js(s):
    import shlex
    return json.dumps(s)
print("prep ok")
