#!/usr/bin/env python3
"""把强制对齐结果(chN_align.json)合并回 manifest_audio.js：
- 用对齐得到的逐词 t0/t1 覆盖每个句子的 words（修复 1045 条 t1<t0 的坏数据）。
- 句子边界 t0/t1 取对齐结果（≈ 整段 clip）。
- ×N 重复句(如 Namo ×3)：words 保持 N× 倍、按 i%olen 取回中文 z，便于逐遍高亮。
- 有对齐数据的句子去掉 _tts 标记（已有真人音频）。
- 无对齐数据(如 ch11 结语、个别 tts)保持原样。
- 写盘前自动备份 manifest_audio.js。
"""
import sys, os, re, json, shutil, time
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")


def main():
    obj = FA.load_js(os.path.join(AUDIO, "manifest_audio.js"))
    sent = obj["sentences"]
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    sections = data.get("sections", [])

    applied = 0
    skipped_missing = 0
    fixed_bad = 0
    total_words = 0
    for sec in sections:
        ch = sec["order"] + 1
        fp = os.path.join(AUDIO, "ch%d_align.json" % ch)
        if not os.path.exists(fp):
            print("SKIP ch%d: 无 ch%d_align.json" % (ch, ch))
            continue
        al = json.load(open(fp, encoding="utf-8"))
        for k, rec in al.items():
            idx = int(k)
            if idx < 0 or idx >= len(rules):
                skipped_missing += 1
                continue
            orig = rules[idx].get("words", [])
            olen = len(orig)
            rep = rec.get("rep", 1)
            aw = rec.get("words", [])
            newwords = []
            for i, w in enumerate(aw):
                oi = (i % olen) if rep > 1 else i
                z = orig[oi].get("z", "") if (oi < olen) else ""
                newwords.append({"p": w.get("p", ""), "z": z,
                                 "t0": w.get("t0", 0), "t1": w.get("t1", 0)})
            e = sent.get(k, {})
            if e.get("_tts") and rec.get("clip"):
                e.pop("_tts", None)  # 现在已有真人音频
            # 统计坏数据修复
            old = sent.get(k, {}).get("words", [])
            for ow in old:
                if ow.get("t0") is not None and ow.get("t1") is not None and ow["t1"] < ow["t0"]:
                    fixed_bad += 1
                    break
            e["clip"] = rec.get("clip")
            e["t0"] = rec.get("t0", 0)
            e["t1"] = rec.get("t1", 0)
            e["rep"] = rep
            e["words"] = newwords
            sent[k] = e
            applied += 1
            total_words += len(newwords)

    # 备份 + 写盘
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(AUDIO, "manifest_audio.js.bak_align_%s" % ts)
    shutil.copy(os.path.join(AUDIO, "manifest_audio.js"), bak)
    with open(os.path.join(AUDIO, "manifest_audio.js"), "w", encoding="utf-8") as f:
        f.write("window.PM_AUDIO = ")
        json.dump(obj, f, ensure_ascii=False)
        f.write(";")
    print("合并完成: applied=%d 句, words=%d, 修复坏t1<t0句=%d, 跳过=%d" % (applied, total_words, fixed_bad, skipped_missing))
    print("备份: %s" % bak)

    # 写盘后自检
    bad = 0
    no_clip = 0
    for k, e in sent.items():
        ws = e.get("words", [])
        if not e.get("clip") and not e.get("_tts"):
            no_clip += 1
        for w in ws:
            if w.get("t0") is not None and w.get("t1") is not None and w["t1"] < w["t0"]:
                bad += 1
    print("自检: 写盘后坏t1<t0词数=%d, 无clip且无tts句=%d" % (bad, no_clip))


if __name__ == "__main__":
    main()
