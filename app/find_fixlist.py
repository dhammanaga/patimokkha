#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确识别"句末被切"的可安全修复句(供 re-cut 用):
判据(三重科学证据叠加):
 1) clip 自身能量: 尾部语音紧贴末尾(headroom<0.12s) -> 疑似被切
 2) 源录音在 cur_end 之后、G0next(下句首词)之前存在 >=0.35s 真静音 -> 可安全扩展不串句
 3) 扩展后确实变长(新end > 旧end+0.03) -> 确有尾巴被切
输出 app/audio/fixlist.json -> list[{ch,idx,old_end,new_end,G1,G0next}]
"""
import os, json, re, subprocess
import numpy as np
from collections import Counter

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
VOICE_TH = 0.012
WIN = 0.010
HEADROOM_CUT = 0.12
MIN_EXTEND = 0.03


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def rms_env(x, sr=16000, win=0.010):
    w = int(sr * win); n = len(x) // w
    if n < 2:
        return np.array([0.0])
    return np.sqrt((x[:n*w].reshape(n, w) ** 2).mean(1))


def clip_energy(path):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    dur = len(x) / 16000.0
    if len(x) < 1600:
        return 0.0, dur
    env = rms_env(x)
    idx = np.where(env > VOICE_TH)[0]
    if idx.size == 0:
        return 0.0, dur
    lv = (idx[-1] + 1) * WIN
    return lv, dur


def main():
    data = json.loads(load_js(os.path.join(APP, "data.js")))
    obj = json.loads(load_js(os.path.join(AUDIO, "manifest_audio.js")))
    msent = obj["sentences"]; sections = data["sections"]

    # 1) clip 尾部紧贴末尾
    tight = set()
    for ch_i, sec in enumerate(sections):
        ch = ch_i + 1
        for idx in range(sec["ruleStart"], sec["ruleEnd"] + 1):
            ms = msent.get(str(idx))
            if not ms or not ms.get("clip"):
                continue
            cp = os.path.join(APP, ms["clip"])
            if not os.path.exists(cp):
                continue
            lv, dur = clip_energy(cp)
            if dur - lv < HEADROOM_CUT:
                tight.add((ch, idx))
    print("clip尾部紧贴末尾(headroom<%.2fs)句数: %d" % (HEADROOM_CUT, len(tight)))

    # 2+3) 源静音校验 + 确实变长
    fixable = []
    for ch_i, sec in enumerate(sections):
        ch = ch_i + 1
        A, B = sec["ruleStart"], sec["ruleEnd"]
        rawp = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
        wav = os.path.join(AUDIO, "ch%d_complete.wav" % ch)
        if not (os.path.exists(rawp) and os.path.exists(wav)):
            continue
        raw = json.load(open(rawp, encoding="utf-8"))
        bounds = {int(k): tuple(v) for k, v in raw["bounds"].items()}
        idxs = sorted(bounds); D = raw.get("D", 0.0)
        x = np.frombuffer(open(wav, "rb").read(), dtype=np.int16).astype(np.float32) / 32768.0
        env = rms_env(x); dt = WIN
        for p_i, idx in enumerate(idxs):
            if (ch, idx) not in tight:
                continue
            ms = msent.get(str(idx))
            if not ms or not ms.get("clip"):
                continue
            g0, g1 = bounds[idx]
            G0next = bounds[idxs[p_i + 1]][0] if p_i < len(idxs) - 1 else D
            cur_end = (g1 + G0next) / 2.0
            f0 = int(cur_end // dt); silent = 0.0; sil = None
            for f in range(f0, min(len(env), f0 + int(3.0 / dt))):
                e = float(env[f])
                silent = 0.0 if e > VOICE_TH else silent + dt
                if silent >= 0.35:
                    sil = (f - silent / dt) * dt; break
            if sil is None:
                continue
            new_end = sil + 0.05
            if new_end <= G0next and new_end > cur_end + MIN_EXTEND:
                fixable.append(dict(ch=ch, idx=idx, old_end=round(cur_end, 3),
                                    new_end=round(new_end, 3),
                                    G1=round(g1, 3), G0next=round(G0next, 3)))
    print("可安全扩展(修尾部)句数: %d" % len(fixable))
    print("分章:", Counter(f["ch"] for f in fixable))
    out = os.path.join(AUDIO, "fixlist.json")
    json.dump(fixable, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("fixlist(含 ch1 待补) 已写 ->", out)
    print("示例:")
    for f in fixable[:15]:
        print("  ch%d idx%d old=%.2f new=%.2f G1=%.2f G0next=%.2f" % (
            f["ch"], f["idx"], f["old_end"], f["new_end"], f["G1"], f["G0next"]))


if __name__ == "__main__":
    main()
