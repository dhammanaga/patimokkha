#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复句终验: 对重切后的 384 句, 自由 CTC 解码新 clip, 检查"末词的规范化字符"是否
出现在解码文本末段。这是"每个词完整发音(尤其末词尾音)"的直接证据。
- 用末词的后缀片段(最后 min(6,len) 字符)在解码文本中模糊定位:
  * 在解码文本末尾 40% 内以较高相似度出现 -> 末词完整(尾音播出) => OK
  * 全文本中都找不到 -> 末词疑似缺失/未播出 => 关注
- 输出 classification + 抽样。
用法: python final_tail_check.py
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
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
CHUNK = 400000
_DIAC = {"ā": "a", "ī": "i", "ū": "u", "ṅ": "n", "ñ": "n", "ṇ": "n", "ṭ": "t",
         "ḍ": "d", "ḷ": "l", "ṃ": "m", "ḥ": "h", "ś": "s", "ṣ": "s", "ṛ": "r", "·": ""}


def norm(s):
    s = (s or "").lower()
    for k, v in _DIAC.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z]", "", s)
    return s


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def pcm_of(path):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def decode_text(x, sess, rev):
    if len(x) < 1600:
        return ""
    x = x - x.mean(); sd = x.std()
    if sd > 1e-5:
        x = x / sd
    ems = []
    for s in range(0, len(x), CHUNK):
        e = min(len(x), s + CHUNK)
        ems.append(sess.run(None, {"input_values": x[s:e].astype(np.float32).reshape(1, -1),
                                   "attention_mask": np.ones((1, e - s), dtype=np.int64)})[0][0])
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


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def main():
    done = json.load(open(os.path.join(AUDIO, "recut_done.json"), encoding="utf-8"))
    data = json.loads(load_js(os.path.join(APP, "data.js")))
    rules = data["rules"]
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    rows = []
    for d in done:
        idx = d["idx"]
        rule = rules[idx]
        wds = rule.get("words", [])
        lw = norm(wds[-1].get("p", "")) if wds else ""
        lw_suf = lw[-6:] if len(lw) > 6 else lw
        cp = os.path.join(APP, "audio/sent_new/%d.mp3" % idx)
        if not os.path.exists(cp):
            rows.append(dict(ch=d["ch"], idx=idx, st="缺文件", pali=rule.get("pali",""))); continue
        x = pcm_of(cp)
        dec = decode_text(x, sess, rev)
        if not dec:
            rows.append(dict(ch=d["ch"], idx=idx, st="空解码", pali=rule.get("pali",""))); continue
        # 末词后缀在解码末尾40%内定位
        tail40 = dec[int(len(dec) * 0.6):]
        head70 = dec[:int(len(dec) * 0.7)]
        r_tail = sim(lw_suf, tail40)
        r_any = sim(lw_suf, dec)
        if r_tail >= 0.55:
            st = "OK-末词在尾"
        elif r_any >= 0.55:
            st = "末词在但非尾(可能他处)"
        else:
            st = "末词疑似缺失"
        rows.append(dict(ch=d["ch"], idx=idx, st=st, lw=lw, lw_suf=lw_suf,
                         dec=dec, r_tail=round(r_tail, 2), pali=rule.get("pali","")))
    from collections import Counter
    stat = Counter(r["st"] for r in rows)
    print("== 修复句末词完整性终验 (自由CTC, %d句) ==" % len(rows))
    print("状态:", dict(stat))
    bad = [r for r in rows if r["st"] != "OK-末词在尾"]
    print("非OK(剩余关注): %d" % len(bad))
    for r in bad[:40]:
        print("  ch%d idx%4d [%s] 末词[%s] dec[...%s] r_tail=%.2f | %s" % (
            r["ch"], r["idx"], r["st"], r.get("lw",""), (r.get("dec","")[-30:] if r.get("dec") else "-"),
            r.get("r_tail",0), r["pali"][:30]))
    outp = os.path.join(AUDIO, "final_tail_check.txt")
    json.dump(rows, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("详情 ->", outp)


if __name__ == "__main__":
    main()
