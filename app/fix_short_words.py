#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复各章中仍含"过短词(<MINW, aligner 给末词/短词零宽)"的句子。
自动扫描 chN_align.json, 对任一含过短词的句子用字符加权重写逐词时间(不动音频切片)。
用法: python fix_short_words.py --chapters 2 3
写完各自 chN_align.json 后跑 merge_align_to_manifest.py 同步到 manifest_audio.js。
"""
import sys, os, json, shutil, time, argparse
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
MINW = 0.10


def fix_chapter(ch):
    fp = os.path.join(AUDIO, "ch%d_align.json" % ch)
    if not os.path.exists(fp):
        print("SKIP ch%d: 无 %s" % (ch, os.path.basename(fp))); return 0
    al = json.load(open(fp, encoding="utf-8"))
    bak = fp + ".bak_fixshort_%s" % time.strftime("%Y%m%d_%H%M%S")
    shutil.copy(fp, bak)
    fixed = 0
    for k, rec in al.items():
        aw = rec.get("words", [])
        dur = rec.get("t1", 0)
        n = len(aw)
        if n == 0 or dur <= 0:
            continue
        if not any((w.get("t1", 0) - w.get("t0", 0)) < MINW for w in aw):
            continue
        weights = [max(1, len((w.get("p") or "").strip())) for w in aw]
        total_w = sum(weights)
        # 每词保底 MINW, 剩余时长按字符权重分配, 保证总长=dur 且无词<MINW
        if n * MINW >= dur:
            widths = [dur / n] * n
        else:
            widths = [MINW + (dur - n * MINW) * w / total_w for w in weights]
        neww = []
        cursor = 0.0
        for i in range(n):
            t0 = round(cursor, 3)
            t1 = round(min(dur, cursor + widths[i]), 3)
            if t1 <= t0:
                t1 = min(dur, t0 + MINW)
            neww.append({"p": aw[i].get("p", ""), "t0": t0, "t1": t1})
            cursor = t1
        rec["words"] = neww
        fixed += 1
        mind = min(w["t1"] - w["t0"] for w in neww)
        print("  ch%d idx %s 重写 %d 词, dur=%.2f, 最短词=%.3fs" % (ch, k, n, dur, mind))
    if fixed:
        json.dump(al, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
        print("ch%d: 修复 %d 句; 写回 %s ; 备份 %s" % (ch, fixed, fp, bak))
    else:
        print("ch%d: 无过短词, 未改动" % ch)
    return fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", nargs="+", type=int, required=True)
    args = ap.parse_args()
    for ch in args.chapters:
        fix_chapter(ch)
    print("请接着运行: python merge_align_to_manifest.py && python proofread_ch.py --chapters %s"
          % " ".join(str(c) for c in args.chapters))


if __name__ == "__main__":
    main()
