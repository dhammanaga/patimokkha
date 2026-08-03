#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""尾部切分修复：把被 CTC 偏早的句末边界，改用「静音段」重新判定。

背景（根因）
------------
CTC 强制对齐有众所周知的 "peaky" 特性：它在音素起点附近打尖峰，随后立刻输出
blank，因此**结束时间(offset)被系统性低估**。之前按 CTC 的 end 直接切片，导致
句末最后一个音节被切掉、掉进下一句开头（如 ch6 `Kathinavaggo paṭhamo`：
482.mp3 只念到 "katinavego ba"，"temo" 跑到 483.mp3 开头）。

方法（不依赖 CTC 的 offset）
---------------------------
相邻两句在源录音里是连续的，把 N 与 N+1 拼回去就还原了原始音频；再用能量
包络找**真正的句间静音段**，在静音里留 pad 重新下刀。边界由声学静音决定，
不再由 CTC 的 offset 决定。

约束：WPS 版 ffmpeg 无 mp3 编码器 → 全程 `-c copy` 流拷贝（帧级 ~26ms 精度）。

用法:
  python _fix_tailcut.py --dry 482            # 只算不改
  python _fix_tailcut.py --apply 482          # 改音频+清单
  python _fix_tailcut.py --scan               # 全库列出候选
  python _fix_tailcut.py --apply --all        # 全量修复
