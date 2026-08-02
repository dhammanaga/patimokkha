#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""紧切 ch6 中 3 句长停顿补静音过多的句子(457/562/563): 按 word_global 实际语音边界裁剪。
新切窗: start = min词起点-0.20, end = max词终点+0.30(不与邻句重叠)。
"""
import sys, os, json, subprocess, time, shutil
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SRC = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\善巧提供\后7章\6. Timsa Nissaggiya Pacittiya Dhamma.mp3"
FIX = [457, 562, 563]

def main():
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    raw = json.load(open(os.path.join(AUDIO, "ch6_align_raw.json"), encoding="utf-8"))
    wg = {int(k): v for k, v in raw["word_global"].items()}
    al = json.load(open(os.path.join(AUDIO, "ch6_align.json"), encoding="utf-8"))
    ts = time.strftime("%Y%m%d_%H%M%S")
    shutil.copy(os.path.join(AUDIO, "ch6_align.json"),
                os.path.join(AUDIO, "ch6_align.json.bak_trim_%s" % ts))
    for idx in FIX:
        ws = wg.get(idx)
        if not ws:
            print("!! idx %d 无 word_global" % idx); continue
        g0 = min(w[0] for w in ws)
        g1 = max(w[1] for w in ws)
        st0 = g0 - 0.20
        st1 = g1 + 0.30
        dur = round(st1 - st0, 3)
        out = os.path.join(SENT_NEW := os.path.join(AUDIO, "sent_new"), "%d.mp3" % idx).replace("\\", "/")
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                        "-i", SRC, "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
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
        print("idx %3d 紧切 %.2f~%.2f (%.2fs, %d词)  [原语音 %.2f-%.2f]" % (
            idx, st0, st1, dur, len(rel), g0, g1), flush=True)
    json.dump(al, open(os.path.join(AUDIO, "ch6_align.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("ch6_align.json 已更新; 备份 ch6_align.json.bak_trim_%s" % ts)
    print("接着: python merge_align_to_manifest.py && python post_manifest_tts.py && python proofread_ch.py --chapters 6")


if __name__ == "__main__":
    main()
