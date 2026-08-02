#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按修复清单重切句子末尾(恢复被切尾音):
- 对 final_fixset_newend.json 中 new_end>old_end+0.02 的句子
- 从源 wav (chN_complete.wav, 16k) 重切 [start, new_end], start=当前clip源起点(不移动),
  只用 ffmpeg -c copy; new_end 为修复后静音边界
- 重算词时: word_global(源秒) 相对 start 平移; 末词 t1 强制 = newextent
- 重切写入 sent_new/{idx}.mp3(覆盖), 并把新词时写回 chN_align.json(目标待merge)
用法: python recut_fix.py
"""
import os, json, re, subprocess, shutil, time, sys
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
SENT_NEW = os.path.join(AUDIO, "sent_new")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
LEAD = 0.12
TAIL = 0.40
SR = 16000
sys.path.insert(0, AUDIO)
from _ch_src_map import CH_SRC


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def main():
    data = json.loads(load_js(os.path.join(APP, "data.js")))
    obj = json.loads(load_js(os.path.join(AUDIO, "manifest_audio.js")))
    msent = obj["sentences"]; sections = data["sections"]
    fix = json.load(open(os.path.join(AUDIO, "final_fixset_newend.json"), encoding="utf-8"))
    # 只取需扩展的
    act = [f for f in fix if f["new_end"] > f["old_end"] + 0.02]
    print("将重切:%d 句" % len(act))

    # 备份将改动的 sent_new mp3
    bak = os.path.join(AUDIO, "sent_new_bak_recut_fix_%s" % time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(bak, exist_ok=True)
    n_bak = 0
    touched = set(os.path.join(SENT_NEW, "%d.mp3" % f["idx"]) for f in act)
    for p in touched:
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(bak, os.path.basename(p)))
            n_bak += 1
    print("已备份改动 mp3 -> %s (%d)" % (bak, n_bak))

    # 分组: 每章读一次 raw
    bych = {}
    for f in act:
        bych.setdefault(f["ch"], []).append(f)

    done = []
    for ch, flist in bych.items():
        rawp = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
        raw = json.load(open(rawp, encoding="utf-8"))
        bounds = {int(k): tuple(v) for k, v in raw["bounds"].items()}
        idxs = sorted(bounds); D = raw.get("D", 0.0)
        wav = CH_SRC.get(ch)
        if not wav or not os.path.exists(wav):
            print("  [WARN] ch%d 源mp3缺失,跳过" % ch); continue
        for f in flist:
            idx = f["idx"]
            g0, _ = bounds[idx]
            # 用当前 manifest 时长反推 start, 保证新旧切片同一起点(杜绝 start 漂移)
            cur_rec = msent.get(str(idx), {})
            cur_dur = cur_rec.get("t1")
            if not cur_dur:
                print("  [skip] ch%d idx%d manifest无此句,跳过" % (ch, idx)); continue
            start = round(f["old_end"] - cur_dur, 3)
            if start < -0.05:
                print("  [skip] ch%d idx%d start<0,跳过" % (ch, idx)); continue
            new_end = f["new_end"]
            if new_end <= start:
                print("  [skip] ch%d idx%d new_end<=start, 跳过" % (ch, idx)); continue
            dur = new_end - start
            nstart, nend = start, new_end
            outpath = os.path.join(SENT_NEW, "%d.mp3" % idx)
            r = subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % nstart, "-to", "%.3f" % nend,
                                "-i", wav, "-c", "copy", outpath],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode != 0:
                print("  [ERR] ch%d idx%d 重切失败" % (ch, idx)); continue
            done.append(dict(ch=ch, idx=idx, new_dur=round(dur, 3)))
            print("  [OK] ch%d idx%4d new_end=%.2f dur=%.2fs" % (ch, idx, new_end, dur))

    json.dump(done, open(os.path.join(AUDIO, "recut_done.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("重切完成, 已记录 %d 句 -> audio/recut_done.json" % len(done))


if __name__ == "__main__":
    main()
