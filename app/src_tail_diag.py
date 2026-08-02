#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""权威句末完整性诊断（源录音锚定，模型无关，能量法）：
对每个有真人音频的句子，用 chN_complete.wav(源16k音频) + chN_align_raw.json(全局词时) 还原
clip 在源里的真实起止，再算 clip_end 之后源里还有多少"语音能量"（即原本该有但被切掉的尾巴）。

判定：
- drop_voiced = clip_end 之后, 源里继续的连续语音时长(直到 >0.35s 静音)。
  * drop_voiced 大(>0.15s) -> clip 把末词尾音/拖腔切掉了 = 句末不完整(硬证据)
  * drop_voiced 小(接近0) -> clip_end 落在真静音, 末词已念完, 完整
- 输出按 drop_voiced 降序, 最严重的(被切掉的尾巴最长)排最前。
用法: python src_tail_diag.py
"""
import sys, os, json, glob, re
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
VOICE_TH = 0.012
WIN = 0.010
LEAD = 0.12
TAIL = 0.40
MIN_DUR = 0.6


def load_js(path):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    s = s.rstrip().rstrip(";")
    return json.loads(s)


def rms_env(x, sr=16000, win=0.010):
    w = int(sr * win); n = len(x) // w
    if n < 2: return np.array([0.0])
    return np.sqrt((x[:n*w].reshape(n, w) ** 2).mean(1))


def voiced_after(x, t_start, sr=16000, until=2.0, vo=VOICE_TH):
    """从 t_start 起往后扫描, 返回连续语音长度(秒), 直到出现 >0.35s 静音或 until 超时。
    用于判断 clip_end 之后源里还压着多少语音。"""
    env = rms_env(x, sr)
    dt = WIN
    f0 = int(t_start // dt)
    rng = int(until // dt)
    if f0 >= len(env): return 0.0
    across = 0.0  # 当前静音跨越
    voiced_len = 0.0
    for f in range(f0, min(len(env), f0 + rng)):
        e = float(env[f])
        if e > vo:  # 语音
            voiced_len += dt
            across = 0.0
        else:
            across += dt
            if across > 0.35:
                break
    return voiced_len


def main():
    data = load_js(os.path.join(APP, "data.js"))
    obj = load_js(os.path.join(AUDIO, "manifest_audio.js"))
    msent = obj["sentences"]
    rules = data["rules"]; sections = data["sections"]
    # 源 wav 是否现成
    have_wav = {}
    for ch in range(1, 12):
        w = os.path.join(AUDIO, "ch%d_complete.wav" % ch)
        have_wav[ch] = os.path.exists(w)

    rows = []  # dict
    for ch_i, sec in enumerate(sections):
        ch = ch_i + 1
        A, B = sec["ruleStart"], sec["ruleEnd"]
        rawp = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
        if not (have_wav[ch] and os.path.exists(rawp)):
            continue
        raw = json.load(open(rawp, encoding="utf-8"))
        if "bounds" not in raw or not raw["bounds"]:
            continue
        bounds = {int(k): tuple(v) for k, v in raw["bounds"].items()}
        idxs = sorted(bounds)
        if not idxs: continue
        D = raw.get("D", 0.0)
        # 加载源 wav (16k mono int16)
        xw = np.frombuffer(open(os.path.join(AUDIO, "ch%d_complete.wav" % ch), "rb").read(),
                           dtype=np.int16).astype(np.float32) / 32768.0
        sr = 16000
        # 还原 clip end(源秒): 仿 align_ch_generic do_split 逻辑
        for i_idx, idx in enumerate(idxs):
            rule = rules[idx]
            pali = rule.get("pali", "")
            ms = msent.get(str(idx))
            if not ms or not ms.get("clip"):
                rows.append(dict(ch=ch, idx=idx, src_end=None, drop=0.0, dur=None, st="TTS", pali=pali))
                continue
            g0, g1 = bounds[idx]
            # clip end
            if i_idx == len(idxs) - 1:
                cust_end = min(D, g1 + TAIL)
            else:
                g0_next, _ = bounds[idxs[i_idx + 1]]
                cust_end = (g1 + g0_next) / 2.0
            # 只考虑"真正切到源里语音还在继续"的情况
            drop = voiced_after(xw, cust_end, sr, until=3.0)
            if drop >= 0.15:
                st = "被切尾巴"
            elif drop >= 0.04:
                st = "轻微/存疑"
            else:
                st = "OK"
            rows.append(dict(ch=ch, idx=idx, src_end=round(cust_end, 3),
                             drop=round(drop, 3), dur=None, st=st, pali=pali))
    # 汇总
    import collections
    stat = collections.Counter(r["st"] for r in rows)
    print("== 源录音锚定句末完整性诊断 ==")
    print("扫描=%d | 状态: %s" % (len(rows), dict(stat)))
    # 分章统计
    bych = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["st"] != "TTS":
            bych[r["ch"]][r["st"]] += 1
    for ch in sorted(bych):
        print("  ch%d: %s" % (ch, dict(bych[ch])))
    # 严重段
    bad = [r for r in rows if r["st"] == "被切尾巴"]
    bad = sorted(bad, key=lambda r: -r["drop"])
    lines = []
    lines.append("== 被切尾巴 (src_drop>=0.15s), 按 drop 降序 ==")
    for r in bad:
        lines.append("ch%d idx%4d src_end=%.3f 切掉≈%.2fs | %s" % (
            r["ch"], r["idx"], r["src_end"] if r["src_end"] is not None else -1,
            r["drop"], r["pali"][:40]))
    txt = "\n".join(lines)
    outp = os.path.join(AUDIO, "src_tail_diag.txt")
    open(outp, "w", encoding="utf-8").write(txt)
    print(txt)
    print("详情已写 ->", outp)


if __name__ == "__main__":
    main()