"""
import os, re, json, subprocess, sys, argparse, shutil
import numpy as np

FF = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(APP, "audio", "manifest_audio.js")
TMP = os.path.join(APP, "audio", "_tmp_fix")

SR = 16000
WIN = 0.010          # 10ms 能量窗
TH = 0.012           # 语音能量阈值
SIL_MIN = 0.25       # 认定为句间静音的最短时长
PAD = 0.35           # 静音里给每侧留的余量
WIN_BACK = 1.0       # 从旧边界往前找的范围
WIN_FWD = 3.5        # 往后找的范围
MIN_GAIN = 0.05      # 至少要救回这么多秒才动手
MAX_GAIN = 1.60      # 救回超过这个秒数视为异常(可能吞了下一句), 拒绝自动处理


def chapter_last_idxs():
    """每章最后一句的 idx —— 跨章不可拼接（分属不同源录音文件）"""
    t = open(os.path.join(APP, "data.js"), encoding="utf-8").read()
    m = re.search(r"window\.PATIMOKKHA_DATA\s*=\s*(\{.*\})\s*;?\s*$", t, re.S)
    d = json.loads(m.group(1))
    last = set()
    for sec in d.get("sections", []):
        rs, re_ = sec.get("ruleStart"), sec.get("ruleEnd")
        if rs is None or re_ is None:
            continue
        rules = d["rules"]
        if 0 <= re_ < len(rules):
            last.add(rules[re_]["idx"])
    return last


# ---------- 基础 ----------
def load_manifest():
    t = open(MANIFEST, encoding="utf-8").read()
    m = re.search(r"window\.PM_AUDIO\s*=\s*(\{.*\})\s*;?\s*$", t, re.S)
    return json.loads(m.group(1))


def save_manifest(a):
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("/* 巴帝摩卡音频清单 */\nwindow.PM_AUDIO = ")
        json.dump(a, f, ensure_ascii=False, indent=0)
        f.write(";\n")
    os.replace(tmp, MANIFEST)


def pcm(path):
    r = subprocess.run([FF, "-v", "error", "-i", path, "-ar", str(SR), "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def envelope(x):
    n = int(WIN * SR)
    m = len(x) // n
    return np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(1))


def ffcut(src, t0, dur, dst):
    cmd = [FF, "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % t0,
           "-i", src]
    if dur is not None:
        cmd += ["-t", "%.3f" % dur]
    cmd += ["-c", "copy", dst]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return r.returncode, (r.stderr or "").strip()


def ffjoin(a, b, dst):
    os.makedirs(TMP, exist_ok=True)
    lst = os.path.join(TMP, "_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("file '%s'\nfile '%s'\n" % (a.replace("\\", "/"), b.replace("\\", "/")))
    cmd = [FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
           "-safe", "0", "-i", lst, "-c", "copy", dst]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return r.returncode, (r.stderr or "").strip()


def silence_runs(e, th=TH):
    """返回 [(start_s, end_s), ...] 所有静音段"""
    quiet = e <= th
    runs = []
    i = 0
    n = len(quiet)
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            runs.append((i * WIN, j * WIN))
            i = j
        else:
            i += 1
    return runs


# ---------- 核心 ----------
def plan_pair(a, idx):
    """计算 idx 与 idx+1 的新边界。返回 dict 或 None(跳过)。"""
    s = a["sentences"]
    k, k2 = str(idx), str(idx + 1)
    if k not in s or k2 not in s:
        return dict(idx=idx, skip="缺相邻句")
    pa = os.path.join(APP, s[k]["clip"])
    pb = os.path.join(APP, s[k2]["clip"])
    if not (os.path.exists(pa) and os.path.exists(pb)):
        return dict(idx=idx, skip="文件缺失")

    os.makedirs(TMP, exist_ok=True)
    joined = os.path.join(TMP, "j.mp3")   # 固定名复用，避免堆积上千临时文件
    rc, err = ffjoin(pa, pb, joined)
    if rc != 0:
        return dict(idx=idx, skip="拼接失败:" + err[:60])

    xa = pcm(pa)
    xj = pcm(joined)
    L = len(xa) / SR                      # 旧边界在拼接时间轴上的位置
    total = len(xj) / SR
    e = envelope(xj)

    runs = [r for r in silence_runs(e) if (r[1] - r[0]) >= SIL_MIN]
    cand = [r for r in runs if L - 0.30 <= r[0] <= L + WIN_FWD]
    if not cand:
        return dict(idx=idx, skip="窗口内无静音段", L=L, total=total)
    rs, re_ = cand[0]
    gain = rs - L                          # 为 N 救回的秒数
    pad = min(PAD, (re_ - rs) / 2.0)
    new_end = min(rs + pad, total)

    # 下一句的真实起点：静音结束后第一个"持续 >=0.12s 的有声段"，而不是静音末尾
    # （静音可能被低能量毛刺打断，直接用静音末尾会留下大段空白）
    onset = re_
    need = int(0.12 / WIN)
    i = int(re_ / WIN)
    while i < len(e) - need:
        if np.all(e[i:i + need] > TH):
            onset = i * WIN
            break
        i += 1
    else:
        onset = re_
    new_start = max(min(onset - PAD, total - 0.2), new_end)

    # ---- 防「吃掉下一句」安全阀 ----
    # 相邻两句若连诵无停顿，窗口内第一个静音会落在【下一句说完之后】，
    # 此时按它下刀会把整句 N+1 并进 N。判据：切完后 N+1 里还剩多少自己的语音。
    dur_b_orig = total - L
    dur_b_new = total - new_start
    voiced_b = float(np.sum(e[int(new_start / WIN):] > TH)) * WIN
    if dur_b_new < 0.45 or voiced_b < 0.35 or gain > dur_b_orig * 0.6:
        return dict(idx=idx, L=L, total=total,
                    skip="会吃掉下一句(剩余=%.2fs 剩语音=%.2fs 救回=%.2fs/原下句=%.2fs)"
                         % (dur_b_new, voiced_b, gain, dur_b_orig))

    return dict(idx=idx, L=L, total=total, sil=(rs, re_), gain=gain,
                new_end=new_end, new_start=new_start, joined=joined,
                dur_a_new=new_end, dur_b_new=dur_b_new, voiced_b=voiced_b)


def apply_pair(a, p):
    """按 plan 落盘并同步清单"""
    s = a["sentences"]
    k, k2 = str(p["idx"]), str(p["idx"] + 1)
    pa = os.path.join(APP, s[k]["clip"])
    pb = os.path.join(APP, s[k2]["clip"])
    joined = p["joined"]

    rc1, e1 = ffcut(joined, 0.0, p["new_end"], pa)
    rc2, e2 = ffcut(joined, p["new_start"], None, pb)
    if rc1 or rc2:
        return "切割失败 %s %s" % (e1[:50], e2[:50])

    # --- 清单：N ---
    da = len(pcm(pa)) / SR
    s[k]["t1"] = round(da, 3)
    ws = s[k].get("words") or []
    if ws:
        ws[-1]["t1"] = round(min(p["sil"][0], da), 3)
        if ws[-1]["t1"] <= ws[-1]["t0"]:
            ws[-1]["t1"] = round(ws[-1]["t0"] + 0.05, 3)

    # --- 清单：N+1（整体左移）---
    db = len(pcm(pb)) / SR
    shift = p["new_start"] - p["L"]
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
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    a = load_manifest()
    s = a["sentences"]

    if args.scan or args.all:
        scan = json.load(open(os.path.join(APP, "_tailscan.json")))
        chlast = chapter_last_idxs()
        targets = [int(k) for k, v in scan.items()
                   if not v.get("empty") and v["head"] < 0.12
                   and str(int(k) + 1) in s and int(k) not in chlast]
        targets.sort()
        print("(已排除 %d 个章末句：跨章分属不同源录音，不可拼接)" % len(chlast))
    else:
        targets = args.idxs
    if args.offset:
        targets = targets[args.offset:]
    if args.limit:
        targets = targets[:args.limit]

    print("目标句数:", len(targets))
    done = fixed = skipped = 0
    for idx in targets:
        p = plan_pair(a, idx)
        if p.get("skip"):
            print("  %5d  跳过: %s" % (idx, p["skip"]))
            skipped += 1
            continue
        if p["gain"] < MIN_GAIN:
            print("  %5d  无需修 (gain=%.3fs)" % (idx, p["gain"]))
            skipped += 1
            continue
        if p["gain"] > MAX_GAIN:
            print("  %5d  ⚠ 救回量异常 %.3fs > %.2fs，拒绝自动处理（待人工/CTC 复核）"
                  % (idx, p["gain"], MAX_GAIN))
            skipped += 1
            continue
        print("  %5d  旧边界=%.3f 静音=[%.3f,%.3f] 救回=%.3fs  新: %s=%.3fs %s=%.3fs"
              % (idx, p["L"], p["sil"][0], p["sil"][1], p["gain"],
                 idx, p["dur_a_new"], idx + 1, p["dur_b_new"]))
        if args.apply:
            err = apply_pair(a, p)
            if err:
                print("        ✗ %s" % err)
            else:
                fixed += 1
        done += 1

    if args.apply and fixed:
        save_manifest(a)
        print("\n清单已写回，修复 %d 句对" % fixed)
    print("处理 %d / 跳过 %d" % (done, skipped))


if __name__ == "__main__":
    main()
