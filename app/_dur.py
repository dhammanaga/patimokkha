#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出 sent_new 指定区间 mp3 的时长(用 ffmpeg 解码计长)。"""
import sys, os, subprocess, re
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
D = r"C:\Users\dhamm\WorkBuddy\巴帝摩卡背诵\app\audio\sent_new"

a = int(sys.argv[1]); b = int(sys.argv[2])
for i in range(a, b + 1):
    p = os.path.join(D, "%d.mp3" % i)
    if not os.path.exists(p):
        print("%4d  MISSING" % i); continue
    r = subprocess.run([FFMPEG, "-i", p], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr or "")
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        print("%4d  %6.2fs  %8d B" % (i, dur, os.path.getsize(p)))
    else:
        print("%4d  ??  %8d B" % (i, os.path.getsize(p)))
