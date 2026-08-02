#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按尊者新原则全面重切: 每句【本句完整优先】, 宁可多包含上一句结尾/下一句开头。
- start = max(0, 本句首词语音全局起点 g0 - START_PAD), START_PAD=0.15 (往前含上句尾音)
- end   = 本句尾音真实结束(源能量最后语音帧) + END_PAD, END_PAD=0.40 (往后含完整尾音)
  * 绝不再用对齐器 G1 低估的位置切
- 输出 recut_plan.json = [{ch,idx,start,end}] 供 dry-run 检查后重切
用法: python recut_for_completeness.py [--dry]
"""
import os, json, re, sys, subprocess
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
sys.path.insert(0, AUDIO)
from _ch_src_map import CH_SRC
VOICE_TH = 0.012
WIN = 0.010
START_PAD = 0.15
END_PAD = 0.10   # 本句尾音后最小余量(必含尾音即可, 少吞下句)
OVERSHOOT = 0.25   # (保留, 未用)
TAIL_SCAN = 0.80   # 向后扫描尾音窗口


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def rms_env(x, sr=16000, win=0.010):
    w = int(sr * win); n = len(x) // w
    if n < 2:
        return np.array([0.0])
    return np.sqrt((x[:n*w].reshape(n, w) ** 2).mean(1))


def src_env(wav):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", wav, "-ar", "16000", "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return rms_env(x)


def tail_voice_end(env, g1, D):
    """在源 [g1, g1+TAIL_SCAN] 内找最后一个语音帧的全局秒。"""
    f0 = int(g1 / WIN); f1 = min(len(env), int((g1 + TAIL_SCAN) / WIN))
    idx = np.where(env[f0:f1] > VOICE_TH)[0]
    if idx.size == 0:
        return g1
    return (f0 + idx[-1] + 1) * WIN


def clip_headroom(path):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if len(x) < 1600:
        return None
    e = rms_env(x)
    idx = np.where(e > VOICE_TH)[0]
    if idx.size == 0:
        return 0.0
    dur = len(x) / 16000.0
    return dur - (idx[-1] + 1) * WIN


def main():
    DRY = "--dry" in sys.argv
    data = json.loads(load_js(os.path.join(APP, "data.js")))
    obj = json.loads(load_js(os.path.join(AUDIO, "manifest_audio.js")))
    msent = obj["sentences"]; sections = data["sections"]
    env_cache = {}
    plan = []
    for ch_i, sec in enumerate(sections):
        ch = ch_i + 1
        A, B = sec["ruleStart"], sec["ruleEnd"]
        rawp = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
        wav = CH_SRC.get(ch)
        if not (os.path.exists(rawp) and wav and os.path.exists(wav)):
            print("  [skip] ch%d 无raw/源" % ch); continue
        raw = json.load(open(rawp, encoding="utf-8"))
        if "bounds" not in raw or not raw["bounds"]:
            continue
        bounds = {int(k): tuple(v) for k, v in raw["bounds"].items()}
        idxs = sorted(bounds); D = raw.get("D", 0.0)
        if ch not in env_cache:
            env_cache[ch] = src_env(wav)
        env = env_cache[ch]
        for idx in range(A, B + 1):
            ms = msent.get(str(idx))
            if not ms or not ms.get("clip"):
                continue
            if idx not in bounds:
                continue
            cur_dur = ms.get("t1")
            g0, g1 = bounds[idx]
            p_i = idxs.index(idx)
            G0next = bounds[idxs[p_i + 1]][0] if p_i < len(idxs) - 1 else D
            start = max(0.0, g0 - START_PAD)
            tv = tail_voice_end(env, g1, D)
            # 尊者原则: 本句完整优先, 宁可吞一点下一句开头。
            # end = 本句真实语音末尾 tv + 余量(必含本句尾音)。tv 可能已含一点下句首音,
            # 但保证本句完整优先。不再用 G0next 做硬 cap(它低估会切掉尾音)。
            end = min(D, tv + END_PAD)
            if end <= start or end - start < 0.5:
                end = min(D, max(start + 0.5, tv + 0.25))
            plan.append(dict(ch=ch, idx=idx, start=round(start, 3), end=round(end, 3),
                             g0=round(g0, 3), g1=round(g1, 3), tail_voice=round(tv, 3),
                             G0next=round(G0next, 3), cur_dur=cur_dur, D=round(D, 3)))
    json.dump(plan, open(os.path.join(AUDIO, "recut_plan.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("计划句数:", len(plan))
    if DRY:
        for p in plan[:30]:
            print("  ch%d idx%d start=%s end=%s (g0=%s g1=%s tv=%s)" % (
                p["ch"], p["idx"], p["start"], p["end"], p["g0"], p["g1"], p["tail_voice"]))
    print("recut_plan.json 已写")


if __name__ == "__main__":
    main()
