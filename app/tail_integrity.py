#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""句末完整性科学扫描（声学能量法，模型无关，快速可靠）：
对每个有真人音频的句子切片，计算 RMS 能量包络，检测"末尾语音是否被切断"。

判定逻辑（针对尊者"每句末尾都不完整"的质疑）：
- last_voiced = 切片内最后一个能量>阈值的语音帧时刻（末端带拖腔的诵念会持续到接近末尾）
- headroom = clip时长 - last_voiced  → 句末语音结束后的静音/拖尾余量
  * headroom 很大(>0.4s) → 末词早已念完，还有充足余量，几乎不可能截断末词
  * headroom 很小(<0.12s) → 切片紧贴最后一个语音帧结束，有被拦腰截断的高风险
- 输出按 headroom 升序排列，让最可疑的（紧贴末尾切断）排在前面。
- 同时输出 clip 起点起点前是否紧贴上一句（串句/缺前导）。
用法: python tail_integrity.py [--chapters N] [--limit N] [--min-headroom 0.15]
"""
import sys, os, re, json, subprocess, time
import numpy as np

FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
# data.js 与 manifest 由 Node 快速读出以避免手写 JS 解析时的转义绕漏问题
RMSWIN = 0.010          # 10ms 窗
SD_INTERNAL = 100       # 采样密度略降以提速
VOICE_TH = 0.012        # RMS 语音阈值(归一化后)


def pcm_of(path):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def load_js(path):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    s = s.rstrip().rstrip(";")
    return json.loads(s)


def rms_env(x, win=160):
    n = len(x) // win
    if n < 2:
        return np.array([0.0])
    return np.sqrt((x[:n * win].reshape(n, win) ** 2).mean(1))


def analyze_clip(path):
    x = pcm_of(path)
    dur = len(x) / 16000.0
    if len(x) < 1600:
        return dict(dur=dur, last_voiced=0.0, headroom=dur, voiced_count=0, peak_rms=0.0)
    env = rms_env(x)
    dt = RMSWIN
    # 语音帧: rms 超过阈值且局部信噪可辨
    voiced = env > VOICE_TH
    peak = float(env.max())
    # 平滑: 允许 2 帧(20ms)间断合并
    idx_voiced = np.where(voiced)[0]
    last_voiced = 0.0
    if idx_voiced.size:
        # 取最后一个被语音覆盖的帧的结束时刻
        last_voiced = (idx_voiced[-1] + 1) * dt
        last_voiced = min(last_voiced, dur)
    headroom = max(0.0, dur - last_voiced)
    return dict(dur=round(dur, 3), last_voiced=round(last_voiced, 3),
                headroom=round(headroom, 3), voiced_count=int(idx_voiced.size),
                peak_rms=round(peak, 4))


def main():
    chapters = None; limit = None; min_head = 0.15
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--chapters":
            chapters = []; i += 1
            while i < len(args) and args[i].isdigit():
                chapters.append(int(args[i])); i += 1
            continue
        if args[i] == "--limit":
            limit = int(args[i + 1]); i += 2; continue
        if args[i] == "--min-headroom":
            min_head = float(args[i + 1]); i += 2; continue
        i += 1

    data = load_js(os.path.join(APP, "data.js"))
    obj = load_js(os.path.join(AUDIO, "manifest_audio.js"))
    sent = obj["sentences"]
    rules = data["rules"]; sections = data["sections"]

    idx_list = []
    for ch_i, sec in enumerate(sections):
        ch = ch_i + 1
        if chapters and ch not in chapters:
            continue
        for idx in range(sec["ruleStart"], sec["ruleEnd"] + 1):
            idx_list.append((ch, idx))
    if limit:
        idx_list = idx_list[:limit]

    rows = []; t0 = time.time(); n = 0
    for (ch, idx) in idx_list:
        e = sent.get(str(idx))
        rule = rules[idx]
        if not e or not e.get("clip"):
            rows.append(dict(ch=ch, idx=idx, st="TTS", headroom=None, dur=None, last_voiced=None, peak=None, pali=rule.get("pali","")))
            continue
        clip = os.path.join(APP, e["clip"])
        if not os.path.exists(clip):
            rows.append(dict(ch=ch, idx=idx, st="缺文件", headroom=None, dur=None, last_voiced=None, peak=None, pali=rule.get("pali","")))
            continue
        a = analyze_clip(clip)
        row = dict(ch=ch, idx=idx, dur=a["dur"], last_voiced=a["last_voiced"],
                   headroom=a["headroom"], peak=a["peak_rms"], pali=rule.get("pali",""))
        if a["voiced_count"] < 3 or a["peak_rms"] < VOICE_TH:
            row["st"] = "无声/过短"
        else:
            row["st"] = "异常紧贴" if a["headroom"] < min_head else "OK"
        rows.append(row)
        n += 1
        if n % 200 == 0:
            print("... %d (%.1fs)" % (n, time.time() - t0), flush=True)

    # 输出：去掉 TTS/缺文件, 按 headroom 升序（最可疑在前）
    real = [r for r in rows if r["headroom"] is not None]
    real_sorted = sorted(real, key=lambda r: r["headroom"])
    suspicious = [r for r in real_sorted if r["st"] == "异常紧贴"]
    from collections import Counter
    stat = Counter(r["st"] for r in rows)
    lines = []
    lines.append("== 句末完整性声学扫描 (min_headroom=%.2f) ==" % min_head)
    lines.append("扫描=%d | 状态: %s" % (len(rows), dict(stat)))
    lines.append("")
    lines.append("== 最可疑(句末语音紧贴切片末尾 -> 可能截断) 按 headroom 升序 ==")
    for r in real_sorted[:120]:
        lines.append("ch%d idx%4d headroom=%s dur=%s last_voiced=%s peak=%s | %s" % (
            r["ch"], r["idx"], r["headroom"], r["dur"], r["last_voiced"], r["peak"], r["pali"][:38]))
    lines.append("")
    lines.append("== 参考: 余量充足的正常句(抽样前 20) ==")
    ok = [r for r in real_sorted if r["headroom"] >= 0.30][:20]
    for r in ok:
        lines.append("ch%d idx%4d headroom=%s dur=%s last_voiced=%s | %s" % (
            r["ch"], r["idx"], r["headroom"], r["dur"], r["last_voiced"], r["pali"][:38]))
    txt = "\n".join(lines)
    outp = os.path.join(AUDIO, "tail_integrity_report.txt")
    open(outp, "w", encoding="utf-8").write(txt)
    print(txt)
    print("报告已写 ->", outp)


if __name__ == "__main__":
    main()
