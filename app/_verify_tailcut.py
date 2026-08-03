# -*- coding: utf-8 -*-
"""尾切修复后的全库复检：
1) manifest t1 是否与 mp3 实际时长一致
2) 逐词时间戳是否越界
3) 尾部 headroom 分布（修复前 vs 修复后）
4) 全静音切片
产物：_tailscan_after.json
"""
import subprocess, numpy as np, os, re, json, time, sys

FF = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SR, WIN, TH = 16000, 0.010, 0.012
APP = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP)

t = open('audio/manifest_audio.js', encoding='utf-8').read()
a = json.loads(re.search(r'window\.PM_AUDIO\s*=\s*(\{.*\})\s*;?\s*$', t, re.S).group(1))
s = a['sentences']
print("清单句数:", len(s), " key2idx:", len(a['key2idx']), flush=True)

old = json.load(open('_tailscan.json')) if os.path.exists('_tailscan.json') else {}

bad_t1, bad_w, heads, empty, missing = [], [], [], [], []
t0 = time.time()
for i, k in enumerate(sorted(s, key=int), 1):
    p = s[k]['clip']
    if not os.path.exists(p):
        missing.append(k)
        continue
    r = subprocess.run([FF, "-v", "error", "-i", p, "-ar", str(SR), "-ac", "1", "-f", "s16le", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    dur = len(x) / SR
    if abs(s[k]['t1'] - dur) > 0.08:
        bad_t1.append((k, s[k]['t1'], round(dur, 3)))
    for w in (s[k].get('words') or []):
        if w['t0'] < -0.001 or w['t1'] > dur + 0.12 or w['t1'] <= w['t0']:
            bad_w.append((k, w['p'], w['t0'], w['t1'], round(dur, 3)))
            break
    n = int(WIN * SR); m = len(x) // n
    if m < 2:
        empty.append(k); continue
    e = np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(1))
    v = np.where(e > TH)[0]
    if len(v) == 0:
        empty.append(k); continue
    heads.append((k, dur - (v[-1] + 1) * WIN))
    if i % 200 == 0:
        print("  ...%d/%d  %.0fs" % (i, len(s), time.time() - t0), flush=True)

hs = sorted(h for _, h in heads)
tight = [k for k, h in heads if h < 0.12]
oldtight = [k for k, v in old.items() if not v.get('empty') and v['head'] < 0.12]
print("\n===== 复检结果 =====")
print("文件缺失          :", len(missing), missing[:5])
print("t1 与实际时长不符 :", len(bad_t1), bad_t1[:5])
print("词时间戳越界      :", len(bad_w), bad_w[:5])
print("全静音切片        :", len(empty), empty[:5])
print("尾部紧贴(<0.12s)  : 修复前 %d  →  修复后 %d" % (len(oldtight), len(tight)))
if hs:
    print("headroom 分位: p10=%.3f p25=%.3f p50=%.3f p75=%.3f"
          % (hs[len(hs) // 10], hs[len(hs) // 4], hs[len(hs) // 2], hs[len(hs) * 3 // 4]))
print("仍紧贴的前30:", sorted(tight, key=int)[:30])
json.dump({k: h for k, h in heads}, open('_tailscan_after.json', 'w'))
print("DONE")
