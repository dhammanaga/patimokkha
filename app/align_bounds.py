#!/usr/bin/env python3
"""生成每句边界(chN_bounds.json) + 逐词时间轴对照报告，复用 pali-forced-align 算法。
以 data.js 的 words 为对齐真相源（绕过 manifest 细粒度 words 的 count mismatch）。
支持按句指定重复遍数 --repeat-map '{"0":3}'：多遍念诵句用 文本×N 对齐，时间轴铺满整段，
且整段仍归该句（句子边界 = 整个 clip）。
"""
import sys, os, json, argparse
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", type=int, required=True)
    ap.add_argument("--range", nargs=2, type=int, required=True)
    ap.add_argument("--repeat-map", type=str, default="{}",
                    help='JSON, 例 \'{"0":3}\' 指定某些 idx 的重复遍数')
    a = ap.parse_args()
    A, B = a.range
    rmap = json.loads(a.repeat_map)
    mani = FA.load_js(os.path.join(APP, "audio", "manifest_audio.js"))
    data = FA.load_js(os.path.join(APP, "data.js"))
    sent = mani["sentences"]; rules = data["rules"]
    # 用 data.js 的 words 替换临时 manifest 的 words（绕过 count mismatch），并按遍数重复
    for idx in range(A, B + 1):
        k = str(idx)
        if k in sent and rules[idx].get("words"):
            words = rules[idx]["words"]
            rep = int(rmap.get(k, 1) or 1)
            if rep > 1:
                words = words * rep  # 多遍念诵: 文本 ×N
            sent[k]["words"] = words
    tmp = os.path.join(APP, "audio", "_align_tmp.js")
    out = os.path.join(APP, "audio", "_align_out.js")
    FA._write(mani, tmp)
    sys.argv = ["fa", "--model", MODEL, "--vocab", VOCAB,
                "--manifest", tmp, "--data", os.path.join(APP, "data.js"),
                "--ffmpeg", FFMPEG, "--app-root", APP,
                "--range", str(A), str(B), "--out", out]
    FA.main()
    out_m = FA.load_js(out)
    bounds = {}; rep_lines = []
    for idx in range(A, B + 1):
        k = str(idx)
        if k not in out_m["sentences"]:
            rep_lines.append(f"idx {idx} SKIP (no clip/align)"); continue
        w = out_m["sentences"][k].get("words", [])
        if not w:
            rep_lines.append(f"idx {idx} no words"); continue
        t0 = min(x.get("t0", 0) for x in w); t1 = max(x.get("t1", 0) for x in w)
        bounds[k] = [round(t0, 3), round(t1, 3)]
        D = out_m["sentences"][k].get("t1")
        repn = int(rmap.get(k, 1) or 1)
        rep_lines.append(f"idx {idx} D={D}s bound=[{bounds[k][0]},{bounds[k][1]}] words={len(w)} repeat={repn}")
        for i, x in enumerate(w):
            rep_lines.append(f"  {i:2d} {(x.get('p') or ''):14s} {x.get('t0')}~{x.get('t1')}")
    json.dump(bounds, open(os.path.join(APP, "audio", f"ch{a.ch}_bounds.json"), "w", encoding="utf-8"), ensure_ascii=False)
    open(os.path.join(APP, "audio", f"ch{a.ch}_align_report.txt"), "w", encoding="utf-8").write("\n".join(rep_lines))
    for f in (tmp, tmp + ".bak_align"):
        try: os.remove(f)
        except Exception: pass
    print("DONE -> ch%d_bounds.json (%d sentences, repeatMap=%s)" % (a.ch, len(bounds), a.repeat_map))


if __name__ == "__main__":
    main()
