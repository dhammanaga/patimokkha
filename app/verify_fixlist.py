#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验 fixlist 每条: 旧切点 old_end 处源录音是否正切在语音上(能量>阈值)。
若为是 -> 真被切, 必须修(记录 source_voiced_at_oldend=True)
若为否 -> old_end 已落在静音, 无语音被丢, 标记为"可延但不必要"
同时记录 old_end 前一帧的语音状态与拖腔起点, 供精细决策。
只读已有 fixlist.json + 源wav, 不重切。"""
import os, json, re
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
VOICE_TH = 0.012
WIN = 0.010


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def rms_env(x, sr=16000, win=0.010):
    w = int(sr * win); n = len(x) // w
    if n < 2:
        return np.array([0.0])
    return np.sqrt((x[:n*w].reshape(n, w) ** 2).mean(1))


def main():
    fx = json.load(open(os.path.join(AUDIO, "fixlist.json"), encoding="utf-8"))
    # 缓存各章 env
    wav_cache = {}
    rows = []
    for f in fx:
        ch = f["ch"]
        if ch not in wav_cache:
            wav = os.path.join(AUDIO, "ch%d_complete.wav" % ch)
            x = np.frombuffer(open(wav, "rb").read(), dtype=np.int16).astype(np.float32) / 32768.0
            wav_cache[ch] = rms_env(x)
        env = wav_cache[ch]; dt = WIN
        oe = f["old_end"]
        fe = int(oe // dt)
        # old_end 处能量(取该帧与前后两帧的最大, 平滑避免单帧抖动)
        seg = env[max(0, fe-1):fe+2]
        e_at = float(seg.max()) if seg.size else 0.0
        voiced = e_at > VOICE_TH
        # old_end 之前最后一个语音帧(即真实语音结束位置)
        idxv = np.where(env[:fe] > VOICE_TH)[0]
        last_voiced_before = (idxv[-1] + 1) * dt if idxv.size else 0.0
        rows.append(dict(ch=ch, idx=f["idx"], old_end=oe, new_end=f["new_end"],
                         voiced_at_old=e_at > 0, voiced_energy=round(e_at, 4),
                         need_voice=e_at > VOICE_TH, last_voice_before=round(last_voiced_before, 3)))
    need = [r for r in rows if r["need_voice"]]
    nod = [r for r in rows if not r["need_voice"]]
    print("fixlist 共%d | old_end切在语音上(真被切):%d | old_end在静音(可延但非必须):%d" % (
        len(rows), len(need), len(nod)))
    from collections import Counter
    print("真被切 分章:", Counter(r["ch"] for r in need))
    print("真被切 扩展>0.3s:", sum(1 for r in need if r["new_end"]-r["old_end"] > 0.3))
    snap = {"need": [dict(r) for r in need], "optional": [dict(r) for r in nod]}
    json.dump(snap, open(os.path.join(AUDIO, "fixlist_verified.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n== 真被切示例(前30, 按扩展降序) ==")
    for r in sorted(need, key=lambda r: -(r["new_end"]-r["old_end"]))[:30]:
        print("  ch%d idx%d old=%.2f new=%.2f (+%.2f) e=%.3f lastVoice=%.3f" % (
            r["ch"], r["idx"], r["old_end"], r["new_end"], r["new_end"]-r["old_end"],
            r["voiced_energy"], r["last_voice_before"]))
    print("\n== 在静音(可选)示例(前10) ==")
    for r in nod[:10]:
        print("  ch%d idx%d old=%.2f new=%.2f e=%.3f lastVoice=%.3f" % (
            r["ch"], r["idx"], r["old_end"], r["new_end"], r["voiced_energy"], r["last_voice_before"]))


if __name__ == "__main__":
    main()
