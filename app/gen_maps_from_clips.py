#!/usr/bin/env python3
"""用【当前】manifest_audio.js 的 clip 重建 chN_map.json（精确时长 + 累计 offset），
并保证 chN_full.m4a 与地图一致（若现有 m4a 总时长与累计不符则重新拼接）。
目的：修复 annotate3.html 连续音轨导航的「串句」（offset 漂移）。
注意：本脚本只读 clip 路径与文件，不改 manifest 的文本/时间字段。
"""
import sys, os, re, json, subprocess, shutil
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SR, CHn, BPS = 44100, 1, 2


def exact_dur(f):
    p = subprocess.run([FFMPEG, "-i", f, "-vn", "-acodec", "pcm_s16le",
                        "-ar", str(SR), "-ac", str(CHn), "-f", "s16le", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return p.stdout.__len__() / (SR * CHn * BPS)


def main():
    obj = FA.load_js(os.path.join(AUDIO, "manifest_audio.js"))
    sent = obj["sentences"]
    data = FA.load_js(os.path.join(APP, "data.js"))
    sections = data.get("sections", [])
    for sec in sections:
        ch = sec["order"] + 1
        start, end = sec["ruleStart"], sec["ruleEnd"]
        idxs = []
        for i in range(start, end + 1):
            e = sent.get(str(i))
            if e and e.get("clip") and re.match(r"^audio/sent", e["clip"] or ""):
                f = os.path.join(APP, e["clip"])
                if os.path.exists(f):
                    idxs.append(i)
        if not idxs:
            print("ch%d: 无 clip，跳过" % ch)
            continue
        # 计算时长 + 累计 offset
        mapd = []
        offset = 0.0
        list_lines = []
        for i in idxs:
            f = os.path.join(APP, sent[str(i)]["clip"])
            d = exact_dur(f)
            mapd.append({"idx": i, "offset": round(offset, 3), "dur": round(d, 3)})
            offset += d
            list_lines.append("file '%s'" % f.replace("'", "'\\''"))
        total = offset
        m4a = os.path.join(AUDIO, "ch%d_full.m4a" % ch)
        need_rebuild = True
        if os.path.exists(m4a):
            try:
                cur = exact_dur(m4a)
                if abs(cur - total) < 0.05:
                    need_rebuild = False
            except Exception:
                need_rebuild = True
        if need_rebuild:
            txt = os.path.join(AUDIO, "_ch%d_concat.txt" % ch)
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write("\n".join(list_lines) + "\n")
            subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0",
                           "-i", txt, "-c", "copy", m4a],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("ch%d: 重建 m4a (%.1fs, %d 句)" % (ch, total, len(idxs)))
        else:
            print("ch%d: m4a 已一致，仅重写 map (%.1fs, %d 句)" % (ch, total, len(idxs)))
        json.dump(mapd, open(os.path.join(AUDIO, "ch%d_map.json" % ch), "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
