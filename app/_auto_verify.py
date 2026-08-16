# -*- coding: utf-8 -*-
"""自动校验：331 个切错词中，哪些对齐值真的对（TTS 标准音 vs 真人区间内容匹配）
策略：解码 TTS mp3（标准发音）→ 解码真人对齐区间 → 编辑距离相似度（容忍诵念变音）
输出：通过词（对齐值 OK，直接确认）+ 待调词（内容不匹配，需重切）
"""
import json, os, re, sys
import numpy as np
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import forced_align as FA

FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
ROOT = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵"
SR = FA.SR
MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
CHUNK = 400000

def load_js(path, var):
    src = open(path, encoding="utf-8").read()
    return json.loads(re.search(re.escape(var) + r"\s*=\s*(\{.*?\});?\s*$", src, re.S).group(1))

NEW = load_js(os.path.join(APP, "audio", "manifest_audio.js"), "window.PM_AUDIO")["sentences"]
DATA = load_js(os.path.join(APP, "data.js"), "window.PATIMOKKHA_DATA")
WORDS = load_js(os.path.join(APP, "audio", "words", "manifest_pali_words.js"), "window.PM_PALI_WORDS")
TTS_SET = set(["4", "14", "1146", "1173"])

vocab = json.load(open(VOCAB, encoding="utf-8"))
rev = {v: k for k, v in vocab.items()}
sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
cache_wav = {}

def decode_wav(x, t0, t1):
    f0, f1 = int(t0*SR), min(int(t1*SR), len(x))
    xw = x[f0:f1].copy()
    if len(xw) < 800:
        return ""
    xw = xw - xw.mean(); sd = xw.std()
    if sd > 1e-5: xw = xw / sd
    ems = []
    for s0 in range(0, len(xw), CHUNK):
        e = min(len(xw), s0+CHUNK)
        xx = xw[s0:e].astype(np.float32).reshape(1, e-s0)
        mask = np.ones((1, e-s0), dtype=np.int64)
        out = sess.run(None, {"input_values": xx, "attention_mask": mask})[0][0]
        ems.append(out)
    em = np.concatenate(ems, 0)
    ids = em.argmax(1)
    out, prev = [], None
    for i in ids:
        if i == 0: prev = None; continue
        if i == prev: continue
        prev = i
        out.append(rev.get(int(i), "?"))
    return "".join(out)

def decode_file(path, t0, t1):
    x, _ = FA.decode_real(path, FFMPEG, APP, os.path.join(APP, "audio", "_tmp_auto.wav"))
    return decode_wav(x, t0, t1)

def norm(s):
    # 去 diacritics + 归一（不替换变音，保留原字符用于编辑距离）
    m = {"ā": "a", "ī": "i", "ū": "u", "ṃ": "m", "ṅ": "n", "ñ": "n", "ṇ": "n",
         "ṭ": "t", "ḍ": "d", "ś": "s", "ṣ": "s", "ṛ": "r", "ṝ": "r", "ḷ": "l", "ḹ": "l",
         "Ā": "a", "Ī": "i", "Ū": "u", "Ṁ": "m", "Ṅ": "n", "Ñ": "n", "Ṇ": "n",
         "Ṭ": "t", "Ḍ": "d", "Ś": "s", "Ṣ": "s", "Ṛ": "r", "Ḷ": "l"}
    return "".join(m.get(c, c) for c in s)

def ed(a, b):
    # 编辑距离（Levenshtein）
    la, lb = len(a), len(b)
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]; dp[0] = i
        for j in range(1, lb + 1):
            tmp = dp[j]
            dp[j] = min(dp[j] + 1, dp[j-1] + 1, prev + (0 if a[i-1] == b[j-1] else 1))
            prev = tmp
    return dp[lb]

# 收集 331 个切错词（非 TTS 句）
rows = []
for k in range(len(DATA["rules"])):
    if str(k) in TTS_SET: continue
    n = NEW.get(str(k))
    if not n: continue
    r = DATA["rules"][k]
    for wi, w in enumerate(r.get("words") or []):
        nw = n["words"][wi] if wi < len(n["words"]) else None
        if not nw or nw.get("t0") is None: continue
        # 用备份旧值算差异（对齐修正过才加入）
        rows.append((k, wi, w["p"], w.get("z", ""), nw["t0"], nw["t1"]))

# 只处理"真的被对齐修正过"的词：旧 manifest 值不同
OLD = load_js(os.path.join(APP, "audio", "manifest_audio.js.bak_2202"), "window.PM_AUDIO")["sentences"]
rows2 = []
for k, wi, p, z, n0, n1 in rows:
    o = OLD.get(str(k))
    if not o: continue
    ow = o["words"][wi] if wi < len(o["words"]) else None
    if not ow or ow.get("t0") is None: continue
    if abs(n0 - ow["t0"]) > 0.35 or abs(n1 - ow["t1"]) > 0.35:
        rows2.append((k, wi, p, z, n0, n1, ow["t0"], ow["t1"]))

print("待校验词:", len(rows2))
passed, retune = [], []
cache_clip = {}
for i, (k, wi, p, z, n0, n1, o0, o1) in enumerate(rows2, 1):
    # TTS 标准发音文本
    key = p.replace("(", "").replace(")", "").strip()
    tts_txt = ""
    if key in WORDS:
        try:
            tts_txt = decode_file(os.path.join(APP, "audio", "words", WORDS[key].replace("words/", "")), 0, 10)
        except Exception:
            tts_txt = ""
    # 真人对齐区间文本
    m = NEW.get(str(k))
    clip = m["clip"]
    if clip not in cache_clip:
        cache_clip[clip] = FA.decode_real(os.path.join(APP, clip), FFMPEG, APP, os.path.join(APP, "audio", "_tmp_auto2.wav"))[0]
    real_txt = decode_wav(cache_clip[clip], n0, n1)
    # 归一 + 编辑距离相似度
    tts_n = norm(tts_txt); real_n = norm(real_txt)
    if not tts_n or not real_n:
        sim = 0
    else:
        d = ed(tts_n, real_n)
        sim = 1 - d / max(len(tts_n), len(real_n))
    thr = 0.45 if len(norm(p.replace("(", "").replace(")", ""))) >= 5 else 0.30
    rec = "通过" if sim >= thr else "待调"
    if rec == "通过": passed.append((k, wi, p, sim))
    else: retune.append((k, wi, p, z, sim, tts_txt, real_txt, n0, n1, o0, o1))
    if i % 50 == 0:
        print("进度 %d/%d 通过=%d 待调=%d" % (i, len(rows2), len(passed), len(retune)), flush=True)

print("\n=== 结果：通过 %d | 待调 %d ===" % (len(passed), len(retune)))
print("\n-- 待调词（对齐值内容与 TTS 不匹配，需重切）--")
for x in retune:
    print("  句#%d [%s] TTS『%s』 真人『%s』 相似%.2f 新[%.2f,%.2f] 旧[%.2f,%.2f]" % (
        x[0]+1, x[2], x[5][:20], x[6][:20], x[4], x[7], x[8], x[9], x[10]))

json.dump({"passed": passed, "retune": [[x[0], x[1], x[2], x[3]] for x in retune]},
          open(os.path.join(ROOT, "自动校验结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n结果已存 自动校验结果.json")
