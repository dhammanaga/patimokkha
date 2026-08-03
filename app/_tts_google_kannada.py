# -*- coding: utf-8 -*-
"""
_tts_google_kannada.py — 用 Google TTS (Kannada) 替换巴帝摩卡发音

替换范围（仅 TTS 部分，不碰真人录音）：
  ① 逐词发音：罗马巴利 → Kannada 字母(aksharamukha) → gTTS(lang='kn')
     覆盖 audio/words/<md5前12位>.mp3，更新 manifest_pali_words.js
     （键=罗马转写词 不变，故 pali-tts.js 无需改动）
  ② 整句 TTS 句：idx ∈ {4,14,1146,1173}（这 4 句无真人录音、原回退 Web Speech）
     生成 audio/sent_new/{idx}.mp3 并「新增」进 PM_AUDIO.sentences
     （只加这 4 个键，1171 条真人句原样保留）

说明：gTTS 是 Google Translate 免费 TTS，无 gender 参数，用的是 Google 默认
Kannada 语音（即此前 _test_google_tts.py 试听的那一版）。语速用 slow=False（原速），
与现有逐词 Edge 音频一致。

依赖（沙箱/受管 Python 已装）：gtts, aksharamukha, requests

用法：
  python _tts_google_kannada.py --mode sentences          # 仅 4 句整句
  python _tts_google_kannada.py --mode words --limit 30   # 先试 30 个逐词
  python _tts_google_kannada.py --mode words              # 全量逐词（约4767词）
  python _tts_google_kannada.py --mode all                # 全部
  python _tts_google_kannada.py --mode words --force      # 忽略已存在，全重生成
"""
import os, re, sys, json, hashlib, time, argparse
from aksharamukha.transliterate import process
from gtts import gTTS

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_JS = os.path.join(BASE, "data.js")
WORDS_DIR = os.path.join(BASE, "audio", "words")
MANIFEST_W = os.path.join(WORDS_DIR, "manifest_pali_words.js")
SENT_DIR = os.path.join(BASE, "audio", "sent_new")
MANIFEST_A = os.path.join(BASE, "audio", "manifest_audio.js")

TTS_IDX = [4, 14, 1146, 1173]
RETRY = 4
DELAY = 0.15          # 每句/词之间的间隔，降低被 Google 限流概率
PUNCT = ".,;:!?()[]{}‘’“”·•"

# ---------- 基础工具 ----------
def load_js(path, var):
    t = open(path, encoding="utf-8").read()
    m = re.search(re.escape(var) + r"\s*=\s*(\{.*\})\s*;?\s*$", t, re.S)
    if not m:
        raise SystemExit(f"无法在 {path} 中找到 {var}")
    return json.loads(m.group(1))

def to_kannada_word(w):
    w0 = w.strip(PUNCT)
    if not w0:
        return w
    try:
        return process("IAST", "Kannada", w0)
    except Exception:
        return w0

def to_kannada_phrase(text):
    # 去掉拉丁标点（括号/连字符等），避免混进 Kannada 文本干扰发音
    text = re.sub(r"[()\[\]{}.;:!?\-·•]", " ", text)
    return " ".join(to_kannada_word(t) for t in text.split())

def is_mp3(path):
    if not os.path.exists(path):
        return False
    sz = os.path.getsize(path)
    if sz < 800:
        return False
    head = open(path, "rb").read(2)
    return head[:2] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)

def gtts_save(text, out_mp3):
    """直接落地 gTTS 原文件（不做 ffmpeg 重编码）。带重试退避。"""
    last = None
    for a in range(1, RETRY + 1):
        try:
            gTTS(text=text, lang="kn", slow=False).save(out_mp3)
            if not is_mp3(out_mp3):
                raise RuntimeError(f"返回非 MP3(大小={os.path.getsize(out_mp3)}B)")
            return os.path.getsize(out_mp3)
        except Exception as e:
            last = e
            if a < RETRY:
                time.sleep(2 * a)       # 退避 2s,4s,6s...
    raise RuntimeError(f"重试 {RETRY} 次仍失败：{last}")

def mp3_duration(path):
    """解析首帧估算 CBR mp3 时长（秒）。gTTS 为 CBR，足够用于 t1。"""
    bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
    srates = {0: 44100, 1: 48000, 2: 32000}
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return 0.0
    n = len(data)
    i = 0
    while i + 4 <= n:
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            b = data[i + 2]
            br_idx = (b >> 4) & 0x0F
            sr_idx = (b >> 2) & 0x03
            pad = (b >> 1) & 1
            if 0 < br_idx < 15 and sr_idx != 3:
                br = bitrates[br_idx] * 1000
                sr = srates.get(sr_idx, 44100)
                frame = 144 * br // sr + pad
                if frame > 0:
                    frames = (n - i) // frame
                    return frames * 1152.0 / sr
        i += 1
    return 0.0

# ---------- 逐词 ----------
def extract_words():
    obj = load_js(DATA_JS, "window.PATIMOKKHA_DATA")
    out = {}
    for r in obj.get("rules", []):
        for w in (r.get("words") or []):
            p = (w.get("p") or "").strip()
            if p and not re.search(r"[‘’“”()]", p) and len(p) >= 2 and re.search(r"[a-zA-Z]", p):
                if p not in out:
                    out[p] = w.get("z", "")
    return out

def hash_name(word):
    return hashlib.md5(word.encode("utf-8")).hexdigest()[:12] + ".mp3"

