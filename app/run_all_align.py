#!/usr/bin/env python3
"""全项目强制对齐：遍历 data.js 各章节，对每句做词级对齐。
- 凡 pali 以 'namo tassa' 开头的句子自动 ×3（多遍念诵，时间轴铺满整段，整段仍归该句）。
- 其余 ×1。
- 每章写 chN_bounds.json（句子级边界）+ chN_align_report.txt（逐词时间轴对照）。
- 模型只加载一次，逐章增量写文件。
"""
import sys, os, json, time
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
NAMO = "namo tassa"
CACHE_WAV = r"E:/WorkBuddy/.fa_cache/_real.wav"


def main():
    t0 = time.time()
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    mani = FA.load_js(os.path.join(APP, "audio", "manifest_audio.js"))
    data = FA.load_js(os.path.join(APP, "data.js"))
    sent = mani["sentences"]; rules = data["rules"]
    sections = data.get("sections", [])
    log = open(os.path.join(APP, "audio", "_run_all_align.log"), "w", encoding="utf-8")

    def say(m):
        print(m, flush=True); log.write(m + "\n"); log.flush()

    say("model loaded, sections=%d" % len(sections))
    for sec in sections:
        ch = sec.get("order", 0) + 1
        A = sec["ruleStart"]; B = sec["ruleEnd"]
        bounds = {}; align = {}; rep = []
        for idx in range(A, B + 1):
            k = str(idx)
            if k not in sent:
                rep.append("idx %d SKIP no-sentence" % idx); continue
            s = sent[k]
            if s.get("_tts") or not s.get("clip"):
                rep.append("idx %d SKIP tts/no-clip" % idx); continue
            words = rules[idx].get("words", [])
            if not words:
                rep.append("idx %d SKIP no-words" % idx); continue
            repN = 3 if rules[idx].get("pali", "").strip().lower().startswith(NAMO) else 1
            orig = rules[idx]["words"]
            if repN > 1:
                rules[idx]["words"] = orig * repN  # 对齐目标也×N（关键修复）
            try:
                wds, res, D, note = FA.align_sentence(idx, sent, rules, vocab, sess, FFMPEG, APP, CACHE_WAV)
            except Exception as e:
                rules[idx]["words"] = orig
                rep.append("idx %d ERR %s" % (idx, e)); continue
            rules[idx]["words"] = orig
            t0b = min(r[0] for r in res); t1b = max(r[1] for r in res)
            bnd = [round(t0b, 3), round(t1b, 3)]
            bounds[k] = bnd
            wlist = orig if repN == 1 else orig * repN
            # 结构化逐词时间轴（不截断 .p），忠实于音频含 ×repN 重复
            align.setdefault(ch, {})[k] = {
                "clip": s.get("clip"), "t0": bnd[0], "t1": bnd[1], "rep": repN,
                "words": [{"p": w.get("p", ""), "t0": round(r[0], 3), "t1": round(r[1], 3)} for w, r in zip(wlist, res)],
            }
            rep.append("idx %d D=%.3f bound=%s words=%d repeat=%d" % (idx, D, bnd, len(res), repN))
            for i, (w, r) in enumerate(zip(wlist, res)):
                rep.append("  %2d %-14s %.3f~%.3f" % (i, w.get("p") or "", r[0], r[1]))
        json.dump(bounds, open(os.path.join(APP, "audio", "ch%d_bounds.json" % ch), "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(align.get(ch, {}), open(os.path.join(APP, "audio", "ch%d_align.json" % ch), "w", encoding="utf-8"), ensure_ascii=False)
        open(os.path.join(APP, "audio", "ch%d_align_report.txt" % ch), "w", encoding="utf-8").write("\n".join(rep))
        say("chapter %d done: %d sentences (%.1fs)" % (ch, len(bounds), time.time() - t0))
    say("ALL DONE (%.1fs)" % (time.time() - t0))
    log.close()


if __name__ == "__main__":
    main()
