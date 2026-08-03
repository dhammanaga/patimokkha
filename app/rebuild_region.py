#!/usr/bin/env python
"""重建公式区: 对指定(ch, idx, 搜索窗口)逐句在源里精确定位+词级对齐, 重切 & 更新 manifest.
用法: python rebuild_region.py  (运行内置的 TARGETS 区域)
"""
import subprocess, os, sys, json, re, time

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
sys.path.insert(0, APP)
import src_align as SA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
LEAD = 0.15   # 开头往前延伸(含上句尾音一点)
TAIL = 0.40   # 末尾额外余量(保证本句完整)

# 重建目标: (ch, idx列表, 每句搜索窗口(w0,w1))  —— 窗口基于源能量/内容先验
# ch2 公式区
CH2 = {
    64: (135.5, 141.0), 65: (139.5, 145.5), 66: (145.0, 151.0),
    67: (150.0, 154.5), 68: (154.0, 158.5), 69: (158.5, 165.0),
}
# ch3 公式区(新编号 111-116)
CH3 = {
    111: (215.0, 223.0), 112: (222.0, 228.0), 113: (227.0, 233.0),
    114: (231.0, 237.0), 115: (235.0, 241.0), 116: (239.0, 246.0),
}
# ch4 公式区(新编号 320-325) —— 窗口基于细分解码(ch4源: 688-693 Tatthā, 693-697 dutiyampi, 697-701 tatiyampi, 701-705 parisuddhettha, 705-708 tasmā, 708-711 Saṅgha)
CH4 = {
    320: (686.0, 694.0), 321: (691.0, 697.5), 322: (696.0, 701.5),
    323: (700.5, 706.0), 324: (704.0, 708.5), 325: (707.5, 711.0),
}

def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.%s\s*=\s*" % var, "", s, count=1, flags=re.S)
    return json.loads(s.rstrip().rstrip(";"))

def write_js(path, var, obj, note=""):
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.system('cp "%s" "%s.bak_%s" 2>nul' % (path, path, ts))
    open(path, "w", encoding="utf-8").write("%s\nwindow.%s = %s;\n" % (note, var, json.dumps(obj, ensure_ascii=False)))

def main():
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = SA.FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = load_js(os.path.join(APP, "data.js"), "PATIMOKKHA_DATA")
    man = load_js(os.path.join(AUDIO, "manifest_audio.js"), "PM_AUDIO")

    targets_all = {"ch2": (2, CH2), "ch3": (3, CH3), "ch4": (4, CH4)}
    # 可选 --ch 过滤
    only = None
    if "--ch" in sys.argv:
        only = sys.argv[sys.argv.index("--ch") + 1]
    targets = {k: v for k, v in targets_all.items() if only is None or k == only}
    records = {}
    for label, (ch, mapping) in targets.items():
        for idx in sorted(mapping):
            w0, w1 = mapping[idx]
            rule = data["rules"][idx]
            wlist = [w.get("p") or w.get("word") for w in rule.get("words", []) if w.get("p")]
            if not wlist:
                wlist = [w for w in re.split(r"\s+", rule.get("pali", "").strip())]
            res = SA.align_window(sess, vocab, SA._CH_SRC[ch], w0, w1, wlist)
            if not res:
                print("  idx%d 对齐失败" % idx); continue
            g0 = res[0][3]; g1 = res[-1][4]
            start = max(0.0, g0 - LEAD)
            end = g1 + TAIL
            dur = end - start
            if dur < 0.3:
                end = start + 0.3; dur = 0.3
            # 重切
            out = os.path.join(AUDIO, "sent_new", "%d.mp3" % idx)
            subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % start, "-to", "%.3f" % end,
                            "-i", SA._CH_SRC[ch], "-c", "copy", out],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # 词时(相对新clip起点)
            words = []
            prev = 0.0
            for w, rt0, rt1, wg0, wg1 in res:
                t0 = max(0.0, wg0 - start); t1 = min(dur, wg1 - start)
                if t1 <= t0:
                    t1 = min(dur, t0 + 0.08)
                words.append({"p": w, "z": "", "t0": round(t0, 3), "t1": round(t1, 3)})
                prev = t1
            # 末词 t1 覆盖到 dur(保证尾音完整)
            if words:
                words[-1]["t1"] = round(dur, 3)
            records[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0.0,
                                 "t1": round(dur, 3), "rep": 1, "words": words}
            print("  ch%d idx%d 源[%.2f,%.2f] clip[%.2f,%.2f] dur=%.2f 词数%d" % (
                ch, idx, g0, g1, start, end, dur, len(words)))

    # 合并回 manifest
    if records:
        for k, rec in records.items():
            man["sentences"][str(int(k))] = rec
        # 备份
        ts = time.strftime("%Y%m%d_%H%M%S")
        os.system('cp "%s" "%s.bak_region_%s" 2>nul' % (os.path.join(AUDIO, "manifest_audio.js"),
                                                        os.path.join(AUDIO, "manifest_audio.js"), ts))
        write_js(os.path.join(AUDIO, "manifest_audio.js"), "PM_AUDIO", man, "/* 巴帝摩卡音频 */")
        print("已合并 %d 句到 manifest" % len(records))

if __name__ == "__main__":
    main()
