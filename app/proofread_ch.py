#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动校对 chN_align.json 生成的切片(技术正确性):
- 文件存在且非过小(无声/空切)
- 单句时长合理(>0.4s 且 <30s)
- 词数 = orig词数 * rep
- 无坏词(t1<t0)、无词时超界(t0<0 或 t1>dur)
- 截断近似: 首词 t0 不大(开头无大静音)、末词 t1 接近 dur(结尾完整)
输出 ch_proofread_report.txt 并打印 PASS/FAIL。
"""
import sys, os, json, argparse
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", nargs="+", type=int, required=True)
    args = ap.parse_args()
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    sections = data["sections"]
    # 加载 manifest 判断 TTS 兜底(无真人录音的句子不算 FAIL)
    mf = FA.load_js(os.path.join(AUDIO, "manifest_audio.js")) if os.path.exists(os.path.join(AUDIO, "manifest_audio.js")) else {}
    msent = mf.get("sentences", {})
    total_pass = 0
    total_fail = 0
    report_lines = []
    for ch in args.chapters:
        sec = sections[ch - 1]
        A, B = sec["ruleStart"], sec["ruleEnd"]
        fp = os.path.join(AUDIO, "ch%d_align.json" % ch)
        if not os.path.exists(fp):
            report_lines.append("===== 第%d章 idx %d-%d : 缺 %s =====" % (ch, A, B, os.path.basename(fp)))
            total_fail += (B - A + 1)
            continue
        al = json.load(open(fp, encoding="utf-8"))
        report_lines.append("===== 第%d章 idx %d-%d =====" % (ch, A, B))
        fails = 0
        for idx in range(A, B + 1):
            k = str(idx)
            rec = al.get(k)
            problems = []
            if rec is None:
                me = msent.get(k, {})
                if not me or not me.get("clip"):
                    total_pass += 1
                    report_lines.append("idx %d: PASS (TTS兜底, 无真人录音)" % idx)
                    continue
                problems.append("缺 rec"); fails += 1
                report_lines.append("idx %d: FAIL 缺 rec" % idx); continue
            clip = rec.get("clip", "")
            fpath = os.path.join(APP, clip) if clip else ""
            if not fpath or not os.path.exists(fpath):
                problems.append("缺文件 %s" % clip)
            elif os.path.getsize(fpath) < 500:
                problems.append("文件过小 %d字节" % os.path.getsize(fpath))
            dur = rec.get("t1", 0)
            if dur is None or dur < 0.4:
                problems.append("时长过短 %.2f" % dur)
            if dur and dur > 30:
                problems.append("时长过长 %.2f" % dur)
            orig = rules[idx].get("words", [])
            olen = len(orig)
            rep = rec.get("rep", 1)
            aw = rec.get("words", [])
            if olen * rep != len(aw):
                problems.append("词数不符 orig*rep=%d got=%d" % (olen * rep, len(aw)))
            bad = 0; oob = 0; shortw = 0
            for w in aw:
                t0 = w.get("t0", 0); t1 = w.get("t1", 0)
                if t1 is not None and t0 is not None and t1 < t0: bad += 1
                if dur and (t0 < 0 or t1 > dur + 0.01): oob += 1
                # 每词时长下限: 词数对但时间被压缩到物理不可能的型错误(如末词0.05s/w)原校对漏检
                if dur and t1 is not None and t0 is not None and (t1 - t0) < 0.10: shortw += 1
            if bad: problems.append("%d坏词(t1<t0)" % bad)
            if oob: problems.append("%d超界词" % oob)
            if shortw: problems.append("%d过短词(<0.10s,可能压缩)" % shortw)
            if aw:
                # 中点边界法在句间静音中点切, 每句带前导/尾随静音属正常; 仅当异常大(>2s)才警告
                if aw[0].get("t0", 0) > 2.0:
                    problems.append("开头留白过大 %.2f" % aw[0].get("t0"))
                if dur and aw[-1].get("t1", 0) < dur - 2.0:
                    problems.append("结尾可能截断 末词t1=%.2f dur=%.2f" % (aw[-1].get("t1"), dur))
            if problems:
                fails += 1
                report_lines.append("idx %2d: FAIL %s" % (idx, "; ".join(problems)))
            else:
                total_pass += 1
        report_lines.append("第%d章: PASS=%d FAIL=%d" % (ch, (B - A + 1) - fails, fails))
        total_fail += fails
    report_lines.append("")
    report_lines.append("总计: PASS=%d FAIL=%d" % (total_pass, total_fail))
    txt = "\n".join(report_lines)
    outp = os.path.join(AUDIO, "ch_proofread_report.txt")
    open(outp, "w", encoding="utf-8").write(txt)
    print(txt)
    print("报告已写 ->", outp)


if __name__ == "__main__":
    main()
