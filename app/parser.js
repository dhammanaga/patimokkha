/*
 * parser.js — 巴帝摩卡逐词对照 HTML 解析器
 * 同时可在 Node (build) 与浏览器 (重新导入) 中运行，逻辑完全一致。
 * 解析结果结构：
 *   {
 *     meta:   { source, hash, generatedAt, ruleCount, sectionCount },
 *     sections: [ { id, title, order, ruleStart, ruleEnd } ],
 *     rules:    [ { idx, secOrder, pali, words:[{p,z}], meaning, note, key } ]
 *   }
 * idx = 全局顺序下标（0 起），用于「按次序背诵全文」。
 * key = 巴利整句归一化哈希，用于源文件改动后按内容保留学习进度。
 */
(function (global) {
  'use strict';

  function stripTags(s) {
    if (s == null) return '';
    return String(s)
      .replace(/<[^>]*>/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#0?39;|&apos;/g, "'")
      .replace(/\s+/g, ' ')
      .trim();
  }

  function normalizePali(s) {
    return String(s)
      .toLowerCase()
      .replace(/[’”"'`]/g, '')
      .replace(/[.,;:!?]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // 找到从 openStart（<div class="rule"> 起始）对应的结束 </div> 下标
  function findRuleEnd(html, afterOpen) {
    let depth = 1;
    let i = afterOpen;
    const n = html.length;
    while (i < n) {
      if (html.startsWith('<div', i)) {
        depth++;
        i = html.indexOf('>', i) + 1;
      } else if (html.startsWith('</div>', i)) {
        depth--;
        i += 6;
        if (depth === 0) return i; // 指向结束 </div> 之后
      } else {
        i++;
      }
    }
    return n;
  }

  function parsePatimokkha(html, sourceName) {
    sourceName = sourceName || '巴帝摩卡_逐词对照.html';
    const rules = [];
    const sections = [];

    // 1) 采集章节标题位置
    const secRe = /<h2 class="sec" id="(sec\d+)">([\s\S]*?)<\/h2>/g;
    let m;
    const secMarks = [];
    while ((m = secRe.exec(html)) !== null) {
      secMarks.push({
        pos: m.index,
        id: m[1],
        title: stripTags(m[2]),
      });
    }

    // 2) 逐规则扫描
    const ruleOpen = '<div class="rule">';
    let pos = html.indexOf(ruleOpen);
    let idx = 0;
    while (pos !== -1) {
      const afterOpen = pos + ruleOpen.length;
      const end = findRuleEnd(html, afterOpen);
      const block = html.slice(pos, end);

      // 归属章节：取 pos 之前最近的 secMark
      let secOrder = 0;
      for (let k = 0; k < secMarks.length; k++) {
        if (secMarks[k].pos < pos) secOrder = k;
        else break;
      }

      // 巴利逐词 & 汉译
      const pRe = /<span class="p">([\s\S]*?)<\/span>/g;
      const zRe = /<span class="z[^"]*">([\s\S]*?)<\/span>/g;
      const palis = [];
      const zhs = [];
      let mm;
      while ((mm = pRe.exec(block)) !== null) palis.push(stripTags(mm[1]));
      while ((mm = zRe.exec(block)) !== null) zhs.push(stripTags(mm[1]));

      const words = [];
      const len = Math.max(palis.length, zhs.length);
      for (let w = 0; w < len; w++) {
        words.push({ p: palis[w] || '', z: zhs[w] || '' });
      }

      // 参考译文（去掉「参考译文：」前缀）
      const refRe = /<div class="ref">([\s\S]*?)<\/div>/g;
      let refText = '';
      while ((mm = refRe.exec(block)) !== null) {
        refText += (refText ? ' ' : '') + stripTags(mm[1]);
      }
      refText = refText.replace(/^参考译文\s*[:：]\s*/, '').trim();
      // 注释（如 x3）
      const noteRe = /<div class="note">([\s\S]*?)<\/div>/g;
      let noteText = '';
      while ((mm = noteRe.exec(block)) !== null) {
        noteText += (noteText ? ' ' : '') + stripTags(mm[1]);
      }

      const pali = palis.join(' ');
      rules.push({
        idx: idx,
        secOrder: secOrder,
        pali: pali,
        words: words,
        meaning: refText,
        note: noteText,
        key: normalizePali(pali),
      });
      idx++;
      pos = html.indexOf(ruleOpen, end);
    }

    // 3) 章节统计（首末规则下标）
    for (let k = 0; k < secMarks.length; k++) {
      const first = rules.findIndex((r) => r.secOrder === k);
      const last = rules.length - 1 - [...rules].reverse().findIndex((r) => r.secOrder === k);
      sections.push({
        id: secMarks[k].id,
        title: secMarks[k].title,
        order: k,
        ruleStart: first,
        ruleEnd: last,
      });
    }

    // 内容敏感哈希（FNV-1a 32bit，覆盖全部巴利整句，用于检测源文件是否改动）
    let h = 0x811c9dc5;
    const blob = rules.map((r) => r.key).join('|');
    for (let i = 0; i < blob.length; i++) {
      h ^= blob.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    const hash = 'h' + h.toString(16).padStart(8, '0') + '-' + rules.length;

    return {
      meta: {
        source: sourceName,
        hash: hash,
        generatedAt: new Date().toISOString(),
        ruleCount: rules.length,
        sectionCount: sections.length,
      },
      sections: sections,
      rules: rules,
    };
  }

  const api = { parsePatimokkha: parsePatimokkha, stripTags: stripTags, normalizePali: normalizePali };
  global.parsePatimokkha = parsePatimokkha;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
