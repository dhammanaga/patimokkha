#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""决定性句末截断判定（自由 CTC 探针）：
连接诵诵法句间几乎无停顿, 单纯"clip_end 后还有语音"不能区分
  (a) 本句末词尾巴被切掉(真截断)  vs  (b) 下一句开头紧接(干净切)。
本脚本用自由 CTC 解码源录音 [clip_end, clip_end+0.8s] 窗口, 读出实际字符序列,
再与"本句末词后缀"和"下句首词前缀"做模糊匹配, 依据**词形学证据**判定:

- 解码尾段更像"本句末词的尾巴" -> 本句被拦腰切断(真截断, 需修)
- 解码尾段更像"下句开头"      -> 边界干净, 句末完整(不需修)
- 输出带 conf 分数, 供人工复核。

用法: python ctc_tail_probe.py [--chapters 2 3 ...] [--limit N]
"""
import sys, os, json, re, subprocess
import numpy as np
import difflib

SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
CHUNK = 400000
TAIL = 0.40
_DIAC = {"ā": "a", "ī": "i", "ū": "u", "ṅ": "n", "ñ": "n", "ṇ": "n", "ṭ": "t",
         "ḍ": "d", "ḷ": "l", "ṃ": "m", "ḥ": "h", "ś": "s", "ṣ": "s", "ṛ": "r", "·": ""}


def norm(s):
    s = (s or "").lower()
    for k, v in _DIAC.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z]", "", s)
    return s


def sim(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_js(path):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    s = s.rstrip().rstrip(";")
    return json.loads(s)


def decode_window(sess, rev, x, f0, f1):
    """解码源序列 [f0,f1) 帧(16k采样) 的自由CTC文本。"""
    xw = x[f0:f1].copy()
    if xw.size < 1600:
        return ""
    xw = xw - xw.mean(); sd = xw.std()
    if sd > 1e-5:
        xw = xw / sd
    ems = []
    for s in range(0, len(xw), CHUNK):
        e = min(len(xw), s + CHUNK)
        ems.append(sess.run(None,
            {"input_values": xw[s:e].astype(np.float32).reshape(1, -1),
             "attention_mask": np.ones((1, len(xw[s:e])), dtype=np.int64)})[0][0])
    em = np.concatenate(ems, axis=0)
    idx = em.argmax(axis=1)
    out = []; prev = -1
    for t in range(len(idx)):
        c = int(idx[t])
        if c <= 2:
            prev = -1; continue
        if c == prev:
            continue
        prev = c; out.append(rev[c])
    return norm("".join(out))


def main():
    chapters = None; limit = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--chapters":
            chapters = []; i += 1
            while i < len(args) and args[i].isdigit():
                chapters.append(int(args[i])); i += 1
            continue
        if args[i] == "--limit":
            limit = int(args[i + 1]); i += 2; continue
        i += 1

    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]; sections = data["sections"]
    obj = load_js(os.path.join(AUDIO, "manifest_audio.js"))
    msent = obj["sentences"]

    rows = []
    for ch_i, sec in enumerate(sections):
        ch = ch_i + 1
        if chapters and ch not in chapters:
            continue
        A, B = sec["ruleStart"], sec["ruleEnd"]
        rawp = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
        wav = os.path.join(AUDIO, "ch%d_complete.wav" % ch)
        if not (os.path.exists(rawp) and os.path.exists(wav)):
            continue
        raw = json.load(open(rawp, encoding="utf-8"))
        if "bounds" not in raw or not raw["bounds"]:
            continue
        bounds = {int(k): tuple(v) for k, v in raw["bounds"].items()}
        idxs = sorted(bounds)
        D = raw.get("D", 0.0)
        x = np.frombuffer(open(wav, "rb").read(), dtype=np.int16).astype(np.float32) / 32768.0
        for p_i, idx in enumerate(idxs):
            if p_i == 0:
                continue  # 首句无"上一句", 但仍有句末; 用 clip_end=G1[0]+TAIL 判定
            ms = msent.get(str(idx))
            if not ms or not ms.get("clip"):
                continue
            g0, g1 = bounds[idx]
            if p_i == len(idxs) - 1:
                cust_end = min(D, g1 + TAIL)
            else:
                g0_next, _ = bounds[idxs[p_i + 1]]
                cust_end = (g1 + g0_next) / 2.0
            cust_end = min(cust_end, D - 0.05)
            f0 = int(max(0, cust_end) * FA.SR)
            f1 = int(min(D, cust_end + 0.8) * FA.SR)
            dec_tail = decode_window(sess, rev, x, f0, f1)
            # 本句末词
            lw = ""
            wds = rules[idx].get("words", [])
            if wds:
                lw = norm(wds[-1].get("p", ""))
            lw_suf = lw[-6:] if len(lw) > 6 else lw
            # 下句首词
            nw = ""
            if p_i + 1 < len(idxs):
                nidx = idxs[p_i + 1]
                nwds = rules[nidx].get("words", [])
                if nwds:
                    nw = norm(nwds[0].get("p", ""))
            s_nw = sim(dec_tail, nw)          # 更像下句首词?
            s_lw = sim(dec_tail, lw_suf) if lw_suf else 0.0  # 更像本句末词尾巴?
            # 判定
            if s_nw >= s_lw and s_nw > 0.5:
                st = "边界干净"
            elif s_lw > s_nw and s_lw > 0.5:
                st = "真截断-尾词"
            else:
                st = "存疑"
            rows.append(dict(ch=ch, idx=idx, cust_end=round(cust_end,3),
                             dec=dec_tail, lw=lw, lw_suf=lw_suf, nw=nw,
                             s_lw=round(s_lw,2), s_nw=round(s_nw,2), st=st,
                             pali=rules[idx].get("pali","")))
    import collections
    stat = collections.Counter(r["st"] for r in rows)
    print("== 决定性命中 (自由CTC探针) ==")
    print("探针=%d | 状态: %s" % (len(rows), dict(stat)))
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[r["ch"]][r["st"]] += 1
    for ch in sorted(by):
        print(" ch%d: %s" % (ch, dict(by[ch])))
    # 真截断
    t = [r for r in rows if r["st"] == "真截断-尾词"]
    print("\n== 真截断候选 (末词尾巴在clip后仍被念出) ==")
    for r in t:
        print("ch%d idx%4d end=%.3f s_lw=%s s_nw=%s | 末词:[%s] 探针dec:[%s] | %s" % (
            r["ch"], r["idx"], r["cust_end"], r["s_lw"], r["s_nw"],
            r["lw"], r["dec"][:40] or "-", r["pali"][:34]))
    # 存疑(证据不足)
    u = [r for r in rows if r["st"] == "存疑"]
    print("\n== 存疑 (证据不足, 需人工) ==")
    for r in u[:60]:
        print("ch%d idx%4d end=%.3f s_lw=%s s_nw=%s | 末词[%s] 探针dec[%s] | %s" % (
            r["ch"], r["idx"], r["cust_end"], r["s_lw"], r["s_nw"],
            r["lw"], r["dec"][:36] or "-", r["pali"][:30]))
    outp = os.path.join(AUDIO, "ctc_tail_probe.txt")
    open(outp, "w", encoding="utf-8").write(
        ("统计: %s\n" % dict(stat)) + "\n".join(
            "ch%d idx%4d %-6s end=%.3f lw[%s] nw[%s] dec[%s] | %s" % (
                r["ch"], r["idx"], r["st"], r["cust_end"], r["lw"], r["nw"],
                r["dec"][:40], r["pali"]) for r in rows))
    print("详情已写 ->", outp)


if __name__ == "__main__":
    main()
