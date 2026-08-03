#!/usr/bin/env python
"""重建 manifest 的 key2idx: {data.rules[idx].key: idx} 对有真人clip的句子, 首次出现优先。
修复"重编号后 key2idx 缺失/错位导致整句播放回退TTS"(app.js playRecSentence(REC.key2idx[key])).
"""
import re, json, os, time
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")

def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.%s\s*=\s*" % var, "", s, count=1, flags=re.S)
    return json.loads(s.rstrip().rstrip(";"))

def main():
    man = load_js(os.path.join(AUDIO, "manifest_audio.js"), "PM_AUDIO")
    d = load_js(os.path.join(APP, "data.js"), "PATIMOKKHA_DATA")
    k2i = {}
    miss_key = []
    used = 0
    for k in sorted(man["sentences"].keys(), key=lambda x: int(x)):
        idx = int(k)
        rec = man["sentences"][k]
        if not rec.get("clip"):
            continue
        rule = d["rules"][idx]
        key = rule.get("key")
        if not key:
            miss_key.append(idx)
            continue
        if key in k2i:
            continue  # 重复 key, 首次(最小idx)优先
        k2i[key] = idx
        used += 1
    man["key2idx"] = k2i
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.system('cp "%s" "%s.bak_k2i_%s" 2>nul' % (os.path.join(AUDIO, "manifest_audio.js"),
                                                  os.path.join(AUDIO, "manifest_audio.js"), ts))
    open(os.path.join(AUDIO, "manifest_audio.js"), "w", encoding="utf-8").write(
        "/* 巴帝摩卡音频 */\nwindow.PM_AUDIO = %s;\n" % json.dumps(man, ensure_ascii=False))
    print("重建 key2idx: %d 条(有clip句). 无key句:%s" % (used, miss_key[:10]))

if __name__ == "__main__":
    main()