def _merge_manifest_w(merged):
    if os.path.exists(MANIFEST_W):
        try:
            t = open(MANIFEST_W, encoding="utf-8").read()
            # 必须锚定行首，否则会误匹配文件头注释里的 "window.PM_PALI_WORDS = { ... }" 示例
            m = re.search(r"^window\.PM_PALI_WORDS\s*=\s*(\{.*\})\s*;", t, re.S | re.M)
            if m:
                old = json.loads(m.group(1))
                old.update(merged)
                return old
        except Exception:
            pass
    return merged

def gen_words(force, limit, newer_than=0.0, count=0):
    """newer_than: 若 mp3 的 mtime >= 该 epoch，视为本轮已生成过，跳过（断点续跑）。
       count: 本次最多真正合成多少个词（分块跑用），达到即停止合成，其余仍记入清单。"""
    words = extract_words()
    items = list(words.keys())
    if limit:
        items = items[:limit]
    os.makedirs(WORDS_DIR, exist_ok=True)
    manifest = {}
    ok = skip = fail = 0
    total = len(items)
    budget_left = count if count else None
    for i, w in enumerate(items, 1):
        fn = hash_name(w)
        path = os.path.join(WORDS_DIR, fn)
        exists = os.path.exists(path) and os.path.getsize(path) > 0
        done_already = exists and newer_than and os.path.getmtime(path) >= newer_than
        if exists and (done_already or not force):
            skip += 1
            manifest[w] = "words/" + fn
            if i % 100 == 0:
                print(f"  进度 {i}/{total} ok={ok} skip={skip} fail={fail}", flush=True)
            continue
        if budget_left is not None and budget_left <= 0:
            # 本块预算用尽：仍登记清单（文件已存在的旧版），留待下一块处理
            if exists:
                manifest[w] = "words/" + fn
            continue
        try:
            kan = to_kannada_word(w)
            gtts_save(kan, path)
            ok += 1
            manifest[w] = "words/" + fn
        except Exception as e:
            fail += 1
            print(f"  [{i}] FAIL {w!r}: {e}", flush=True)
            if exists:
                manifest[w] = "words/" + fn
        if budget_left is not None:
            budget_left -= 1
        if i % 50 == 0:
            print(f"  进度 {i}/{total} ok={ok} skip={skip} fail={fail}", flush=True)
        time.sleep(DELAY)

    merged = _merge_manifest_w(manifest)   # 始终合并旧清单，避免 --limit 预览时覆盖丢失
    header = (
        "/* 巴利「逐词」TTS 音频清单（由 _tts_google_kannada.py 生成）\n"
        " * window.PM_PALI_WORDS = { \"<罗马转写单词>\": \"words/<md5前12位>.mp3\", ... }\n"
        " * 发音引擎：罗马巴利 → Kannada 字母(aksharamukha) → Google TTS(kannada)。\n"
        " */\n"
    )
    tmp = MANIFEST_W + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("window.PM_PALI_WORDS = " + json.dumps(merged, ensure_ascii=False, indent=0) + ";\n")
    os.replace(tmp, MANIFEST_W)
    print(f"\n逐词完成：ok={ok} skip={skip} fail={fail}  清单共 {len(merged)} 条 -> {os.path.relpath(MANIFEST_W, BASE)}")

# ---------- 整句（仅 4 个 TTS 句） ----------
def gen_sentences(force):
    obj = load_js(DATA_JS, "window.PATIMOKKHA_DATA")
    rules = {r["idx"]: r for r in obj["rules"]}
    audio = load_js(MANIFEST_A, "window.PM_AUDIO")
    sent = audio.setdefault("sentences", {})
    os.makedirs(SENT_DIR, exist_ok=True)
    for idx in TTS_IDX:
        r = rules.get(idx)
        if not r:
            print(f"  [{idx}] 在 data.js 找不到，跳过")
            continue
        pali = r.get("pali", "")
        path = os.path.join(SENT_DIR, f"{idx}.mp3")
        if os.path.exists(path) and not force and os.path.getsize(path) > 0:
            print(f"  [{idx}] 已存在({os.path.getsize(path)}B)，跳过生成")
        else:
            kan = to_kannada_phrase(pali)
            gtts_save(kan, path)
            print(f"  [{idx}] 生成 ok ({os.path.getsize(path)}B)  kn={kan[:60]!r}")
        dur = round(mp3_duration(path), 3)
        # 只新增/更新这 4 个键，绝不改动其它真人句
        sent[str(idx)] = {
            "clip": f"audio/sent_new/{idx}.mp3",
            "t0": 0,
            "t1": dur,
            "rep": 1,
            "words": [],
        }
    # 写回（保留原包裹/其它顶层字段如 extras/key2idx）
    tmp = MANIFEST_A + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("/* 巴帝摩卡音频清单 */\nwindow.PM_AUDIO = "
                + json.dumps(audio, ensure_ascii=False, indent=0) + ";\n")
    os.replace(tmp, MANIFEST_A)
    print(f"\n整句完成：已新增/更新 PM_AUDIO.sentences 的 {len(TTS_IDX)} 个 TTS 键（真人句未改动）")

# ---------- 入口 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="all", choices=["words", "sentences", "all"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--newer-than", type=float, default=0.0,
                    help="epoch 秒；mtime 不早于该时刻的 mp3 视为本轮已生成，跳过（断点续跑）")
    ap.add_argument("--count", type=int, default=0,
                    help="本次最多真正合成多少个词（前台分块跑用）")
    args = ap.parse_args()
    if args.mode in ("sentences", "all"):
        print("== 整句 TTS 句（4/14/1146/1173）==")
        gen_sentences(args.force)
    if args.mode in ("words", "all"):
        print("\n== 逐词 ==", "(limit=%d)" % args.limit if args.limit else "")
        gen_words(args.force, args.limit, args.newer_than, args.count)

if __name__ == "__main__":
    main()
