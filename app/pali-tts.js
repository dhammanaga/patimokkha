/*
 * pali-tts.js — 巴利语发音
 * 依据权威巴利语发音指南（bhikkhu-manual / tipitaka.org / paligrammar / christham.net）
 * 把罗马转写「正确」转写成英语可读近似串：保留
 *   送气音 (kh/ph/th/ch/gh/dh/jh/ṭh/ḍh) 、长短元音 (ā/ī/ū vs a/i/u) 、
 *   鼻音 (ṃ/ṅ → ng) 、卷舌音 (ṭ/ḍ/ṇ) 、腭音 (c → ch) 的区别，
 * 让浏览器语音合成尽量接近真实巴利语，而非简单剥掉变音符号。
 *
 * 提供：
 *   PaliTTS.toReadable(pali)  罗马巴利 → 英语可读近似串（也用作「读音参考」标注）
 *   PaliTTS.speak(text, opts)  朗读。opts.key 指定音频清单键，命中本地真实录音则优先播录音
 *   PaliTTS.supported()        是否支持语音合成
 *   PaliTTS.setAudioBase(url)   设置本地录音目录（默认 'audio/'）
 *
 * 真实发音优先顺序：① 本地预录音频(window.PM_AUDIO[key])  ② Web Speech 近似朗读
 *   （若本机装有印度英语 en-IN 语音，听感最接近巴利；否则退 en-GB / en-US）
 */
