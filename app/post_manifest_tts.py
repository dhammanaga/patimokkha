#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并后处理: 把 manifest 中无真人录音的句子(第二章 70-79 等)从 sentences 移除,
并重建 key2idx(仅含"有真实 clip"的句子, 首次出现的 key 优先), 使 🔊 按钮回退 TTS。"""
import sys, os, json, shutil, time
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
MANIFEST = os.path.join(AUDIO, "manifest_audio.js")
TTS_IDX = list(range(70, 80)) + [1209]  # 第二章 70-79(序诵录音无此内容) + 结语 1209(录音未念此标题)


def main():
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(AUDIO, "manifest_audio.js.bak_tts_%s" % ts)
    shutil.copy(MANIFEST, bak)
    obj = FA.load_js(MANIFEST)
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    # 1) 移除 TTS 句的 manifest 条目
    for idx in TTS_IDX:
        obj["sentences"].pop(str(idx), None)
        print("manifest sentences[%d] 已移除 -> TTS 兜底" % idx, flush=True)
    # 2) 重建 key2idx: 仅"有 clip"的句子; key 首次出现优先(重复文本保留最早 idx, 如结语句)
    k2i = {}
    for idx, r in enumerate(rules):
        e = obj["sentences"].get(str(idx))
        if e and e.get("clip"):
            key = r.get("key") or r.get("pali") or ""
            key = key.strip()
            if key and key not in k2i:
                k2i[key] = idx
    obj["key2idx"] = k2i
    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write("window.PM_AUDIO = ")
        json.dump(obj, f, ensure_ascii=False)
        f.write(";")
    print("key2idx 重建完成: %d 条" % len(k2i))
    print("备份: %s" % bak)


if __name__ == "__main__":
    main()
