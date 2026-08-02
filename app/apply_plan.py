#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 recut_plan.json 全面重切 + 词时重算(尊者原则: 本句完整优先)。
- 每句: ffmpeg -ss [start] -to [end] 源mp3 -> sent_new/{idx}.mp3  (start 往前含上句尾音)
- 词时: 用 chN_align_raw.world_global(源秒) 相对新 start 平移; 末词 t1=dur
- 写 recut_done.json 给 merge 使用
用法: python apply_plan.py [--limit N] (缺省全量)
"""
import os, json, re, sys, subprocess, time, shutil
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
SENT_NEW = os.path.join(AUDIO, "sent_new")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
sys.path.insert(0, AUDIO)
from _ch_src_map import CH_SRC


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def main():
    limit = None
    maxidx = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--maxidx" in sys.argv:
        maxidx = int(sys.argv[sys.argv.index("--maxidx") + 1])
    plan = json.load(open(os.path.join(AUDIO, "recut_plan.json"), encoding="utf-8"))
    if maxidx is not None:
        plan = [p for p in plan if p["idx"] <= maxidx]
    if limit:
        plan = plan[:limit]
    data = json.loads(load_js(os.path.join(APP, "data.js")))
    rules = data["rules"]
    obj = json.loads(load_js(os.path.join(AUDIO, "manifest_audio.js")))
    msent = obj["sentences"]

    done = []          # 仅记录
    records = {}       # key=(ch,idx) -> full sentence record (含重算词时)
    raw_cache = {}
    for it, p in enumerate(plan):
        ch, idx = p["ch"], p["idx"]
        if ch not in raw_cache:
            raw_cache[ch] = json.load(open(os.path.join(AUDIO, "ch%d_align_raw.json" % ch),
                                           encoding="utf-8"))
        raw = raw_cache[ch]
        wg = {int(k): [tuple(w) for w in v] for k, v in raw["word_global"].items()}
        ws = wg.get(idx, [])
        orig = rules[idx].get("words", [])
        olen = len(orig)
        repN = len(ws) // olen if olen else 1
        wav = CH_SRC.get(ch)
        start, end = p["start"], p["end"]
        dur = end - start
        out = os.path.join(SENT_NEW, "%d.mp3" % idx)
        r = subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % start, "-to", "%.3f" % end,
                            "-i", wav, "-c", "copy", out],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode != 0:
            print("ERR ch%d idx%d" % (ch, idx)); continue
        # 重算词时: word_global(源秒) 相对新 start 平移; 末词 t1=dur(完整)
        rel = []
        for j, (wt0, wt1) in enumerate(ws):
            oi = j % olen
            rel.append({"p": orig[oi].get("p", ""),
                        "t0": round(max(0.0, wt0 - start), 3),
                        "t1": round(min(dur, wt1 - start), 3)})
        if rel:
            rel[-1]["t1"] = round(dur, 3)
        records[(ch, idx)] = {"clip": "audio/sent_new/%d.mp3" % idx,
                              "t0": 0, "t1": round(dur, 3),
                              "rep": repN, "words": rel}
        done.append(dict(ch=ch, idx=idx, new_dur=round(dur, 3)))
        if it % 200 == 0:
            print("... %d" % it, flush=True)
    json.dump(done, open(os.path.join(AUDIO, "recut_done.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 记录完整词时记录供 merge 使用
    json.dump({("%d_%d" % k): v for k, v in records.items()},
              open(os.path.join(AUDIO, "recut_records.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("重切完成 %d 句" % len(done))


if __name__ == "__main__":
    main()
