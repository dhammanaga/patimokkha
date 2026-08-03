#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量：对指定 idx 的 mp3 自由解码, 输出"实读字母串" vs "data期望文本", 供比对。
用法: python dec_batch.py 1141,1143,...  或  python dec_batch.py all(1141-1176)
"""
import sys, os, json
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import forced_align as FA
import numpy as np

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SR = FA.SR
CHUNK = 400000
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
DATA_REF = os.path.join(APP, "_data_ref.json")

def decode_str(path):
    x, sr = FA.decode_real(path, FFMPEG, APP, os.path.join(APP, "audio", "_tmp_clip.wav"))
    dur = len(x)/float(sr)
    xw = x.copy(); xw = xw - xw.mean()
    sd = xw.std()
    if sd > 1e-5: xw = xw / sd
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    ems=[]
    for s in range(0, len(xw), CHUNK):
        e=min(len(xw), s+CHUNK)
        xx=xw[s:e].astype(np.float32).reshape(1,e-s)
        mask=np.ones((1,e-s),dtype=np.int64)
        out=sess.run(None,{"input_values":xx,"attention_mask":mask})[0][0]
        ems.append(out)
    em=np.concatenate(ems,axis=0)
    mx=em.max(axis=1,keepdims=True); z=em-mx; np.exp(z,out=z); z=z/z.sum(axis=1,keepdims=True)
    idx=z.argmax(axis=1)
    chars=[]; prev=-1
    for t in range(len(idx)):
        c=int(idx[t])
        if c<=2: prev=-1; continue
        if c==prev: continue
        chars.append(rev[c]); prev=c
    return dur, "".join(chars)

def load_data_map(data_js):
    return json.load(open(data_js, encoding="utf-8"))

def norm_rough(s):
    # 诵念形变映射用于粗比对打分: 清音→浊音 等
    import unicodedata
    t=s.lower()
    t=t.replace("p","b").replace("t","d").replace("k","g").replace("c","j")
    t=t.replace("ph","b").replace("th","d").replace("kh","g").replace("ch","j")
    t=t.replace("d','d").replace("h","")
    t=t.replace("ṅ","ng").replace("ñ","ny")
    return t

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv)>1 else "all"
    if arg=="all":
        idxs=list(range(1141,1177))
    else:
        idxs=[int(x) for x in arg.split(",")]
    data_map = load_data_map(DATA_REF)
    results=[]
    for i in idxs:
        clip=os.path.join(APP,"audio","sent_new","%d.mp3"%i)
        if not os.path.exists(clip):
            results.append((i,None,"NO_MP3","-","-"))
            continue
        if str(i) not in data_map:
            results.append((i,None,"NO_DATA","-","-"))
            continue
        dur, dec = decode_str(clip)
        exp = data_map[str(i)]["pali"]
        results.append((i,dur,dec,exp,data_map[str(i)]["meaning"]))
    for i,dur,dec,exp,mean in results:
        print("### idx=%d%s" % (i, (" dur=%.2f"%dur) if dur else ""))
        print(" 期望: %s" % exp)
        print(" 实读: %s" % dec)
        print(" 释义: %s" % mean)
    print("\n共 %d 句" % len(results))
