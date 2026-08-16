# -*- coding: utf-8 -*-
"""紧急补生成：被标记 TTS 的关键词 + 全量（后台会覆盖）。
"""
import asyncio, edge_tts, os, json, hashlib, subprocess

BASE = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
WDIR = os.path.join(BASE, "audio", "words", "words")
MF = os.path.join(BASE, "audio", "words", "manifest_pali_words.js")
TMP = r"C:/Users/dhamm/AppData/Local/Temp/PM_PALI_WORDS.json"
os.makedirs(WDIR, exist_ok=True)

# 用 Node 把 manifest 解析为 JSON（避免 JS 转义陷阱）
subprocess.run([r"C:/Users/dhamm/.workbuddy/binaries/node/versions/22.22.2/node.exe",
    os.path.join(BASE, "_extract_words.js"), MF, TMP], check=True)
M = json.load(open(TMP, encoding="utf-8"))

def h12(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]

# 紧急 17 个词（去括号）
EMERGENCY = [
    "pavāraṇāya", "pavāraṇākammassa", "dasa", "pavāraṇagge", "pavāraṇākammato",
    "pavāraṇā", "ajja", "pannarasī", "pavāraṇāsu", "pañca", "pan(a)",
    "pavāraṇā", "pavāraṇā", "pavāraṇā", "pavāraṇā", "pavāraṇā", "pavāraṇā",
]

async def gen(word):
    from aksharamukha import transliterate
    deva = transliterate.process("IAST", "Devanagari", word)
    fn = h12(word) + ".mp3"
    p = os.path.join(WDIR, fn)
    if os.path.exists(p) and os.path.getsize(p) > 1000: return fn
    c = edge_tts.Communicate(deva, "hi-IN-MadhurNeural")
    await c.save(p)
    return fn

async def main():
    added = 0
    for w in EMERGENCY:
        if w in M: continue  # 清单已有
        try:
            fn = await gen(w)
            M[w] = "words/" + fn
            added += 1
            print(f"  + {w} -> {fn}")
        except Exception as e:
            print(f"  FAIL {w}: {e}")
    out = "window.PM_PALI_WORDS = " + json.dumps(M, ensure_ascii=False) + ";\n"
    open(MF, "w", encoding="utf-8").write(out)
    print(f"新增 {added} 项，当前清单 {len(M)} 条")

asyncio.run(main())