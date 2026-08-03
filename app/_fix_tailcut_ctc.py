#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""尾切修复 · CTC 补刀版

适用场景
--------
`_fix_tailcut.py` 用「句间静音」定边界，对**连诵无停顿**的句对无能为力
（窗口内找不到静音段），甚至会把整个下一句吞进来。本脚本改用**词级强制对齐**：
把 N 与 N+1 拼回去，将两句的词序列一起对到拼接音频上，边界取
「N 最后一个词的结束」与「N+1 第一个词的起始」之间。

注意
----
- CTC 的 end 系统性偏早（peaky），故边界向后偏置（gap 的 55%，最少 +0.12s）。
- 仍保留「不吃掉下一句」安全阀。
- 跨章不拼接（分属不同源录音）。
- WPS ffmpeg 无 mp3 编码器 → 全程 `-c copy`。

用法:
  python _fix_tailcut_ctc.py --dry              # 全部候选试算
  python _fix_tailcut_ctc.py --apply --limit 50
  python _fix_tailcut_ctc.py --dry 1152 1160
"""
import os, re, json, subprocess, sys, argparse
import numpy as np

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import src_align as SA
from src_align import align_window
import forced_align as FA

FF = SA.FFMPEG
MANIFEST = os.path.join(APP, "audio", "manifest_audio.js")
TMP = os.path.join(APP, "audio", "_tmp_ctc")
SR = 16000
WIN = 0.010
TH = 0.012
MAX_GAIN = 1.20      # CTC 版更保守
MIN_GAIN = 0.05


def load_manifest():
    t = open(MANIFEST, encoding="utf-8").read()
    return json.loads(re.search(r"window\.PM_AUDIO\s*=\s*(\{.*\})\s*;?\s*$", t, re.S).group(1))


def save_manifest(a):
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("/* 巴帝摩卡音频清单 */\nwindow.PM_AUDIO = ")
        json.dump(a, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    os.replace(tmp, MANIFEST)


def pcm(path):
    r = subprocess.run([FF, "-v", "error", "-i", path, "-ar", str(SR), "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def envelope(x):
    n = int(WIN * SR); m = len(x) // n
    return np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(1))


def ffcut(src, t0, dur, dst):
    cmd = [FF, "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % t0, "-i", src]
    if dur is not None:
        cmd += ["-t", "%.3f" % dur]
    cmd += ["-c", "copy", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.returncode, (r.stderr or "").strip()


def ffjoin(a, b, dst):
    os.makedirs(TMP, exist_ok=True)
    lst = os.path.join(TMP, "_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("file '%s'\nfile '%s'\n" % (a.replace("\\", "/"), b.replace("\\", "/")))
    cmd = [FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
           "-i", lst, "-c", "copy", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.returncode, (r.stderr or "").strip()


def chapter_last_idxs():
    t = open(os.path.join(APP, "data.js"), encoding="utf-8").read()
    d = json.loads(re.search(r"window\.PATIMOKKHA_DATA\s*=\s*(\{.*\})\s*;?\s*$", t, re.S).group(1))
    last = set()
    for sec in d.get("sections", []):
        rs, re_ = sec.get("ruleStart"), sec.get("ruleEnd")
        if rs is None or re_ is None:
            continue
        if 0 <= re_ < len(d["rules"]):
            last.add(d["rules"][re_]["idx"])
    return last


def parse_targets():
    """从 _scan_dry.txt 取「窗口内无静音段」「救回量异常」两类未解决的句对"""
    p = os.path.join(APP, "_scan_dry.txt")
    ids = []
    for ln in open(p, encoding="utf-8"):
        m = re.match(r"\s*(\d+)\s+跳过: 窗口内无静音段", ln)
        if m:
            ids.append(int(m.group(1))); continue
        m = re.match(r"\s*(\d+)\s+⚠ 救回量异常", ln)
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids))


def plan(sess, vocab, a, idx):
    s = a["sentences"]
    k, k2 = str(idx), str(idx + 1)
    if k not in s or k2 not in s:
        return dict(idx=idx, skip="缺相邻句")
    pa = os.path.join(APP, s[k]["clip"]); pb = os.path.join(APP, s[k2]["clip"])
    if not (os.path.exists(pa) and os.path.exists(pb)):
        return dict(idx=idx, skip="文件缺失")
    wa = [w["p"] for w in (s[k].get("words") or []) if w.get("p")]
    wb = [w["p"] for w in (s[k2].get("words") or []) if w.get("p")]
    if not wa or not wb:
        return dict(idx=idx, skip="缺逐词文本")

    os.makedirs(TMP, exist_ok=True)
    joined = os.path.join(TMP, "j.mp3")
    rc, err = ffjoin(pa, pb, joined)
    if rc != 0:
        return dict(idx=idx, skip="拼接失败:" + err[:50])

    xa = pcm(pa); xj = pcm(joined)
    L = len(xa) / SR
    total = len(xj) / SR
    if total > 40:
        return dict(idx=idx, skip="拼接过长(%.1fs)" % total)

    res = align_window(sess, vocab, joined, 0.0, total, wa + wb)
    endA = res[len(wa) - 1][2]
    startB = res[len(wa)][1]
    gap = startB - endA
    boundary = endA + (gap * 0.55 if gap > 0.06 else 0.12)
    boundary = min(max(boundary, 0.2), total - 0.2)

    gain = boundary - L
    dur_b_orig = total - L
    dur_b_new = total - boundary
    e = envelope(xj)
    voiced_b = float(np.sum(e[int(boundary / WIN):] > TH)) * WIN

    if gain < MIN_GAIN:
        return dict(idx=idx, skip="无需修 (gain=%.3f)" % gain, gain=gain)
    if gain > MAX_GAIN:
        return dict(idx=idx, skip="救回量过大 %.3f>%.2f" % (gain, MAX_GAIN), gain=gain)
    if dur_b_new < 0.45 or voiced_b < 0.35 or gain > dur_b_orig * 0.6:
        return dict(idx=idx, skip="会吃掉下一句(剩%.2fs 语音%.2fs)" % (dur_b_new, voiced_b))

    return dict(idx=idx, L=L, total=total, endA=endA, startB=startB, gap=gap,
                boundary=boundary, gain=gain, joined=joined,
                dur_a_new=boundary, dur_b_new=dur_b_new,
                lastw=wa[-1], firstw=wb[0])


def apply_one(a, p):
    s = a["sentences"]
    k, k2 = str(p["idx"]), str(p["idx"] + 1)
    pa = os.path.join(APP, s[k]["clip"]); pb = os.path.join(APP, s[k2]["clip"])
    rc1, e1 = ffcut(p["joined"], 0.0, p["boundary"], pa)
    rc2, e2 = ffcut(p["joined"], p["boundary"], None, pb)
    if rc1 or rc2:
        return "切割失败 %s %s" % (e1[:40], e2[:40])
    da = len(pcm(pa)) / SR
    s[k]["t1"] = round(da, 3)
    ws = s[k].get("words") or []
    if ws:
        ws[-1]["t1"] = round(min(p["endA"], da), 3)
        if ws[-1]["t1"] <= ws[-1]["t0"]:
            ws[-1]["t1"] = round(min(ws[-1]["t0"] + 0.05, da), 3)
    db = len(pcm(pb)) / SR
    shift = p["boundary"] - p["L"]
    s[k2]["t1"] = round(db, 3)
    for w in (s[k2].get("words") or []):
        w["t0"] = round(max(0.0, w["t0"] - shift), 3)
        w["t1"] = round(max(0.05, min(db, w["t1"] - shift)), 3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("idxs", nargs="*", type=int)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    a = load_manifest()
    targets = args.idxs or parse_targets()
    chlast = chapter_last_idxs()
    targets = [i for i in targets if i not in chlast]
    if args.offset:
        targets = targets[args.offset:]
    if args.limit:
        targets = targets[:args.limit]
    print("候选句对:", len(targets), flush=True)

    vocab = json.load(open(SA.VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(SA.MODEL, providers=["CPUExecutionProvider"])

    fixed = skipped = 0
    for n, idx in enumerate(targets, 1):
        try:
            p = plan(sess, vocab, a, idx)
        except Exception as ex:
            print("  %5d  异常: %s" % (idx, repr(ex)[:70])); skipped += 1; continue
        if p.get("skip"):
            print("  %5d  跳过: %s" % (idx, p["skip"])); skipped += 1
        else:
            print("  %5d  L=%.3f 末词%s结束=%.3f 下句%s起=%.3f 边界=%.3f 救回=%.3fs  新:%d=%.2fs %d=%.2fs"
                  % (idx, p["L"], p["lastw"][:12], p["endA"], p["firstw"][:12], p["startB"],
                     p["boundary"], p["gain"], idx, p["dur_a_new"], idx + 1, p["dur_b_new"]), flush=True)
            if args.apply:
                err = apply_one(a, p)
                if err:
                    print("        ✗ " + err)
                else:
                    fixed += 1
        if n % 25 == 0:
            print("  ... %d/%d" % (n, len(targets)), flush=True)
            if args.apply and fixed:
                save_manifest(a)

    if args.apply and fixed:
        save_manifest(a)
    print("\n修复 %d / 跳过 %d" % (fixed, skipped))


if __name__ == "__main__":
    main()
