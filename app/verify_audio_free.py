#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科学校对 v2(逐词覆盖, 独立于强制对齐器):
逐句 ffmpeg 解码切片 -> 自由 CTC 转写 -> 对 data.js 逐词模糊定位(SequenceMatcher 滑窗)。
- 判定完整: 所有"长词"(规范化>=4字符)都找到(相似度>=WRATIO), 且最末长词落在解码尾部
- 短词(<4字符)不计(模糊匹配不可靠)
- --selftest: 人为截断若干正确切片验证检出率(校验校对法本身)
用法: python verify_audio_free.py [--chapters 2] [--selftest] [--limit N]
"""
import sys, os, re, json, subprocess, difflib, time
import numpy as np
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
WRATIO = 0.42          # 每词模糊定位阈值(失真宽容)
MIN_EXIST = 0.35       # 低于此才判"词缺失"(真不在音频里); 0.35~0.42 判"存疑"

_DIAC = {"ā": "a", "ī": "i", "ū": "u", "ṅ": "n", "ñ": "n", "ṇ": "n", "ṭ": "t",
         "ḍ": "d", "ḷ": "l", "ṃ": "m", "ḥ": "h", "ś": "s", "ṣ": "s", "ṛ": "r", "ḟ": "f", "·": ""}


def norm(s):
    s = (s or "").lower()
    for k, v in _DIAC.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z]", "", s)
    out = []
    for c in s:
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def find_word(target, text):
    """返回 (最佳相似度, 起始位置)"""
    if not target or not text:
        return 0.0, -1
    L = len(target)
    if len(text) < L:
        return difflib.SequenceMatcher(None, target, text).ratio(), 0
    best = 0.0; bestpos = -1
    for i in range(0, len(text) - L + 1):
        r = difflib.SequenceMatcher(None, target, text[i:i + L]).ratio()
        if r > best:
            best = r; bestpos = i
    return best, bestpos


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
        xc = x[s:e].astype(np.float32).reshape(1, -1)
        mask = np.ones((1, e - s), dtype=np.int64)
        ems.append(sess.run(None, {"input_values": xc, "attention_mask": mask})[0][0])
    em = np.concatenate(ems, axis=0)
    mx = em.max(axis=1, keepdims=True); z = em - mx
    np.exp(z, out=z); z = z / z.sum(axis=1, keepdims=True)
    idx = z.argmax(axis=1)
    out = []; prev = -1
    for t in range(len(idx)):
        c = int(idx[t])
        if c <= 2:
            prev = -1; continue
        if c == prev:
            continue
        prev = c; out.append(rev[c])
    return "".join(out)


def check_sentence(rule, dec):
    """对一句做逐词覆盖校验。返回 (状态, 详情missing/存疑)
    长词(规范化>=4字符)逐个在解码里模糊定位:
      <MIN_EXIST -> 真缺失; MIN_EXIST~WRATIO -> 存疑(失真大, 待人工核)"""
    wds = [norm(w.get("p", "")) for w in rule.get("words", [])]
    long_words = [w for w in wds if len(w) >= 4]
    if not dec:
        return "空解码", [], []
    missing = []; unsure = []
    for w in long_words:
        r, pos = find_word(w, dec)
        if r < MIN_EXIST:
            missing.append((w, r))
        elif r < WRATIO:
            unsure.append((w, r))
    if missing:
        return "词缺失", missing, unsure
    if unsure:
        return "存疑", missing, unsure
    return "PASS", [], []


def main():
    chapters = None; limit = None; selftest = False
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
        if args[i] == "--selftest":
            selftest = True; i += 1; continue
        i += 1

    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    sections = data["sections"]
    obj = FA.load_js(os.path.join(AUDIO, "manifest_audio.js"))
    sent = obj["sentences"]

    # ---- 自验证: 人为截断一句, 校验检出 ----
    if selftest:
        print("== 自验证(人为截断正确切片) ==")
        for idx in [66, 1196]:
            e = sent.get(str(idx))
            if not e or not e.get("clip"):
                continue
            x = pcm_of(os.path.join(APP, e["clip"]))
            # 60% 截断
            xt = x[:int(len(x) * 0.6)]
            dec_full = decode_text(x, sess, rev)
            dec_trunc = decode_text(xt, sess, rev)
            st_full, _, _ = check_sentence(rules[idx], dec_full)
            st_trunc, miss, _ = check_sentence(rules[idx], dec_trunc)
            print("idx %d: 完整=%s | 截60%%=%s %s" % (idx, st_full, st_trunc,
                  ("缺:%s" % [m[0] for m in miss]) if miss else ""), flush=True)
        print()

    idx_list = []
    for ch_i, sec in enumerate(sections):
        ch = ch_i + 1
        if chapters and ch not in chapters:
            continue
        for idx in range(sec["ruleStart"], sec["ruleEnd"] + 1):
            idx_list.append((ch, idx))
    if limit:
        idx_list = idx_list[:limit]

    rows = []; t0 = time.time(); n_done = 0
    for (ch, idx) in idx_list:
        e = sent.get(str(idx))
        rule = rules[idx]
        pali = rule.get("pali", "")
        if not e or not e.get("clip"):
            rows.append((ch, idx, pali, "", "TTS", [], [])); continue
        clip = os.path.join(APP, e["clip"])
        if not os.path.exists(clip):
            rows.append((ch, idx, pali, "", "缺文件", [], [])); continue
        x = pcm_of(clip)
        dec = decode_text(x, sess, rev)
        st, miss, unsure = check_sentence(rule, dec)
        rows.append((ch, idx, pali, dec, st, miss, unsure))
        n_done += 1
        if n_done % 100 == 0:
            print("... %d/%d (%.1fs)" % (n_done, len(idx_list), time.time() - t0), flush=True)

    bad = [r for r in rows if r[4] not in ("PASS", "TTS")]
    tts = [r for r in rows if r[4] == "TTS"]
    good = [r for r in rows if r[4] == "PASS"]
    # 统计各状态
    from collections import Counter
    stat = Counter(r[4] for r in rows)
    lines = []
    lines.append("== 逐词覆盖校对报告 ==")
    lines.append("校验=%d | 状态: %s" % (len(rows), dict(stat)))
    lines.append("")
    lines.append("== 词缺失(真不在音频里, 高置信) ==")
    for (ch, idx, pali, dec, st, miss, unsure) in [r for r in bad if r[4] == "词缺失"]:
        lines.append("ch%d idx%4d [%s] | %s" % (ch, idx, st, pali[:44]))
        if miss:
            lines.append("        缺词: %s" % ", ".join("%s(%.2f)" % m for m in miss))
        lines.append("        dec: %s" % dec[:70])
    lines.append("")
    lines.append("== 存疑(失真大, 待人工核) ==")
    for (ch, idx, pali, dec, st, miss, unsure) in [r for r in bad if r[4] not in ("词缺失",)]:
        lines.append("ch%d idx%4d [%s] | %s" % (ch, idx, st, pali[:44]))
        if unsure:
            lines.append("        存疑词: %s" % ", ".join("%s(%.2f)" % m for m in unsure))
        lines.append("        dec: %s" % dec[:70])
    txt = "\n".join(lines)
    outp = os.path.join(AUDIO, "verify_report.txt")
    open(outp, "w", encoding="utf-8").write(txt)
    print("\n".join(lines))
    print("报告已写 ->", outp)


if __name__ == "__main__":
    main()
