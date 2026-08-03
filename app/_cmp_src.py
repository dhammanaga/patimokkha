import sys, os, subprocess, wave, contextlib
FFMPEG = "C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
files = [
 "C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/9. Sekhiya Dhamma.mp3",
 "C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/9. Sekhiya Dhamma.mp3",
 "C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/10. Satta Adhikarana Samatha Dhamma.mp3",
 "C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/10. Satta Adhikarana Samatha Dhamma.mp3",
]
tmp = os.path.join(os.getcwd(), "_tmp_probe.wav")
for f in files:
    if not os.path.exists(f):
        print("MISSING", f); continue
    sz = os.path.getsize(f)
    p = subprocess.run([FFMPEG,"-hide_banner","-loglevel","error","-y","-i",f,"-ac","1","-ar","8000",tmp],
                       capture_output=True)
    dur = 0
    if os.path.exists(tmp):
        with contextlib.closing(wave.open(tmp,'rb')) as w:
            dur = w.getnframes()/w.getframerate()
    print("%-95s  %9d bytes  %8.2f s" % (f.split("巴帝摩卡诵/")[-1], sz, dur))
