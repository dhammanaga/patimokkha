#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二章真实修复(根因: 今天的 v4 重做把正确的 sent_new/64-69 覆写坏了):
1) 从 v4 重做前的备份 sent_new_bak_before_complete_20260731_201508 恢复 64-69.mp3(内容经自由解码验证正确);
2) 用 bak_align(原始 manifest)的 64-69 词时重建 ch2_align.json;
3) 70-79(序诵录音里没有, 录音止于 Nidānuddeso paṭhamo)从 ch2_align.json 移除 -> 合并后走 TTS 兜底。
随后: python merge_align_to_manifest.py && python post_manifest_tts.py && python proofread_ch.py --chapters 2
"""
import sys, os, json, shutil, time
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
SENT_NEW = os.path.join(AUDIO, "sent_new")
BAK_SRC = os.path.join(AUDIO, "sent_new_bak_before_complete_20260731_201508")
BAK_ALIGN = os.path.join(AUDIO, "manifest_audio.js.bak_align")
RESTORE = [64, 65, 66, 67, 68, 69]
TTS_IDX = range(70, 80)


def main():
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak1 = os.path.join(AUDIO, "ch2_align.json.bak_truth_%s" % ts)
    shutil.copy(os.path.join(AUDIO, "ch2_align.json"), bak1)
    bak2 = os.path.join(AUDIO, "sent_new_bak_truth_%s" % ts)
    if os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW)):
        shutil.copytree(SENT_NEW, bak2)
        print("备份 sent_new ->", bak2, flush=True)

    # 1) 恢复音频
    for idx in RESTORE:
        src = os.path.join(BAK_SRC, "%d.mp3" % idx)
        if not os.path.exists(src):
            print("!! 备份缺 %d.mp3" % idx); continue
        shutil.copy(src, os.path.join(SENT_NEW, "%d.mp3" % idx))
        print("恢复 sent_new/%d.mp3 (%d bytes)" % (idx, os.path.getsize(src)), flush=True)

    # 2) 重建 ch2_align.json 64-69 (词时来自原始 manifest)
    al = json.load(open(os.path.join(AUDIO, "ch2_align.json"), encoding="utf-8"))
    bakobj = FA.load_js(BAK_ALIGN)
    sents = bakobj["sentences"]
    for idx in RESTORE:
        e = sents.get(str(idx))
        if not e:
            print("!! bak_align 缺 idx %d" % idx); continue
        t1 = e.get("t1", 0)
        wds = [{"p": w.get("p", ""), "t0": w.get("t0", 0), "t1": w.get("t1", 0)} for w in e.get("words", [])]
        al[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0, "t1": t1, "rep": 1, "words": wds}
        print("ch2_align.json[%d] <- t1=%.3f nwords=%d (原始词时)" % (idx, t1, len(wds)), flush=True)

    # 3) 移除 70-79 -> TTS
    for idx in TTS_IDX:
        al.pop(str(idx), None)
        print("ch2_align.json[%d] 移除 -> 合并后走 TTS 兜底" % idx, flush=True)

    json.dump(al, open(os.path.join(AUDIO, "ch2_align.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("ch2_align.json 已写回 (36-69, 70-79 TTS)")
    print("备份: %s" % bak1)
    print("\n接着运行:")
    print("  python merge_align_to_manifest.py")
    print("  python post_manifest_tts.py")
    print("  python proofread_ch.py --chapters 2")


if __name__ == "__main__":
    main()
