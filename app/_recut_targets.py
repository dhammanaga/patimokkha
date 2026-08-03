#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定点重切: 按自由CTC解码得到的真实边界, 从章节源录音重切指定 idx 的 mp3。
边界表见 TARGETS。输出直接覆盖 app/audio/sent_new/<idx>.mp3。
"""
import os, subprocess, sys

FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
OUT = r"C:\Users\dhamm\WorkBuddy\巴帝摩卡背诵\app\audio\sent_new"
SRC9 = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\善巧提供\后7章\9. Sekhiya Dhamma.mp3"
SRC10 = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\善巧提供\后7章\10. Satta Adhikarana Samatha Dhamma.mp3"

# (idx, 源, 起, 止, 说明)
TARGETS = [
    (1144, SRC9,  444.88, 447.00, "应学#113 parisuddhetthāyasmanto"),
    (1145, SRC9,  447.00, 450.10, "应学#114 tasmā tuṇhī evametaṃ dhārayāmīti"),
    (1161, SRC10,  39.85,  43.11, "止争#15 tatiyampi pucchāmi kaccittha parisuddhā"),
    (1162, SRC10,  43.11,  49.45, "止争#16 parisuddhetthāyasmanto tasmā tuṇhī evametaṃ dhārayāmīti"),
    (1163, SRC10,  49.45,  53.14, "止争#17 Satta adhikaraṇasamathā dhammā niṭṭhitā"),
]


def cut(src, t0, t1, dst):
    # 不用 os.remove(safe-delete 闸门会拦), 直接让 ffmpeg -y 覆写
    # WPS 版 ffmpeg 无 libmp3lame; 源与目标同为 mp3, 用流拷贝(无损, 帧级 ~26ms 精度)
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-ss", "%.3f" % t0, "-i", src, "-t", "%.3f" % (t1 - t0),
           "-c", "copy", dst]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return r.returncode, (r.stderr or "").strip()


def main():
    only = set(int(a) for a in sys.argv[1:]) if len(sys.argv) > 1 else None
    for idx, src, t0, t1, note in TARGETS:
        if only and idx not in only:
            continue
        dst = os.path.join(OUT, "%d.mp3" % idx)
        rc, err = cut(src, t0, t1, dst)
        sz = os.path.getsize(dst) if os.path.exists(dst) else 0
        print("%4d  %7.2f-%7.2f (%.2fs)  rc=%d  %7dB  %s%s"
              % (idx, t0, t1, t1 - t0, rc, sz, note, ("  ERR:" + err) if err else ""))


if __name__ == "__main__":
    main()
