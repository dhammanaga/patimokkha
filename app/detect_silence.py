#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""细粒度静音检测: 在 idx 64-79 所在区域(约 140-166s)找出所有句间停顿,
用作逐句强制对齐的真实边界(地面真相)。"""
import sys, os, json, time
import numpy as np
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:\Users\dhamm\WorkBuddy\巴帝摩卡背诵\app"
AUDIO = os.path.join(APP, "audio")
AUDIO_SRC = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\巴帝摩卡诵.善吉祥长老\序20220805_091549.mp3"

REGION = (140.0, 167.0)  # 关注区域
WIN = 0.020              # 20ms 能量窗
HOP = 0.010              # 10ms 跳
MIN_GAP = 0.05           # 最小停顿时长(秒), 过滤词内微小停顿
# 阈值: 相对整段 RMS 的倍数
THRESH_REL = 0.06

def main():
    CACHE = os.path.join(AUDIO, "ch2_complete.wav")
    x, sr = FA.decode_real(AUDIO_SRC, FFMPEG, APP, CACHE)
    print("解码 %.2fs, sr=%d" % (len(x)/FA.SR, FA.SR), flush=True)
    x = x.astype(np.float32)
    overall_rms = float(np.sqrt(np.mean(x**2)))
    print("整段 RMS=%.5f, 阈值=%.5f" % (overall_rms, overall_rms*THRESH_REL), flush=True)

    f0 = int(REGION[0]*FA.SR); f1 = int(REGION[1]*FA.SR)
    xs = x[f0:f1]
    n = len(xs); win = max(1, int(WIN*FA.SR)); hop = max(1, int(HOP*FA.SR))
    energy = []
    for s in range(0, n-hop, hop):
        seg = xs[s:s+win]
        if len(seg) < win: seg = xs[s:]; 
        energy.append(float(np.sqrt(np.mean(seg**2))))
    energy = np.array(energy, dtype=np.float64)
    # 平滑
    k = max(1, int(0.05*FA.SR//hop))
    if k > 1:
        energy = np.convolve(energy, np.ones(k)/k, mode="same")
    times = np.arange(len(energy))*hop/FA.SR + REGION[0]
    thr = overall_rms*THRESH_REL
    silent = energy < thr
    # 找连续静音段
    gaps = []
    i = 0
    while i < len(silent):
        if silent[i]:
            j = i
            while j < len(silent) and silent[j]:
                j += 1
            t0 = times[i]; t1 = times[min(j, len(times)-1)]
            if t1 - t0 >= MIN_GAP:
                gaps.append((t0, t1, float(energy[(i+min(j,len(times)-1))//2] if False else 0)))
            i = j
        else:
            i += 1
    # 重新算每个 gap 的平均能量(供参考)
    gaps2 = []
    for (t0, t1, _) in gaps:
        a = int((t0-REGION[0])*FA.SR//hop); b = int((t1-REGION[0])*FA.SR//hop)
        a = max(0, min(len(energy)-1, a)); b = max(0, min(len(energy)-1, b))
        gaps2.append((t0, t1, float(np.mean(energy[a:b]))))
    print("\n== 静音段(>=%.2fs) 在 [%.1f, %.1f] ==" % (MIN_GAP, REGION[0], REGION[1]))
    for (t0,t1,e) in gaps2:
        print("  %.2f - %.2f  (长 %.2fs, 能量 %.4f)" % (t0, t1, t1-t0, e))
    # 中心点
    centers = [ (t0+t1)/2 for (t0,t1,_) in gaps2 ]
    print("\n== 静音中心(用于切句) ==", ["%.2f"%c for c in centers])
    # 段统计
    edges = [REGION[0]] + centers + [REGION[1]]
    print("\n== 若以上中心全作边界, 分段时长 ==")
    for k in range(len(edges)-1):
        print("  seg%d: %.2f-%.2f = %.2fs" % (k, edges[k], edges[k+1], edges[k+1]-edges[k]))

if __name__ == "__main__":
    main()
