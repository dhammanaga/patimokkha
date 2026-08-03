import os, sys, subprocess, wave, contextlib
sys.path.insert(0, os.getcwd())
import importlib.util
spec = importlib.util.spec_from_file_location("FA", os.path.join(os.getcwd(), "dec_src.py"))
FFMPEG = "C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
BASE = "C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/"
files = ["3. Parajikuddes.mp3","4. Sanghadisesuddeso.mp3","5. Aniyatuddeso.mp3",
         "6. Timsa Nissaggiya Pacittiya Dhamma.mp3","7. Dvenavuti Pacittiya Dhamma.mp3",
         "8. Cattaro Patidesaniya Dhamm.mp3","9. Sekhiya Dhamma.mp3",
         "10. Satta Adhikarana Samatha Dhamma.mp3"]
tmp = os.path.join(os.getcwd(), "_tmp_end.wav")
import struct
for f in files:
    p = BASE + f
    subprocess.run([FFMPEG,"-hide_banner","-loglevel","error","-y","-i",p,"-ac","1","-ar","16000",tmp],capture_output=True)
    with contextlib.closing(wave.open(tmp,'rb')) as w:
        sr=w.getframerate(); n=w.getnframes(); raw=w.readframes(n)
    d = struct.unpack("<%dh"%(len(raw)//2), raw)
    dur = n/sr
    W = int(sr*0.02)
    # 找最后一个有声 20ms 窗
    last_voiced = 0.0
    for i in range(0, len(d)-W, W):
        seg=d[i:i+W]
        pk=max(abs(v) for v in seg)
        if pk/32768.0 > 0.04:
            last_voiced = i/sr + 0.02
    print("%-46s 时长 %8.2fs  末尾人声 %8.2fs  尾部静音 %6.2fs" % (f[:44], dur, last_voiced, dur-last_voiced))
