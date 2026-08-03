import sys, os, subprocess, wave, contextlib, struct
FFMPEG = "C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
src = sys.argv[1]; t0 = float(sys.argv[2]); t1 = float(sys.argv[3])
tmp = os.path.join(os.getcwd(), "_tmp_tail.wav")
subprocess.run([FFMPEG,"-hide_banner","-loglevel","error","-y","-ss",str(t0),"-to",str(t1),
                "-i",src,"-ac","1","-ar","16000",tmp], capture_output=True)
with contextlib.closing(wave.open(tmp,'rb')) as w:
    sr = w.getframerate(); n = w.getnframes()
    raw = w.readframes(n)
d = struct.unpack("<%dh" % (len(raw)//2), raw)
W = int(sr*0.02)  # 20ms
print("区间 %.2f-%.2f  采样率 %d  帧数 %d" % (t0,t1,sr,n))
print("每 20ms 的 RMS / 峰值 (归一化到 32768):")
peak_all = max(abs(v) for v in d) or 1
for i in range(0, len(d)-W, W):
    seg = d[i:i+W]
    pk = max(abs(v) for v in seg)
    rms = (sum(v*v for v in seg)/len(seg)) ** 0.5
    t = t0 + i/sr
    bar = "#" * int(pk/peak_all*50)
    print("  %7.3f  pk=%6d (%.4f)  rms=%7.1f  %s" % (t, pk, pk/32768.0, rms, bar))
