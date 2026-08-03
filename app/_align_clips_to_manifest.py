#!/usr/bin/env python
"""对已存在的 clip mp3 做词级对齐, 生成 manifest 条目(不重切音频).
用法: python _align_clips_to_manifest.py [--apply] [idx...]
不给 idx 则自动处理"文件在磁盘但 manifest 无条目"的全部句子.
"""
import os, sys, re, json, time, subprocess
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
SENT = os.path.join(AUDIO, "sent_new")
MAN = os.path.join(AUDIO, "manifest_audio.js")
sys.path.insert(0, APP)
import src_align as SA
FA = SA.FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SR = 16000


def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.%s\s*=\s*" % var, "", s, count=1, flags=re.S)
    return json.loads(s.rstrip().rstrip(";"))


def clip_dur(p):
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", p,
                        "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return len(r.stdout) // 2 / SR


def main():
    apply = "--apply" in sys.argv
    ids = [int(a) for a in sys.argv[1:] if a.isdigit()]

    data = load_js(os.path.join(APP, "data.js"), "PATIMOKKHA_DATA")
    man = load_js(MAN, "PM_AUDIO")

    if not ids:
        disk = set()
        for f in os.listdir(SENT):
            m = re.match(r"^(\d+)\.mp3$", f)
            if m:
                disk.add(int(m.group(1)))
        ids = sorted(i for i in disk if str(i) not in man["sentences"] and i < len(data["rules"]))

    print("待处理 %d 句: %s" % (len(ids), ",".join(map(str, ids))))
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])

    records = {}
    for idx in ids:
        p = os.path.join(SENT, "%d.mp3" % idx)
        if not os.path.exists(p):
            print("  idx%-5d 缺文件, 跳过" % idx); continue
        dur = clip_dur(p)
        rule = data["rules"][idx]
        rw = rule.get("words") or []
        wlist = [w.get("p") or w.get("word") for w in rw if (w.get("p") or w.get("word"))]
        zlist = [w.get("z", "") for w in rw] if rw else []
        if not wlist:
            wlist = [w for w in re.split(r"\s+", rule.get("pali", "").strip()) if w]
            zlist = [""] * len(wlist)
        try:
            res = SA.align_window(sess, vocab, p, 0.0, dur, wlist)
        except Exception as e:
            print("  idx%-5d 对齐异常 %s" % (idx, e)); continue
        if not res:
            print("  idx%-5d 对齐失败" % idx); continue

        words = []
        for k, (w, rt0, rt1, g0, g1) in enumerate(res):
            t0 = max(0.0, min(rt0, dur))
            t1 = max(t0 + 0.05, min(rt1, dur))
            words.append({"p": w, "z": (zlist[k] if k < len(zlist) else ""),
                          "t0": round(t0, 3), "t1": round(t1, 3)})
        # 单调化 + 首词从 0 起、末词覆盖到结尾
        for k in range(1, len(words)):
            if words[k]["t0"] < words[k - 1]["t1"]:
                words[k]["t0"] = words[k - 1]["t1"]
            if words[k]["t1"] <= words[k]["t0"]:
                words[k]["t1"] = round(min(dur, words[k]["t0"] + 0.08), 3)
        if words:
            words[0]["t0"] = 0.0
            words[-1]["t1"] = round(dur, 3)

        records[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0,
                             "t1": round(dur, 3), "words": words, "rep": 1}
        print("  idx%-5d dur=%5.2fs 词数%-3d  %s" % (idx, dur, len(words), rule["pali"][:48]))

    print("\n生成 %d 条记录" % len(records))
    if not apply:
        print("(演练模式, 加 --apply 写入)")
        return

    for k, rec in records.items():
        man["sentences"][k] = rec
    # key2idx 同步
    k2 = man.get("key2idx") or {}
    for k in records:
        key = data["rules"][int(k)].get("key")
        if key and key not in k2:
            k2[key] = int(k)
    man["key2idx"] = k2

    ts = time.strftime("%Y%m%d_%H%M%S")
    import shutil
    shutil.copyfile(MAN, MAN + ".bak_fill_" + ts)
    open(MAN, "w", encoding="utf-8").write(
        "/* 巴帝摩卡音频清单 */\nwindow.PM_AUDIO = %s;\n" % json.dumps(man, ensure_ascii=False))
    print("已写入 manifest, 备份: %s" % (MAN + ".bak_fill_" + ts))


if __name__ == "__main__":
    main()
