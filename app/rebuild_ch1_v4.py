#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 第1章 重建 v4 —— 用【权威全局对齐】的"中点边界"逐句切片。
#
# v3 的缺陷: 用"前句末尾推后句开头 + cap + 单调兜底"的级联逻辑, 误差累积,
#   导致 ~20 句被截断/拉伸(如 idx15 实切 3.31s 但完整语音 7.71s; idx13 拉长到 5.00s)。
#   文件能播, 但内容错位 → 用户听到"音频出错"。
#
# 本版修正(无级联、无漂移):
#   每句边界 = 与上一句末尾、下一句开头之间的【静音间隙中点】:
#     start[N] = (g1[N-1] + g0[N]) / 2        (N>0)
#     end[N]   = (g1[N]   + g0[N+1]) / 2      (N<35)
#   首句 start=max(0,g0[0]-LEAD); 末句 end=min(D,g1[35]+TAIL)。
#   这样: start[N] < g0[N] < g1[N] < end[N] (完整包含本句), 且 end[N] == start[N+1] (不重叠不空缺)。
#   词时 = 全局对齐词时平移到本句起点(精确, 无需再对齐)。
import sys, os, json, subprocess, shutil, time
import numpy as np
import align_ch1_complete as AC
from align_ch1_complete import FFMPEG, APP, AUDIO, COMPLETE, SENT_NEW
import merge_align_to_manifest as M
import forced_align as FA

SR = AC.FA.SR
LEAD = 0.12
TAIL = 0.40
MIN_DUR = 0.6


def main():
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]

    print("加载权威全局对齐 ch1_align_raw.json ...", flush=True)
    raw = json.load(open(os.path.join(AUDIO, "ch1_align_raw.json"), encoding="utf-8"))
    wg = {int(k): [tuple(w) for w in v] for k, v in raw["word_global"].items()}
    D = raw["D"]
    G0 = {i: min(w[0] for w in wg[i]) for i in range(36)}
    G1 = {i: max(w[1] for w in wg[i]) for i in range(36)}

    # 中点边界(无级联)
    start = [0.0] * 36
    end = [0.0] * 36
    start[0] = max(0.0, G0[0] - LEAD)
    for i in range(1, 36):
        start[i] = (G1[i - 1] + G0[i]) / 2.0
    for i in range(0, 35):
        end[i] = (G1[i] + G0[i + 1]) / 2.0
    end[35] = min(D, G1[35] + TAIL)
    for i in range(36):
        if end[i] - start[i] < MIN_DUR:
            end[i] = start[i] + max(MIN_DUR, (G1[i] - G0[i]) + 0.3)

    has = os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW))
    BAK = os.path.join(AUDIO, "sent_new_bak_v4_%s" % time.strftime("%Y%m%d_%H%M%S"))
    if has:
        shutil.copytree(SENT_NEW, BAK)
        print("备份旧 sent_new ->", BAK, flush=True)
    os.makedirs(SENT_NEW, exist_ok=True)

    ch1 = {}
    for idx in range(0, 36):
        st0, st1 = start[idx], end[idx]
        clip = "audio/sent_new/%d.mp3" % idx
        out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                        "-i", COMPLETE, "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur = round(st1 - st0, 3)
        orig = rules[idx]["words"]
        olen = len(orig)
        repN = len(wg[idx]) // olen if olen else 1
        rel = []
        for j, (wt0, wt1) in enumerate(wg[idx]):
            oi = j % olen
            rel.append({"p": orig[oi].get("p", ""),
                        "t0": round(max(0.0, wt0 - st0), 3),
                        "t1": round(min(dur, wt1 - st0), 3)})
        ch1[str(idx)] = {"clip": clip, "t0": 0, "t1": dur, "rep": repN, "words": rel}
        print("  idx %2d -> %.2f~%.2fs (%.2fs, %d 词, rep=%d)" %
              (idx, st0, st1, dur, len(rel), repN), flush=True)

    json.dump(ch1, open(os.path.join(AUDIO, "ch1_align.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("ch1_align.json 写出 (%d 句)" % len(ch1), flush=True)

    print("\n=== 合并回 manifest_audio.js ===", flush=True)
    M.main()


if __name__ == "__main__":
    main()
