#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 final_fixset.json(需修复句全集) 统一计算安全 new_end:
把每句末尾延伸到「old_end 之后下一个完整静音段的中点」, 从而:
  - 完整恢复被切尾音(静音段起点>0.18s 无语音 => 已包含全部语音)
  - new_end 落在静音中段 => 修复后 headroom≈静音宽/2>=0.09s, 不再紧贴
  - new_end < G0next(下句首词) => 绝不串句
对找不到完整静音(连诵极紧)的, 保持 old_end 不强改。
输出 final_fixset_newend.json(统一 new_end)。
"""
import os, json, re
import numpy as np

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
VOICE_TH = 0.012
WIN = 0.010
MIN_SIL = 0.18
LOOKAHEAD = 1.2
FILL_RATIO = 0.5


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def rms_env(x, sr=16000, win=0.010):
    w = int(sr * win); n = len(x) // w
    if n < 2:
        return np.array([0.0])
    return np.sqrt((x[:n*w].reshape(n, w) ** 2).mean(1))


def silence_segment(env, dt, t0, min_sil=MIN_SIL, look=LOOKAHEAD):
    """返回 t0 后第一个完整静音段 (起点, 终点)。找不到返回 None"""
    f0 = int(t0 // dt); silent = 0.0; seg_start = None
    limit = min(len(env), f0 + int(look // dt))
    for f in range(f0, limit):
        e = float(env[f])
        if e > VOICE_TH:
            if silent >= min_sil and seg_start is not None:
                return seg_start, f * dt
            silent = 0.0; seg_start = None
        else:
            if seg_start is None:
                seg_start = f * dt
            silent += dt
    if silent >= min_sil and seg_start is not None:
        return seg_start, limit * dt
    return None


def main():
    data = json.loads(load_js(os.path.join(APP, "data.js")))
    sections = data["sections"]
    final = json.load(open(os.path.join(AUDIO, "final_fixset.json"), encoding="utf-8"))
    env_cache = {}
    out = []
    for f in final:
        ch, idx = f["ch"], f["idx"]
        if ch not in env_cache:
            wav = os.path.join(AUDIO, "ch%d_complete.wav" % ch)
            x = np.frombuffer(open(wav, "rb").read(), dtype=np.int16).astype(np.float32) / 32768.0
            env_cache[ch] = rms_env(x)
        env = env_cache[ch]; dt = WIN
        rawp = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
        raw = json.load(open(rawp, encoding="utf-8"))
        bounds = {int(k): tuple(v) for k, v in raw["bounds"].items()}
        idxs = sorted(bounds); D = raw.get("D", 0.0)
        p_i = idxs.index(idx)
        _, g1 = bounds[idx]
        G0next = bounds[idxs[p_i + 1]][0] if p_i < len(idxs) - 1 else D
        old_end = (g1 + G0next) / 2.0
        seg = silence_segment(env, dt, old_end)
        if seg is None:
            new_end = old_end; safe = False
        else:
            s0, s1 = seg
            # 关键修正: 不用 G0next 做硬 cap!
            # 静音段终点=下一句真正语音起点, 静音段内任意点都安全(<下句首词)。
            # 之前的 min(静音中点, G0next-0.05) 因 G0next(aligner估)被低估, 会把
            # new_end 拉到静音起点之前 -> 尾巴仍被切。现直接取静音段中点。
            new_end = s0 + (s1 - s0) * FILL_RATIO
            safe = new_end > old_end + 0.05
        out.append(dict(ch=ch, idx=idx, old_end=round(old_end, 3),
                        new_end=round(new_end, 3), safe=safe,
                        sil=(round(seg[0], 3), round(seg[1], 3)) if seg else None))
    n_change = sum(1 for o in out if o["new_end"] > o["old_end"] + 0.05)
    from collections import Counter
    print("final_fixset:%d | 将扩展:%d | 保持:%d" % (
        len(out), n_change, len(out) - n_change))
    print("分章(扩展):", Counter(o["ch"] for o in out if o["new_end"] > o["old_end"] + 0.05))
    json.dump(out, open(os.path.join(AUDIO, "final_fixset_newend.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("final_fixset_newend.json 已重算(静音中段法)")
    for o in out[:8]:
        print("  ch%d idx%d old=%s new=%s sil=%s %s" % (
            o["ch"], o["idx"], o["old_end"], o["new_end"], o["sil"], "EXT" if o["safe"] else "keep"))


if __name__ == "__main__":
    main()