(function (global) {
  'use strict';

  // —— 单字符 → 英语可读近似 ——
  // 送气音不在此表，由下方「辅音 + h」分支统一处理（塞音 + 空格 + 气声）
  var SINGLE = {
    'a': 'a', 'ā': 'aa', 'Ā': 'aa',
    'i': 'i', 'ī': 'ii', 'Ī': 'ii',
    'u': 'u', 'ū': 'uu', 'Ū': 'uu',
    'e': 'e', 'o': 'o',
    'ṃ': 'ng', 'ṁ': 'ng', 'Ṃ': 'ng',
    'ṅ': 'ng', 'Ṅ': 'ng',
    'ñ': 'ny', 'Ñ': 'ny',
    'ṇ': 'n', 'Ṇ': 'n',
    'ṭ': 't', 'Ṭ': 't',
    'ḍ': 'd', 'Ḍ': 'd',
    'ḷ': 'l', 'Ḷ': 'l',
    'c': 'ch',
    'v': 'v',
    'y': 'y', 'r': 'r', 'l': 'l', 's': 's', 'h': 'h',
    'm': 'm', 'n': 'n',
    'k': 'k', 'g': 'g', 'j': 'j', 't': 't', 'd': 'd', 'p': 'p', 'b': 'b'
  };

  // 可作为送气音前字（辅音）的字符集合
  var CONS = 'kgcjṭḍṇtdnpbmyrlvshḷñṅ';
  function isCons(ch) { return CONS.indexOf(ch) >= 0; }

  // 直接删除的字符（源文件里的智能引号 / 中间点等 artifact）
  var DROP = { '’': 1, '‘': 1, '“': 1, '”': 1, '·': 1, '•': 1 };

  // 罗马巴利 → 英语可读近似串
  function toReadable(s) {
    if (!s) return '';
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var ch = s[i];
      var nx = s[i + 1];
      if (DROP[ch]) continue;
      if (ch === "'" || ch === '`') continue;
      // 送气音：辅音 + 下一个字符是 h → 读作「塞音 + 空格 + 气声」
      //   （同时正确处理 lh/mh/ñh/vh 这类「两个辅音」：同样用空格隔开读成两音）
      if (isCons(ch) && nx === 'h') {
        out += (SINGLE[ch] !== undefined ? SINGLE[ch] : ch) + ' ';
        i++; // 跳过 h
        continue;
      }
      out += (SINGLE[ch] !== undefined) ? SINGLE[ch] : ch;
    }
    return out.replace(/\s+/g, ' ').trim();
  }

  // —— 语音合成（Web Speech API）——
  var synth = (typeof window !== 'undefined') ? window.speechSynthesis : null;
  var voices = [];
  function loadVoices() {
    if (!synth) return;
    try { voices = synth.getVoices() || []; } catch (e) { voices = []; }
  }
  if (synth) {
    if ('onvoiceschanged' in synth) synth.onvoiceschanged = loadVoices;
    loadVoices();
  }

  // 语音排序：印度英语 en-IN 听感最接近巴利（自带卷舌/送气）；其次 en-GB / en-US
  function rank(v) {
    var L = (v.lang || '').toLowerCase();
    if (/^en[-_]in/i.test(L)) return 5;
    if (/^en[-_]gb/i.test(L)) return 4;
    if (/^en[-_]us/i.test(L)) return 3;
    if (/^en/i.test(L)) return 2;
    return 1;
  }
  function pickVoice() {
    if (!synth) return null;
    if (!voices.length) { try { voices = synth.getVoices() || []; } catch (e) {} }
    if (!voices.length) return null;
    var best = null, bestR = 0;
    for (var i = 0; i < voices.length; i++) {
      var r = rank(voices[i]);
      if (r > bestR) { bestR = r; best = voices[i]; }
    }
    return best;
  }

  // —— 本地真实录音优先 ——
  var audioBase = 'audio/';
  function setAudioBase(u) { if (u) audioBase = u.replace(/\/+$/, '') + '/'; }

  // —— 本地巴利「逐词」TTS 音频（罗马巴利→天城体→Edge hi-IN 神经嗓音 预生成）——
  //    键 = 罗马转写单词（与 data.js 中 words[].p 一致）；值 = 相对 audio/ 的路径
  var wordAudio = {};
  function setWordAudio(obj) { if (obj && typeof obj === 'object') wordAudio = obj; }
  if (global.PM_PALI_WORDS) setWordAudio(global.PM_PALI_WORDS);
  function localAudioUrl(key) {
    if (!key || !global.PM_AUDIO) return null;
    var rel = global.PM_AUDIO[key];
    if (!rel) return null;
    if (/^https?:\/\//i.test(rel) || /^[a-z]:[\\/]/i.test(rel)) return rel; // 绝对路径/URL
    return audioBase + rel;
  }
  function playAudio(url) {
    try { var a = new global.Audio ? new global.Audio(url) : new Audio(url); a.play(); return true; }
    catch (e) { return false; }
  }

  var current = null;
  function speak(text, opts) {
    opts = opts || {};
    if (!text && !opts.key) return false;

    // ① 本地真实录音优先（整句）
    if (opts.key) {
      var au = localAudioUrl(opts.key);
      if (au && playAudio(au)) return true;
    }

    // ①.5 本地巴利「逐词」TTS 音频优先（Google 巴利语音，最贴近真人诵戒）
    if (opts.key && wordAudio[opts.key]) {
      var wrel = wordAudio[opts.key];
      var wu = (/^https?:\/\//i.test(wrel) || /^[a-z]:[\\/]/i.test(wrel)) ? wrel : audioBase + wrel;
      if (playAudio(wu)) return true;
    }

    // ② Web Speech 近似朗读（把巴利转写成可读近似串，兜底）
    if (!synth) return false;
    var readable = (window.PaliTTS && window.PaliTTS.toReadable)
      ? window.PaliTTS.toReadable(text) : text;
    if (!readable) return false;
    try { synth.cancel(); } catch (e) {}
    var u = new SpeechSynthesisUtterance(readable);
    var v = pickVoice();
    if (v) u.voice = v;
    u.lang = v ? v.lang : 'en-US';
    u.rate = (typeof opts.rate === 'number') ? opts.rate : 0.72;
    u.pitch = (typeof opts.pitch === 'number') ? opts.pitch : 1.0;
    try { synth.speak(u); current = u; } catch (e) { return false; }
    return true;
  }

  function supported() { return !!synth; }

  var api = {
    toReadable: toReadable,
    speak: speak,
    supported: supported,
    pickVoice: pickVoice,
    setAudioBase: setAudioBase,
    setWordAudio: setWordAudio
  };
  global.PaliTTS = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
