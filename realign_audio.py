#!/usr/bin/env python
# 离线逐词时间轴重对齐（不依赖任何 ML 模型 / HF 下载）
# 方法：每句 clip 已按句正确切分；在 clip 内用「音节数加权切分 + 真实停顿谷吸附」重新求每词 [t0,t1]。
#   - 唱诵节奏近似恒定 → 按每词元音音节数在整句时长内比例切分（文字轴约束）
#   - 再把算出的边界吸附到音频中检测到的真实静音谷（若有，≤0.35s 内）
# 仅重写「退化句」（零宽词 / 首词吞整段 / 整体被压短），保留词文本与音频不动。
# 用法：python realign_audio.py [section_order]   # section_order 默认 3 = 第四章(Saṅghādisesa)
import subprocess, re, json, os, wave, sys, shutil
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
FF = r"C:\Users\dhamm\AppData\Roaming\kingsoft\wps\addons\pool\win-i386\kaudio_3.1.0.9646\ffmpeg.exe"
DATA = os.path.join(BASE, "app", "data.js")
MANI = os.path.join(BASE, "app", "audio", "manifest_audio.js")
TMPW = os.path.join(BASE, "_realign_tmp.wav")

def load_js_span(path):
    t = open(path, encoding="utf-8").read()
    i = t.index("{"); depth = 0
    for j in range(i, len(t)):
        if t[j] == "{": depth += 1
        elif t[j] == "}":
            depth -= 1
            if depth == 0: return json.loads(t[i:j+1]), i, j+1
    raise RuntimeError("no json end")

data, _, _ = load_js_span(DATA)
mani, m0, m1 = load_js_span(MANI)
rules = data["rules"]; sent = mani["sentences"]
_orig_text = open(MANI, encoding="utf-8").read()

def decode(clip):
    p = os.path.join(BASE, "app", clip)
    if not os.path.exists(p): return None, 0
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", p,
                    "-ar", "16000", "-ac", "1", "-f", "wav", TMPW], check=True)
    w = wave.open(TMPW, "rb"); sr = w.getframerate(); n = w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)/32768.0
    return x, sr

def syllables(w): return max(1, len(re.findall(r'[aāiīuūeēoō]', w)))

def energy_env(x, sr):
    fl = int(0.025*sr); hop = int(0.010*sr)
    nframes = 1+(len(x)-fl)//hop
    rms = np.array([np.sqrt(np.mean(x[f*hop:f*hop+fl]**2)+1e-12) for f in range(nframes)])
    times = np.arange(nframes)*hop/sr
    rms = rms/(rms.max()+1e-9)
    if len(rms) > 7: rms = np.convolve(rms, np.ones(7)/7, mode="same")
    return times, rms

def valleys(times, rms):
    silent = rms < 0.18; vs = []; i = 0; n = len(silent)
    while i < n:
        if silent[i]:
            j = i
            while j < n and silent[j]: j += 1
            if (times[j-1]-times[i]) >= 0.08: vs.append((times[i]+times[j-1])/2)
            i = j
        else: i += 1
    merged = []
    for b in sorted(vs):
        if merged and (b-merged[-1]) < 0.10: continue
        merged.append(b)
    return merged

def new_spans(words, x, sr):
    D = len(x)/sr; K = len(words)
    if K == 1: return [(0.0, D)]
    times, rms = energy_env(x, sr); vs = valleys(times, rms)
    syll = [syllables(w) for w in words]; tot = sum(syll)
    raw = []; acc = 0.0
    for s in syll[:-1]:
        acc += s/tot*D; raw.append(acc)
    chosen = []
    for b in raw:
        best=None; bd=1e9
        for v in vs:
            d=abs(v-b)
            if d<bd: bd=d; best=v
        chosen.append(best if (best is not None and bd<=0.35) else b)
    out=[]; prev=0.0
    for c in chosen:
        c=max(prev+0.02, min(c, D-0.02)); out.append(c); prev=c
    bnd=[0.0]+out+[D]
    return [(bnd[i], bnd[i+1]) for i in range(K)]

def is_degenerate(words, D):
    K=len(words)
    if K<2: return False
    for w in words:
        if (w["t1"]-w["t0"]) < 0.03: return True
    if (words[0]["t1"]-words[0]["t0"]) > 0.7*D: return True
    span = words[-1]["t1"]-words[0]["t0"]
    if span > 0 and span < 0.5*D: return True
    return False

sec_order = int(sys.argv[1]) if len(sys.argv)>1 else 3
sec = next(s for s in data["sections"] if s.get("order")==sec_order)
a, b = sec["ruleStart"], sec["ruleEnd"]
rewritten=[]; skipped=[]; errs=[]
for idx in range(a, b+1):
    e = sent.get(str(idx))
    if not e or not e.get("clip") or not e.get("words"): skipped.append(idx); continue
    mw = e["words"]
    try: x, sr = decode(e["clip"])
    except Exception as ex: errs.append((idx,str(ex))); continue
    if x is None: skipped.append(idx); continue
    D = len(x)/sr
    if not is_degenerate(mw, D): continue
    words = [w.get("p","") for w in mw]
    spans = new_spans(words, x, sr)
    for w,(t0,t1) in zip(mw, spans):
        w["t0"]=round(float(t0),3); w["t1"]=round(float(t1),3)
    rewritten.append(idx)

BAK = MANI + f".bak_sec{sec_order}"
if os.path.exists(BAK): os.remove(BAK)
shutil.copy2(MANI, BAK)
rebuilt = _orig_text[:m0] + json.dumps(mani, ensure_ascii=False) + _orig_text[m1:]
with open(MANI, "w", encoding="utf-8") as f: f.write(rebuilt)
print(f"章节 order={sec_order} 范围 idx {a}..{b}")
print(f"重写退化句数: {len(rewritten)} -> {rewritten}")
print(f"跳过: {skipped}  错误: {errs}")
print(f"备份: {BAK}")
