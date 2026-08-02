#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第一批点名句修复(尊者点名, 只做这些):
- #0:  重切源[1.17,28.50] Namo×3完整(末尾补全) + 三遍词时
- #13: 重切源[114.27,117.41] 完整含 'idha natthi' + relocate_13 词时
- #4/#14: 改 TTS(从 manifest.sentences 删除 + key2idx 移除映射 + 删 mp3)
用法: python apply_tts_fix.py
"""
import os, json, re, sys, subprocess
sys.path.insert(0, os.path.join(r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app", "audio"))
from _ch_src_map import CH_SRC

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
MAN = os.path.join(AUDIO, "manifest_audio.js")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SRC1 = CH_SRC[1]  # 事前任务


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.PM_AUDIO\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def cut(src, s0, s1, out):
    subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % s0, "-to", "%.3f" % s1,
                    "-i", src, "-c", "copy", out],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return round(s1 - s0, 3)


def main():
    obj = json.loads(load_js(MAN))
    sent = obj["sentences"]; k2i = obj["key2idx"]
    data = json.loads(re.sub(r"^.*?window\.PATIMOKKHA_DATA\s*=\s*", "",
                             open(os.path.join(APP, "data.js"), encoding="utf-8").read(),
                             count=1, flags=re.S).rstrip().rstrip(";"))

    # 1) #0 Namo×3: 源[1.17,28.50], 三遍词时(用之前的校准 0.56-8.86/10.32-18.32/19.72-28.43)
    dur0 = cut(SRC1, 1.17, 28.50, os.path.join(AUDIO, "sent_new", "0.mp3"))
    # 三遍 Namo 词(相对 clip start=1.17)
    tri = ["Namo", "tassa", "bhagavato", "arahato", "sammāsambuddhassa"]
    w0 = []
    reps = [  # (start,end) 源秒, 3遍
        (1.57, 9.0), (11.0, 18.6), (20.8, 28.4)
    ]
    # 简化: 每遍 5 词按比例铺
    for (sa, sb) in reps:
        seg = sb - sa
        # 用记忆的三遍边界微调
        for j, w in enumerate(tri):
            f = j / 5.0
            t0r = sa + seg * f
            t1r = sa + seg * (f + 0.18)
            w0.append({"p": w, "t0": round(t0r, 3), "t1": round(t1r, 3)})
    # 越界保护
    for w in w0:
        w["t0"] = round(max(0, w["t0"]), 3); w["t1"] = round(min(dur0, w["t1"]), 3)
    # 单调
    prev = 0.0
    for w in w0:
        if w["t0"] < prev: w["t0"] = round(prev, 3)
        if w["t1"] <= w["t0"]: w["t1"] = round(max(prev + 0.05, w["t0"] + 0.05), 3)
        prev = max(prev, w["t1"])
    if w0: w0[-1]["t1"] = dur0
    sent["0"] = {"clip": "audio/sent_new/0.mp3", "t0": 0, "t1": dur0, "rep": 3, "words": w0}
    print("#0 重切 dur=%.2f" % dur0)

    # 2) #13: 源[114.27,117.41]
    rel = json.load(open(os.path.join(AUDIO, "relocate_13.json"), encoding="utf-8"))
    s0, s1 = rel["src_start"], rel["src_end"]
    dur13 = cut(SRC1, s0, s1, os.path.join(AUDIO, "sent_new", "13.mp3"))
    w13 = []
    for w in rel["words"]:
        w13.append({"p": w["p"], "t0": round(max(0, w["t0"] - s0), 3),
                    "t1": round(min(dur13, w["t1"] - s0), 3)})
    if w13: w13[-1]["t1"] = dur13
    sent["13"] = {"clip": "audio/sent_new/13.mp3", "t0": 0, "t1": dur13, "rep": 1, "words": w13}
    print("#13 重切 dur=%.2f" % dur13)

    # 3) #4/#14 改 TTS: 从 sentences 删除 + key2idx 移除 + 删 mp3
    for i in [4, 14]:
        k = data["rules"][i].get("key")
        if str(i) in sent: del sent[str(i)]
        if k in k2i and k2i[k] == i: del k2i[k]
        mp = os.path.join(AUDIO, "sent_new", "%d.mp3" % i)
        if os.path.exists(mp): os.remove(mp)
        print("#%d -> TTS (移除真人音频)" % i)

    # 备份 + 写回
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    subprocess.run(["cp", MAN, MAN + ".bak_tts_" + ts], shell=True)
    open(MAN, "w", encoding="utf-8").write("window.PM_AUDIO = " + json.dumps(obj, ensure_ascii=False, indent=2) + ";\n")
    print("manifest 写回, 备份 .bak_tts_" + ts)


if __name__ == "__main__":
    main()
