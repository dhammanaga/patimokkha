#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ch10 尾部修复 + 结语章(ch11)用 ch10 录音的真人音频:
- ch10 idx 1196/1197 按自由解码真实边界紧切 (43.50-49.30 / 49.80-52.80)
- ch11 idx 1198-1210 用 ch10 录音 53.7-102s 区域: 边界=自由解码锚点中点, 词时=字符加权
输出更新 ch10_align.json / ch11_align.json 并重切 sent_new/1196-1210.mp3。
"""
import sys, os, json, subprocess, time, shutil
import numpy as np
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
SENT_NEW = os.path.join(AUDIO, "sent_new")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SRC = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\善巧提供\后7章\10. Satta Adhikarana Samatha Dhamma.mp3"

# ch10 修复
CH10_FIX = {1196: (43.50, 49.30), 1197: (49.80, 52.80)}
# ch11 真实边界 (自由解码锚点): idx -> (start, end)
CH11 = {
    1198: (53.92, 56.40), 1199: (57.54, 59.74), 1200: (60.90, 63.92),
    1201: (65.02, 66.78), 1202: (67.82, 70.60), 1203: (71.76, 74.06),
    1204: (75.20, 77.74), 1205: (78.88, 80.58), 1206: (81.80, 84.34),
    1207: (85.36, 92.22), 1208: (93.30, 98.00), 1209: (98.00, 99.16),
    1210: (99.16, 101.32),
}


def cut_and_write(idx, st0, st1, rules, al, ch, src=SRC):
    out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
    subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                    "-i", src, "-c", "copy", out],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    dur = round(st1 - st0, 3)
    orig = rules[idx]["words"]; olen = len(orig)
    weights = [max(1, len((orig[i].get("p") or "").strip())) for i in range(olen)]
    total_w = sum(weights)
    rel = []; cursor = 0.0
    for i in range(olen):
        wlen = dur * weights[i] / total_w
        rel.append({"p": orig[i].get("p", ""), "t0": round(cursor, 3),
                    "t1": round(min(dur, cursor + wlen), 3)})
        cursor = rel[-1]["t1"]
    al[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0, "t1": dur,
                    "rep": 1, "words": rel}
    print("  idx %3d -> %.2f~%.2fs (%.2fs, %d词)" % (idx, st0, st1, dur, len(rel)), flush=True)


def main():
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    ts = time.strftime("%Y%m%d_%H%M%S")
    # --- ch10 ---
    al10 = json.load(open(os.path.join(AUDIO, "ch10_align.json"), encoding="utf-8"))
    shutil.copy(os.path.join(AUDIO, "ch10_align.json"),
                os.path.join(AUDIO, "ch10_align.json.bak_tail_%s" % ts))
    print("== ch10 1196/1197 紧切 ==")
    for idx, (st0, st1) in CH10_FIX.items():
        cut_and_write(idx, st0, st1, rules, al10, 10)
    json.dump(al10, open(os.path.join(AUDIO, "ch10_align.json"), "w", encoding="utf-8"), ensure_ascii=False)
    # --- ch11 ---
    al11 = json.load(open(os.path.join(AUDIO, "ch11_align.json"), encoding="utf-8")) if os.path.exists(
        os.path.join(AUDIO, "ch11_align.json")) else {}
    shutil.copy(os.path.join(AUDIO, "ch11_align.json"),
                os.path.join(AUDIO, "ch11_align.json.bak_tail_%s" % ts))
    print("== ch11 结语 1198-1210 (真人录音) ==")
    ids = sorted(CH11.keys())
    # 中点边界
    cuts = {}
    for i, idx in enumerate(ids):
        g0, g1 = CH11[idx]
        if i == 0:
            st0 = g0 - 0.22
        else:
            st0 = cuts[ids[i - 1]][1]
        if i == len(ids) - 1:
            st1 = min(103.18, g1 + 0.60)
        else:
            ng0 = CH11[ids[i + 1]][0]
            st1 = (g1 + ng0) / 2.0
        cuts[idx] = (st0, st1)
    for idx in ids:
        st0, st1 = cuts[idx]
        cut_and_write(idx, st0, st1, rules, al11, 11)
    json.dump(al11, open(os.path.join(AUDIO, "ch11_align.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("完成; 备份 ch10/ch11_align.json.bak_tail_%s" % ts)
    print("接着: merge_align_to_manifest.py && post_manifest_tts.py && proofread_ch.py --chapters 10 11")


if __name__ == "__main__":
    main()
