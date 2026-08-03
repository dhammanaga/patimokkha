#!/usr/bin/env python
"""基于 seq_align 整段对齐结果重建公式区: 对每句重切 & 更新 manifest.
用法: python rebuild_seq_region.py --ch ch2  (或 ch3/ch4)
"""
import os, sys, json, re, subprocess, time

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
sys.path.insert(0, APP)
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import seq_align as SEQ

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"

REGIONS = {
    "ch2": dict(ch=2, idxs=[63,64,65,66,67,68,69], w0=133.0, w1=166.0, rebuild=[64,65,66,67,68,69]),
    "ch3": dict(ch=3, idxs=[110,111,112,113,114,115,116], w0=215.0, w1=246.0, rebuild=[111,112,113,114,115,116]),
    "ch4": dict(ch=4, idxs=[319,320,321,322,323,324,325], w0=686.0, w1=711.0, rebuild=[320,321,322,323,324,325]),
}
LEAD = 0.35   # 首词前延伸
TAIL = 0.50   # 末词后余量

def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.%s\s*=\s*" % var, "", s, count=1, flags=re.S)
    return json.loads(s.rstrip().rstrip(";"))

def write_js(path, var, obj, note=""):
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.system('cp "%s" "%s.bak_%s" 2>nul' % (path, path, ts))
    open(path, "w", encoding="utf-8").write("%s\nwindow.%s = %s;\n" % (note, var, json.dumps(obj, ensure_ascii=False)))

def main():
    which = sys.argv[sys.argv.index("--ch") + 1] if "--ch" in sys.argv else "ch2"
    cfg = REGIONS[which]
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = SEQ.FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = load_js(os.path.join(APP, "data.js"), "PATIMOKKHA_DATA")
    man = load_js(os.path.join(AUDIO, "manifest_audio.js"), "PM_AUDIO")

    all_words = []; word_sent = []
    for idx in cfg["idxs"]:
        rule = data["rules"][idx]
        wl = [w.get("p") or w.get("word") for w in rule.get("words", []) if w.get("p")]
        if not wl:
            wl = [w for w in re.split(r"\s+", rule.get("pali", "").strip()) if w]
        s_i = len(all_words)
        all_words.extend(wl)
        word_sent += [idx] * len(wl)
    wt = SEQ.align_seq(sess, vocab, SEQ._CH_SRC[cfg["ch"]], cfg["w0"], cfg["w1"], all_words, None)

    records = {}
    for idx in cfg["rebuild"]:
        w_ids = [i for i, s_i in enumerate(word_sent) if s_i == idx]
        if not w_ids:
            print("%d 无词" % idx); continue
        ws, we = w_ids[0], w_ids[-1] + 1
        sg = wt[ws:we]
        g0 = sg[0][0]; g1 = sg[-1][1]
        start = max(0.0, g0 - LEAD)
        end = g1 + TAIL
        dur = end - start
        out = os.path.join(AUDIO, "sent_new", "%d.mp3" % idx)
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % start, "-to", "%.3f" % end,
                        "-i", SEQ._CH_SRC[cfg["ch"]], "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        words = []
        prev = 0.0
        for w, (a, b) in zip(all_words[ws:we], sg):
            t0 = max(0.0, a - start); t1 = min(dur, b - start)
            if t1 <= t0:
                t1 = min(dur, t0 + 0.06)
            words.append({"p": w, "z": "", "t0": round(t0, 3), "t1": round(t1, 3)})
            prev = t1
        if words:
            words[-1]["t1"] = round(dur, 3)  # 末词覆盖到底
        records[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0.0,
                             "t1": round(dur, 3), "rep": 1, "words": words}
        print("  idx%d 源[%.2f,%.2f] clip[%.2f,%.2f] dur=%.2f 词%d" % (idx, g0, g1, start, end, dur, len(words)))

    if records:
        for k, rec in records.items():
            man["sentences"][str(int(k))] = rec
        ts = time.strftime("%Y%m%d_%H%M%S")
        os.system('cp "%s" "%s.bak_seq_%s" 2>nul' % (os.path.join(AUDIO, "manifest_audio.js"),
                                                     os.path.join(AUDIO, "manifest_audio.js"), ts))
        write_js(os.path.join(AUDIO, "manifest_audio.js"), "PM_AUDIO", man, "/* 巴帝摩卡音频 */")
        print("已合并 %d 句" % len(records))

if __name__ == "__main__":
    main()
