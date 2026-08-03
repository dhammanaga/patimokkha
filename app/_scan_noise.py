import os, sys, subprocess, wave, contextlib, struct
FFMPEG = "C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
D = "audio/sent_new"
tmp = os.path.join(os.getcwd(), "_tmp_scan.wav")
bad = []
files = sorted([f for f in os.listdir(D) if f.endswith(".mp3")], key=lambda x:int(x[:-4]))
for f in files:
    p = os.path.join(D, f)
    if os.path.getsize(p) > 40000:   # >~1.8s 的先跳过, 只查短的
        continue
    subprocess.run([FFMPEG,"-hide_banner","-loglevel","error","-y","-i",p,"-ac","1","-ar","16000",tmp],capture_output=True)
    if not os.path.exists(tmp): continue
    with contextlib.closing(wave.open(tmp,'rb')) as w:
        sr=w.getframerate(); n=w.getnframes(); raw=w.readframes(n)
    if n == 0: continue
    d = struct.unpack("<%dh"%(len(raw)//2), raw)
    dur = n/sr
    pk = max(abs(v) for v in d)/32768.0
    W = int(sr*0.02); voiced = 0
    for i in range(0, len(d)-W, W):
        if max(abs(v) for v in d[i:i+W])/32768.0 > 0.04: voiced += 1
    vr = voiced*0.02
    if pk < 0.10 or vr < 0.30:
        bad.append((f, dur, pk, vr))
        print("可疑 %-10s 时长%5.2fs 峰值%.4f 有声%.2fs" % (f, dur, pk, vr))
print("---- 共 %d 条可疑 ----" % len(bad))
