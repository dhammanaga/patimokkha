#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""二次验证: 检查被重切修复的句子, 修复后 headroom(=含尾音余量)是否明显增大。
headroom 合理区间: 0.15~2.5s(有静音余量, 既不紧贴也不吞到下句)。
过小(<0.12) 仍有被切嫌疑; 过大(>2.5) 可能吞进下句/过度加静音。
只读 sent_new/*.mp3 + 已验证源边界, 不重切。
"""
import os, json, re, subprocess
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
VOICE_TH = 0.012
WIN = 0.010


def rms_env(x, sr=16000, win=0.010):
    w = int(sr * win); n = len(x) // w
    if n < 2:
        return np.array([0.0])
    return np.sqrt((x[:n*w].reshape(n, w) ** 2).mean(1))


def headroom_of(path):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    dur = len(x) / 16000.0
    if len(x) < 1600:
        return dur, dur
    env = rms_env(x)
    idx = np.where(env > VOICE_TH)[0]
    if idx.size == 0:
        return dur, dur
    lv = (idx[-1] + 1) * WIN
    return dur - lv, dur


def main():
    done = json.load(open(os.path.join(AUDIO, "recut_done.json"), encoding="utf-8"))
    good = 0; tight = []; overshoot = []
    hr = []
    for d in done:
        cp = os.path.join(SENT_NEW if False else APP, "audio/sent_new/%d.mp3" % d["idx"])
        if not os.path.exists(cp):
            continue
        h, dur = headroom_of(cp)
        hr.append(h)
        if h < 0.12:
            tight.append((d["ch"], d["idx"], round(h, 3)))
        elif h > 2.5:
            overshoot.append((d["ch"], d["idx"], round(h, 3)))
        else:
            good += 1
    arr = np.array(hr)
    print("修复句验证: %d" % len(done))
    print("headroom: min=%.3f p25=%.2f 中位=%.2f p75=%.2f max=%.2f" % (
        arr.min(), np.percentile(arr, 25), np.median(arr), np.percentile(arr, 75), arr.max()))
    print("合理(0.12~2.5): %d | 仍紧贴(<0.12): %d | 过大(>2.5): %d" % (
        good, len(tight), len(overshoot)))
    print("仍紧贴(需人工复查):", tight[:20])
    print("过大(可能吞下句,需复查):", overshoot[:20])


if __name__ == "__main__":
    SENT_NEW = os.path.join(AUDIO, "sent_new")
    main()
