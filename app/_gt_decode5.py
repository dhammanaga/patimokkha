#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地面真相: 对 5 句 + 各自下一句自由 CTC 解码, 看实际念出内容边界。
模型只加载一次。"""
import sys, os
APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import decode_clip as DC

CAND = [(939,940),(941,942),(954,955),(957,958),(1089,1090)]

def main():
    for a,b in CAND:
        for i in (a,b):
            p = os.path.join(APP, "audio", "sent_new", "%d.mp3" % i)
            if not os.path.exists(p):
                print("=== %d 文件缺失 ===" % i); continue
            dur, txt = DC.clip_decode(p)
            print("=== clip %d (时长%.2fs) 实读:\n%s" % (i, dur, txt))
            print()
    print("DONE")

if __name__ == "__main__":
    main()
