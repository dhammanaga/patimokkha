/* app.js — 巴帝摩卡背诵应用
 * 依赖：parser.js (window.parsePatimokkha)、data.js (window.PATIMOKKHA_DATA/HASH)、
 *        images/manifest.js (window.PM_IMAGES：{ ruleKey: "images/xxx.png" })
 * 全部本地运行，进度存于 localStorage，源文件可在「设置」中重新导入。
 */
(function () {
  'use strict';

  // ---------- 常量 ----------
  var BOX = [0, 1, 3, 7, 16, 35];            // 各盒子复习间隔(天)，下标=盒子号
  var BOX_LABEL = ['未学', '初学', '相识', '稳固', '熟练', '背诵'];
  var DAY = 86400000;
  var LS_KEY = 'pm_state_v1';

  // 数据（可被重新导入覆盖）
  var DATA = window.PATIMOKKHA_DATA;
  var HASH = window.PATIMOKKHA_HASH;
  var IMAGES = window.PM_IMAGES || {};
  // 真人录音清单：window.PM_AUDIO = { sentences:{ ruleKey:{clip,t0,t1,words:[{p,z,t0,t1}]} }, extras:{...} }
  var REC = window.PM_AUDIO || { sentences: {}, key2idx: {}, extras: {} };
  var recAudio = new Audio();
  recAudio.preload = 'none';
  function playRecClip(clip, start, end) {
    if (!clip) return false;
    recAudio.src = clip;
    recAudio.onloadedmetadata = function () {
      try { recAudio.currentTime = start || 0; } catch (e) {}
      var stopAt = (typeof end === 'number' && end > 0) ? end : (recAudio.duration || 0);
      recAudio.play().catch(function () {});
      recAudio.ontimeupdate = function () {
        if (recAudio.currentTime >= stopAt) { recAudio.pause(); recAudio.ontimeupdate = null; }
      };
    };
    recAudio.load();
    return true;
  }
  function playRecSentence(idx) {
    var m = REC.sentences[String(idx)];
    if (!m) return false;
    return playRecClip(m.clip, 0, null);
  }
  function playRecWord(idx, wi) {
    var m = REC.sentences[String(idx)];
    if (!m || !m.words || !m.words[wi]) return false;
    var w = m.words[wi];
    return playRecClip(m.clip, w.t0, w.t1);
  }

  // ===== v1.4 按钮化：整句/逐词切换播放状态 =====
  var sentState = { idx: -1 };
  var wordAudio = new Audio();
  wordAudio.preload = 'none';
  recAudio.onended = function () { sentState.idx = -1; updatePlayingUI(); };

  function clearPlayingUI() {
    document.querySelectorAll('.playing').forEach(function (e) { e.classList.remove('playing'); });
  }
  function updatePlayingUI() {
    clearPlayingUI();
    if (sentState.idx >= 0) {
      var s = '[data-idx="' + sentState.idx + '"].pali, .recite-item[data-idx="' + sentState.idx + '"] .pali, .rule-row[data-idx="' + sentState.idx + '"] .r-pali';
      document.querySelectorAll(s).forEach(function (e) { e.classList.add('playing'); });
    }
  }

  // 整句：同句再点停止；不同句切换
  function playSentenceToggle(idx) {
    if (sentState.idx === idx && !recAudio.paused && recAudio.src) {
      recAudio.pause(); recAudio.currentTime = 0;
      sentState.idx = -1; updatePlayingUI(); return;
    }
    if (!recAudio.paused) recAudio.pause();
    sentState.idx = idx; updatePlayingUI();
    if (!playRecSentence(idx)) {
      // 没有真人录音时用 TTS 朗读全文
      if (window.PaliTTS) {
        var rule = DATA.rules[idx];
        var pali = rule && rule.pali;
        if (pali) window.PaliTTS.speak(pali, { rate: state.settings.speakRate || 0.72 });
        else { sentState.idx = -1; updatePlayingUI(); }
      } else { sentState.idx = -1; updatePlayingUI(); }
    }
  }

  // 逐词：独立 wordAudio，不打断整句；无真人录音时回退 TTS
  function playWordClick(idx, wi) {
    var rule = DATA.rules[idx];
    var m = REC.sentences[String(idx)];
    var w = (m && m.words) ? m.words[wi] : null;
    var pali = (rule && rule.words && rule.words[wi]) ? rule.words[wi].p : null;
    var el = document.querySelector('.word[data-idx="' + idx + '"][data-wi="' + wi + '"], .wm[data-idx="' + idx + '"][data-wi="' + wi + '"], .rw[data-idx="' + idx + '"][data-wi="' + wi + '"]');
    clearPlayingUI();
    if (el) el.classList.add('playing');
    // 无真人录音、无该词、或时间戳无效（未念的括号注释词）→ 优先播预生成 mp3（Kannada TTS 真人感），未命中再走 Web Speech
    if (!w || w.t0 == null || w.t1 == null || !pali) {
      // 词文本去括号匹配 PM_PALI_WORDS（"(pavāraṇāya)" → "pavāraṇāya"）
      var key = pali.replace(/[()]/g, '').trim();
      var pre = (window.PM_PALI_WORDS || {})[key];
      var played = false;
      if (el) el.classList.remove('playing');
      if (pre) {
        var a = new Audio('audio/' + pre);
        a.onended = function () { if (el) el.classList.remove('playing'); };
        if (el) el.classList.add('playing');
        a.play().catch(function () {
          if (el) el.classList.remove('playing');
          if (window.PaliTTS) window.PaliTTS.speak(pali, { rate: state.settings.speakRate || 0.72 });
        });
        played = true;
      }
      if (!played && window.PaliTTS) {
        var ok = window.PaliTTS.speak(pali, { rate: state.settings.speakRate || 0.72 });
        if (!ok && window.PaliTTS.supported && !window.PaliTTS.supported()) banner('该词暂无发音（浏览器不支持巴利 TTS）', 'warn');
      } else if (!played) {
        if (el) banner('该词暂无发音', 'warn');
      }
      return;
    }
    try {
      wordAudio.pause();
      wordAudio.onloadedmetadata = function () {
        try { wordAudio.currentTime = w.t0 || 0; } catch (e) {}
        var stopAt = w.t1 || (wordAudio.duration || 0);
        wordAudio.play().catch(function () { /* 静默失败 */ });
        wordAudio.ontimeupdate = function () {
          if (wordAudio.currentTime >= stopAt) {
            wordAudio.pause(); wordAudio.ontimeupdate = null;
            if (el) el.classList.remove('playing');
          }
        };
      };
      wordAudio.onended = function () { if (el) el.classList.remove('playing'); };
      wordAudio.src = m.clip;
      wordAudio.load();
    } catch (e) {
      if (el) el.classList.remove('playing');
    }
  }

  // ---------- 状态 ----------
  var state = loadState();

  function loadState() {
    try {
      var s = JSON.parse(localStorage.getItem(LS_KEY));
      if (s && s.progress) return s;
    } catch (e) {}
    return {
      progress: {},
      settings: { dailyNew: 10 },
      meta: { hash: HASH, importedAt: null },
      newToday: { date: todayStr(), count: 0 },
      streak: { date: todayStr(), count: 0 }
    };
  }
  function save() { try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (e) {} }

  function todayStr() { return new Date().toDateString(); }

  // ---------- 进度访问 ----------
  function getProg(rule, createIfMissing) {
    var p = state.progress[rule.key];
    if (!p && createIfMissing) {
      p = { box: 0, due: Date.now(), reps: 0, lapses: 0, added: Date.now(), lastReviewed: null, lastRating: null };
      state.progress[rule.key] = p;
    }
    return p;
  }
  function isIntroduced(rule) { return !!state.progress[rule.key]; }
  function newTodayCount() {
    if (state.newToday.date !== todayStr()) { state.newToday = { date: todayStr(), count: 0 }; }
    return state.newToday.count;
  }

  // ---------- 间隔重复 ----------
  function applyRating(rule, rating) {
    var p = getProg(rule, true);
    p.reps += 1;
    p.lastReviewed = Date.now();
    p.lastRating = rating;
    if (rating === 'again') {
      p.lapses += 1; p.box = 1; p.due = Date.now() + 10 * 60 * 1000;
    } else if (rating === 'hard') {
      p.box = Math.max(1, p.box);
      var mult = p.box >= 2 ? 1 : 0.5;
      p.due = Date.now() + DAY * mult;
    } else if (rating === 'good') {
      p.box = Math.min(5, p.box + 1);
      p.due = Date.now() + DAY * BOX[p.box];
    } else { // easy
      p.box = Math.min(5, p.box + 2);
      p.due = Date.now() + DAY * BOX[Math.min(5, p.box)] * 1.3;
    }
    save();
  }

  // ---------- 学习队列（顺序解锁 + 每日新学上限）----------
  function buildQueue() {
    var now = Date.now();
    var due = [], introducedIdx = [];
    DATA.rules.forEach(function (r) {
      if (r.hidden) return;
      var p = state.progress[r.key];
      if (p) {
        introducedIdx.push(r.idx);
        if (p.due <= now) due.push(r);
      }
    });
    due.sort(function (a, b) { return state.progress[a.key].due - state.progress[b.key].due; });

    // 新卡：从 frontier 之后按全文顺序连续取出，受每日上限与「前句已学」门控
    var maxIntro = introducedIdx.length ? Math.max.apply(null, introducedIdx) : -1;
    var allowed = Math.max(0, state.settings.dailyNew - newTodayCount());
    var frontierRated = maxIntro === -1 || (state.progress[DATA.rules[maxIntro].key].reps >= 1);
    var news = [];
    if (frontierRated && allowed > 0) {
      for (var i = maxIntro + 1; i < DATA.rules.length && news.length < allowed; i++) {
        var r = DATA.rules[i];
        if (r.hidden) continue;
        if (!isIntroduced(r)) news.push(r);
      }
    }
    return due.concat(news);
  }

  // 连诵可达：从 0 起，所有 0..k 句均 box>=2 的最大 k
  function reciteFrontier() {
    var k = -1;
    for (var i = 0; i < DATA.rules.length; i++) {
      if (DATA.rules[i].hidden) continue; // 隐藏条不阻断连诵链
      var p = state.progress[DATA.rules[i].key];
      if (p && p.box >= 2) k = i; else break;
    }
    return k; // -1 表示尚无
  }
  function sectionOf(rule) { return DATA.sections[rule.secOrder]; }

  // ---------- 章节目录（学习/熟读/连诵 通用跳转条）----------
  function ensureToc(containerId, mode) {
    var box = document.getElementById(containerId);
    if (!box) return;
    if (box.dataset.mode === mode && box.childElementCount) return; // 已挂载则免重建
    box.dataset.mode = mode;
    box.innerHTML = '';
    box.appendChild(el('<span class="toc-label">章目录</span>'));
    DATA.sections.forEach(function (s) {
      var b = el('<button type="button" class="toc-item" data-sec="' + s.order + '">' + esc(s.title) + '</button>');
      b.onclick = function () {
        if (mode === 'study') jumpStudyToSection(s.order);
        else if (mode === 'read') jumpReadToSection(s.order);
        else if (mode === 'recite') jumpReciteToSection(s.order);
      };
      box.appendChild(b);
    });
  }
  function highlightToc(containerId, order) {
    var box = document.getElementById(containerId);
    if (!box) return;
    box.querySelectorAll('.toc-item').forEach(function (b) {
      b.classList.toggle('active', Number(b.dataset.sec) === Number(order));
    });
  }
  function jumpStudyToSection(order) {
    if (!session.queue.length) { banner('请先开始学习。', 'warn'); return; }
    var idx = session.queue.findIndex(function (r) { return sectionOf(r).order === order; });
    if (idx < 0) { banner('该章暂不在今日学习队列中。可前往「熟读」逐章浏览。', 'warn'); return; }
    session.pos = idx; session.revealed = false;
    highlightToc('studyToc', order);
    renderStudyCard();
  }
  function jumpReadToSection(order) {
    if (!readSession.queue.length) return;
    var idx = readSession.queue.findIndex(function (r) { return sectionOf(r).order === order; });
    if (idx < 0) return;
    readSession.pos = idx; stopReadLoop();
    highlightToc('readToc', order);
    renderReadCard();
  }
  function jumpReciteToSection(order) {
    var k = reciteFrontier();
    if (k < 0) { banner('还没有可连诵的句子。', 'warn'); return; }
    if (order > sectionOf(DATA.rules[k]).order) { banner('该章尚未进入连诵范围（需前面全部达「稳固」）。', 'warn'); return; }
    var firstRule = null;
    for (var i = 0; i <= k; i++) { if (!DATA.rules[i].hidden && sectionOf(DATA.rules[i]).order === order) { firstRule = DATA.rules[i]; break; } }
    if (!firstRule) return;
    var node = document.getElementById('recite-item-' + firstRule.idx);
    if (node) { node.scrollIntoView({ behavior: 'smooth', block: 'start' }); highlightToc('reciteToc', order); }
  }

  // ---------- 工具 ----------
  function el(html) { var t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }

  // 发音按钮 HTML（整句 / 单词通用）；点击由全局委托处理
  //   key：音频清单键（命中本地真实录音则优先播录音）；整句用 rule.key，单词用其罗马字
  function speakBtn(text, extraClass, key) {
    if (!text && !key) return '';
    var rd = (window.PaliTTS && window.PaliTTS.toReadable) ? window.PaliTTS.toReadable(text) : text;
    if (!rd) rd = '';
    return '<button type="button" class="speak' + (extraClass ? ' ' + extraClass : '') + '" data-speak="' + esc(rd) + '"' + (key ? ' data-key="' + esc(key) + '"' : '') + ' title="朗读发音（真实录音优先）">🔊</button>';
  }
  // 真人录音按钮：整句 / 逐词（点击由全局委托处理；统一用唯一 idx 索引）
  function recSentBtn(idx) {
    return '<button type="button" class="rec-sent" data-idx="' + idx + '" title="播放真人录音（整句）">🔉</button>';
  }
  function recWordBtn(idx, wi) {
    return '<button type="button" class="rec-word" data-idx="' + idx + '" data-wi="' + wi + '" title="播放真人发音（单词）">🔊</button>';
  }
  function imgFor(rule) { return IMAGES[rule.key] || null; }
  function lotusSVG() {
    return '<svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="#b9a87e" stroke-width="1.4">' +
      '<path d="M12 21c4-2 7-5 7-9 0-1-1-2-2-1-2 2-4 3-5 4-1-1-3-2-5-4-1-1-2 0-2 1 0 4 3 7 7 9z"/>' +
      '<path d="M12 21v-7"/><circle cx="12" cy="21" r="1.2" fill="#b9a87e" stroke="none"/></svg>';
  }
  function illusHTML(rule, cls) {
    var src = imgFor(rule);
    if (src) return '<img class="' + (cls || 'illus') + '" src="' + esc(src) + '" alt="记忆插图">';
    return '<div class="' + (cls || 'illus') + ' placeholder">' + lotusSVG() + '<span>记忆插图待生成</span></div>';
  }

  // ---------- 视图切换 ----------
  function showView(name) {
    document.querySelectorAll('.view').forEach(function (v) { v.classList.remove('active'); });
    document.getElementById('view-' + name).classList.add('active');
    document.querySelectorAll('#tabs button').forEach(function (b) { b.classList.toggle('active', b.dataset.view === name); });
    if (name === 'dashboard') renderDashboard();
    if (name === 'browse') renderBrowse();
    if (name === 'recite') renderRecite();
    if (name !== 'read') { try { stopReadLoop(); } catch (e) {} if (mediaRec && mediaRec.recording) stopRec(); }
  }
  function banner(msg, type) {
    var b = document.getElementById('banner');
    b.className = 'banner show ' + (type || 'info');
    b.innerHTML = msg;
    if (type !== 'err') setTimeout(function () { b.className = 'banner'; }, 6000);
  }

  // ---------- 仪表盘 ----------
  function renderDashboard() {
    var total = DATA.rules.filter(function (r) { return !r.hidden; }).length, studied = 0, mastered = 0, readN = 0;
    Object.keys(state.progress).forEach(function (k) {
      var p = state.progress[k];
      if (p.box >= 1) studied++;
      if (p.box >= 4) mastered++;
      if (p.read) readN++;
    });
    var rf = reciteFrontier();
    var grid = document.getElementById('statGrid');
    grid.innerHTML =
      stat(total, '总句数') + stat(studied, '已学', 'gold') + stat(readN, '已熟读', 'read') +
      stat(mastered, '熟练', 'teal') + stat(rf + 1, '连诵可达', 'maroon');
    // 章节条
    var bars = document.getElementById('sectionBars'); bars.innerHTML = '';
    DATA.sections.forEach(function (s) {
      var n = 0, st = 0, ma = 0, rd = 0;
      for (var i = s.ruleStart; i <= s.ruleEnd; i++) {
        var r = DATA.rules[i];
        if (r.hidden) continue;
        n++;
        var p = state.progress[r.key];
        if (p && p.box >= 1) st++;
        if (p && p.box >= 4) ma++;
        if (p && p.read) rd++;
      }
      var row = el('<div class="section-row"><div class="head"><span class="t">' + esc(s.title) +
        '</span><span class="c">已熟读 ' + rd + ' / 已学 ' + st + ' / 熟练 ' + ma + ' / 共 ' + n + '</span></div>' +
        '<div class="bar"><span style="width:' + (st / n * 100) + '%"></span></div>' +
        '<div class="bar read" style="margin-top:4px"><span style="width:' + (rd / n * 100) + '%"></span></div>' +
        '<div class="bar master" style="margin-top:4px"><span style="width:' + (ma / n * 100) + '%"></span></div></div>');
      bars.appendChild(row);
    });
  }
  function stat(num, lbl, cls) {
    return '<div class="stat"><div class="num ' + (cls || '') + '">' + num + '</div><div class="lbl">' + lbl + '</div></div>';
  }

  // ---------- 学习 ----------
  var session = { queue: [], pos: 0, revealed: false };
  function startStudy() {
    session.queue = buildQueue();
    session.pos = 0; session.revealed = false;
    showView('study');
    ensureToc('studyToc', 'study');
    if (!session.queue.length) { renderStudyDone(); return; }
    renderStudyCard();
  }
  // 从「学习」tab 进入：已有进行中的会话则续接当前卡，否则（首次/已学完）开新会话
  function enterStudy() {
    if (session.queue.length && session.pos < session.queue.length) {
      showView('study');
      ensureToc('studyToc', 'study');
      renderStudyCard();
    } else {
      startStudy();
    }
  }
  function renderStudyDone() {
    var w = document.getElementById('studyWrap');
    w.innerHTML = '<div class="done-msg"><div class="big">善哉 · 今日这一程学完啦 🪷</div>' +
      '<p class="muted">没有到期复习，也没有可解锁的新句。<br>可去「连诵」巩固已学的部分，或复习以解锁下一句。</p>' +
      '<div class="btn-row" style="justify-content:center"><button class="btn ghost gold" onclick="PM.recite()">📿 连诵</button>' +
      '<button class="btn ghost" onclick="PM.dash()">返回仪表盘</button></div></div>';
  }
  function renderStudyCard() {
    var rule = session.queue[session.pos];
    var sec = sectionOf(rule);
    var total = session.queue.length;
    var w = document.getElementById('studyWrap');
    w.innerHTML = '';
    var card = el('<div class="card">' + illusHTML(rule) +
      '<div class="body">' +
      '<div class="sec-tag">' + esc(sec.title) + ' · 第 ' + (rule.idx + 1) + ' 句</div>' +
      '<div class="meaning">' + esc(rule.meaning || '（无参考译文）') + '</div>' +
      (rule.note ? '<div class="note">' + esc(rule.note) + '</div>' : '') +
      '<button class="btn reveal-btn" id="revealBtn">显示巴利与逐词</button>' +
      '<div class="answer" id="answer"></div>' +
      '</div></div>');
    var prog = el('<div class="progress-pill"><span>第 ' + (session.pos + 1) + ' / ' + total + ' 张</span>' +
      '<span class="bar"><span style="width:' + ((session.pos) / total * 100) + '%"></span></span>' +
      '<span>' + studiedToday() + ' 已学今日</span></div>');
    var nav = el('<div class="study-nav">' +
      '<button class="btn ghost" id="stPrev"' + (session.pos <= 0 ? ' disabled' : '') + '>← 上一句</button>' +
      '<button class="btn ghost" id="stNext"' + (session.pos >= total - 1 ? ' disabled' : '') + '>下一句 →</button>' +
      '</div>');
    w.appendChild(prog); w.appendChild(card); w.appendChild(nav);

    function doReveal() {
      session.revealed = true;
      var a = document.getElementById('answer');
      var words = rule.words.map(function (wd, i) {
        return '<div class="word" data-idx="' + rule.idx + '" data-wi="' + i + '">' + speakBtn(wd.p, null, wd.p) + '<span class="p">' + esc(wd.p) + '</span><span class="z' + (wd.z ? '' : ' empty') + '">' + esc(wd.z || '—') + '</span></div>';
      }).join('');
      a.innerHTML = recSentBtn(rule.idx) + speakBtn(rule.pali, 'speak-full', rule.key) + '<div class="pali-full pali" data-idx="' + rule.idx + '">' + esc(rule.pali) + '</div>' + '<div class="words">' + words + '</div>' +
        '<div class="rating">' +
        '<button class="again" data-r="again">忘了</button>' +
        '<button class="hard" data-r="hard">困难</button>' +
        '<button class="good" data-r="good">良好</button>' +
        '<button class="easy" data-r="easy">轻松</button></div>';
      a.classList.add('show');
      a.querySelectorAll('.rating button').forEach(function (b) {
        b.onclick = function () { rate(rule, b.dataset.r); };
      });
    }
    document.getElementById('revealBtn').onclick = doReveal;
    if (session.revealed) doReveal();
    document.getElementById('stPrev').onclick = function () { studyNav(-1); };
    document.getElementById('stNext').onclick = function () { studyNav(1); };
    highlightToc('studyToc', sectionOf(rule).order);
  }
  function studyNav(dir) {
    var np = session.pos + dir;
    if (np < 0 || np >= session.queue.length) return;
    session.pos = np;
    session.revealed = false; // 新句重新隐藏答案，保持「先回忆再揭示」
    renderStudyCard();
  }
  function studiedToday() {
    var n = 0;
    Object.keys(state.progress).forEach(function (k) { if (state.progress[k].added && new Date(state.progress[k].added).toDateString() === todayStr()) n++; });
    return n;
  }
  function rate(rule, rating) {
    var wasNew = !isIntroduced(rule);
    applyRating(rule, rating);
    if (wasNew && state.newToday.date === todayStr()) state.newToday.count++;
    save();
    session.pos++;
    session.revealed = false;
    if (session.pos >= session.queue.length) renderStudyDone();
    else renderStudyCard();
  }

  // ---------- 熟读（先朗诵熟练，再开始背诵）----------
  // 依据认知科学实证有效的熟读方法：慢速原音跟读 → 单句循环读顺 → 录音回听对比 → 标记已熟读
  var readSession = { queue: [], pos: 0, showPali: true, rate: 1, loopTimes: 3 };
  var readAudio = new Audio(); readAudio.preload = 'auto';
  var readLoop = { running: false, timer: null };
  var mediaRec = { rec: null, chunks: [], stream: null, url: null, audio: null, recording: false };

  function startRead() {
    readSession.queue = DATA.rules.filter(function (r) { return !r.hidden; });
    readSession.pos = 0;
    showView('read');
    ensureToc('readToc', 'read');
    renderReadCard();
  }
  function enterRead() {
    if (readSession.queue.length && readSession.pos < readSession.queue.length) { showView('read'); ensureToc('readToc', 'read'); renderReadCard(); }
    else startRead();
  }
  function readCount() {
    var n = 0;
    Object.keys(state.progress).forEach(function (k) { if (state.progress[k] && state.progress[k].read) n++; });
    return n;
  }
  function stopReadLoop() { readLoop.running = false; if (readLoop.timer) clearTimeout(readLoop.timer); try { readAudio.pause(); } catch (e) {} updateReadLoopBtn(); }
  function playReadSentence(idx, rate, cb) {
    var m = REC.sentences[String(idx)];
    if (!m || !m.clip) { if (cb) cb(); return; }
    readAudio.src = m.clip;
    readAudio.playbackRate = rate || 1;
    readAudio.onended = function () { if (cb) cb(); };
    readAudio.onerror = function () { if (cb) cb(); };
    readAudio.play().catch(function () {});
  }
  function startReadLoop() {
    stopReadLoop();
    if (readSession.pos >= readSession.queue.length) return;
    var idx = readSession.queue[readSession.pos].idx;
    readLoop.running = true; updateReadLoopBtn();
    stepReadLoop(idx, 1);
  }
  function stepReadLoop(idx, n) {
    if (!readLoop.running) return;
    if (readSession.loopTimes !== 'inf' && n > readSession.loopTimes) { readLoop.running = false; updateReadLoopBtn(); return; }
    playReadSentence(idx, readSession.rate, function () {
      if (!readLoop.running) return;
      if (readSession.loopTimes !== 'inf' && n >= readSession.loopTimes) { readLoop.running = false; updateReadLoopBtn(); return; }
      readLoop.timer = setTimeout(function () { stepReadLoop(idx, n + 1); }, 700);
    });
  }
  function startRec() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { banner('当前环境不支持录音（需用 https 或 localhost 打开本应用）。', 'warn'); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      mediaRec.stream = stream; mediaRec.chunks = [];
      var mr = new MediaRecorder(stream);
      mediaRec.rec = mr; mediaRec.recording = true;
      mr.ondataavailable = function (e) { if (e.data && e.data.size) mediaRec.chunks.push(e.data); };
      mr.onstop = function () {
        if (mediaRec.url) URL.revokeObjectURL(mediaRec.url);
        var blob = new Blob(mediaRec.chunks, { type: 'audio/webm' });
        mediaRec.url = URL.createObjectURL(blob);
        if (!mediaRec.audio) mediaRec.audio = new Audio();
        mediaRec.audio.src = mediaRec.url;
        stream.getTracks().forEach(function (t) { t.stop(); });
        mediaRec.recording = false; renderReadCard();
      };
      mr.start(); renderReadCard();
    }).catch(function (err) { banner('无法访问麦克风：' + (err && err.message ? err.message : err), 'err'); });
  }
  function stopRec() { if (mediaRec.rec && mediaRec.rec.state === 'recording') mediaRec.rec.stop(); }
  function updateReadLoopBtn() { var b = document.getElementById('loopBtn'); if (b) b.textContent = readLoop.running ? '■ 停止' : '▶ 开始循环'; }
  function markRead(rule) {
    var p = state.progress[rule.key] || { box: 0, due: Date.now(), reps: 0, lapses: 0, added: Date.now(), lastReviewed: null, lastRating: null };
    p.read = true; state.progress[rule.key] = p; save();
    banner('已标记第 ' + (rule.idx + 1) + ' 句为「已熟读」 🪷 随喜', 'info');
    // 标记后自动跳下一句（末句则停在原地）
    if (readSession.pos < readSession.queue.length - 1) {
      stopReadLoop();
      readSession.pos++;
      renderReadCard();
    } else {
      renderReadCard();
    }
  }
  function renderReadCard() {
    var rule = readSession.queue[readSession.pos];
    if (!rule) { document.getElementById('readWrap').innerHTML = '<div class="empty-hint">没有可熟读的句。</div>'; return; }
    var sec = sectionOf(rule);
    var total = readSession.queue.length;
    var isRead = !!(state.progress[rule.key] && state.progress[rule.key].read);
    var words = rule.words.map(function (wd, i) {
      return '<div class="word" data-idx="' + rule.idx + '" data-wi="' + i + '">' + speakBtn(wd.p, null, wd.p) + '<span class="p">' + esc(wd.p) + '</span><span class="z' + (wd.z ? '' : ' empty') + '">' + esc(wd.z || '—') + '</span></div>';
    }).join('');
    var paliHtml = readSession.showPali
      ? (recSentBtn(rule.idx) + speakBtn(rule.pali, 'speak-full', rule.key) + '<div class="pali-full pali" data-idx="' + rule.idx + '">' + esc(rule.pali) + '</div>')
      : '<div class="hint" style="color:var(--muted)">巴利文已隐藏（跟读模式）。点「显示巴利」查看。</div>';

    var rateBtns = [['0.6', '慢'], ['1', '常速'], ['1.3', '快']].map(function (p) {
      return '<button data-rate="' + p[0] + '" class="' + (String(readSession.rate) === p[0] ? 'active' : '') + '">' + p[1] + '</button>';
    }).join('');
    var loopOpts = [['1', '1 遍'], ['3', '3 遍'], ['5', '5 遍'], ['inf', '连续']].map(function (p) {
      return '<option value="' + p[0] + '"' + (String(readSession.loopTimes) === p[0] ? ' selected' : '') + '>' + p[1] + '</option>';
    }).join('');

    var w = document.getElementById('readWrap');
    w.innerHTML =
      '<div class="read-top"><span class="info">第 ' + (readSession.pos + 1) + ' / ' + total + ' 句 · ' + esc(sec.title) + '</span>' +
      '<span class="info">已熟读 <b>' + readCount() + '</b> / ' + total + '</span></div>' +
      '<div class="read-controls">' +
        '<div class="grp"><span class="lbl">原音速度</span><span class="seg" id="rateSeg">' + rateBtns + '</span></div>' +
        '<div class="grp"><span class="lbl">🔁 循环</span><select id="loopSel">' + loopOpts + '</select>' +
          '<button class="btn ghost" id="loopBtn" style="padding:6px 12px;font-size:13px">' + (readLoop.running ? '■ 停止' : '▶ 开始循环') + '</button></div>' +
        '<div class="grp"><span class="lbl">🎙 录音</span>' +
          '<button class="btn ghost" id="recBtn" style="padding:6px 12px;font-size:13px">' + (mediaRec.recording ? '■ 停止并回放' : '● 开始录音') + '</button>' +
          '<button class="btn ghost" id="myRecBtn" style="padding:6px 12px;font-size:13px"' + (mediaRec.url ? '' : ' disabled') + '>再听我的录音</button>' +
          '<span class="rec-status"><span class="rec-dot' + (mediaRec.recording ? ' on' : '') + '"></span>' + (mediaRec.recording ? '录音中…' : '跟读对比') + '</span></div>' +
      '</div>' +
      '<div class="read-prog">方法：先听原音（可放慢），再<b>跟读</b>；用 🔁 循环把它读顺，用 🎙 录下自己与原音对比。整句读熟后点「✓ 标记已熟读」。</div>' +
      '<div class="card">' + illusHTML(rule) +
        '<div class="body">' +
          '<div class="sec-tag">' + esc(sec.title) + ' · 第 ' + (rule.idx + 1) + ' 句</div>' +
          '<div class="meaning">' + esc(rule.meaning || '（无参考译文）') + '</div>' +
          (rule.note ? '<div class="note">' + esc(rule.note) + '</div>' : '') +
          paliHtml +
          '<div class="words">' + words + '</div>' +
        '</div></div>' +
      '<div class="read-actions">' +
        '<button class="btn ghost" id="rdPrev">← 上一句</button>' +
        '<button class="btn ghost" id="rdNext">下一句 →</button>' +
        '<button class="btn ghost" id="rdTogglePali">' + (readSession.showPali ? '隐藏巴利（跟读）' : '显示巴利') + '</button>' +
        '<button class="btn mark' + (isRead ? ' done' : '') + '" id="rdMark">' + (isRead ? '✓ 已熟读' : '✓ 标记已熟读') + '</button>' +
      '</div>';

    w.querySelectorAll('#rateSeg button').forEach(function (b) {
      b.onclick = function () { readSession.rate = parseFloat(b.dataset.rate); renderReadCard(); };
    });
    document.getElementById('loopSel').onchange = function (e) { readSession.loopTimes = e.target.value === 'inf' ? 'inf' : parseInt(e.target.value, 10); };
    document.getElementById('loopBtn').onclick = function () { if (readLoop.running) stopReadLoop(); else startReadLoop(); };
    document.getElementById('recBtn').onclick = function () { if (mediaRec.recording) stopRec(); else startRec(); };
    document.getElementById('myRecBtn').onclick = function () { if (mediaRec.audio) mediaRec.audio.play(); };
    document.getElementById('rdPrev').onclick = function () { stopReadLoop(); if (readSession.pos > 0) { readSession.pos--; renderReadCard(); } };
    document.getElementById('rdNext').onclick = function () { stopReadLoop(); if (readSession.pos < total - 1) { readSession.pos++; renderReadCard(); } };
    document.getElementById('rdTogglePali').onclick = function () { readSession.showPali = !readSession.showPali; renderReadCard(); };
    document.getElementById('rdMark').onclick = function () { markRead(rule); };
    highlightToc('readToc', sectionOf(rule).order);
  }

  // ---------- 连诵 ----------
  var blurOn = true;
  function renderRecite() {
    ensureToc('reciteToc', 'recite');
    var k = reciteFrontier();
    var info = document.getElementById('reciteInfo');
    var list = document.getElementById('reciteList');
    if (k < 0) {
      list.innerHTML = '<div class="empty-hint">还没有可连诵的句子。先去「学习」把前面的句子练到「稳固」(box≥2) 吧。</div>';
      info.textContent = ''; return;
    }
    info.textContent = '连诵范围：第 1 – ' + (k + 1) + ' 句（从开头起，全部达「稳固」）';
    list.innerHTML = '';
    for (var i = 0; i <= k; i++) {
      var rule = DATA.rules[i];
      if (rule.hidden) continue;
      var sec = sectionOf(rule);
      var words = rule.words.map(function (wd, wi) {
        return '<span class="wm" data-idx="' + i + '" data-wi="' + wi + '"><span class="p">' + esc(wd.p) + '</span><span class="z">' + esc(wd.z) + '</span></span>';
      }).join('');
      var item = el('<div class="recite-item" id="recite-item-' + i + '" data-idx="' + i + '"><div class="top">' + illusHTML(rule, 'illus') +
        '<div class="meta"><div class="idx">' + esc(sec.title) + ' · 第 ' + (i + 1) + ' 句</div>' +
        '<div class="meaning">' + esc(rule.meaning) + '</div>' +
        recSentBtn(rule.idx) + speakBtn(rule.pali, 'speak-full', rule.key) +
        '<div class="pali pali' + (blurOn ? ' hidden' : '') + '" data-i="' + i + '">' + esc(rule.pali) + '</div>' +
        '<div class="words-mini">' + words + '</div></div></div></div>');
      list.appendChild(item);
    }
    list.querySelectorAll('.pali.hidden').forEach(function (p) {
      p.onclick = function (ev) {
        p.classList.remove('hidden');
        p.onclick = null; // 本次仅「显示」；解除后再次点击走正常播放
        if (ev && ev.stopPropagation) ev.stopPropagation();
      };
    });
  }

  // ---------- 浏览 ----------
  function renderBrowse(filter) {
    filter = (filter || '').toLowerCase().trim();
    var list = document.getElementById('browseList'); list.innerHTML = '';
    DATA.sections.forEach(function (s) {
      var rows = [];
      for (var i = s.ruleStart; i <= s.ruleEnd; i++) {
        var r = DATA.rules[i];
        if (r.hidden) continue;
        if (filter && (r.pali.toLowerCase().indexOf(filter) < 0 && (r.meaning || '').toLowerCase().indexOf(filter) < 0)) continue;
        var p = state.progress[r.key];
        var box = p ? p.box : 0;
        var dotcls = box >= 1 ? 'b' + box : '';
        var row = el('<div class="rule-row" id="rule-' + r.idx + '" data-idx="' + r.idx + '">' +
          '<span class="r-idx" title="全局第 ' + (r.idx + 1) + ' 句">' + (r.idx + 1) + '</span>' +
          illusHTML(r, 'illus') +
          '<div class="r-main"><div class="r-pali pali" data-idx="' + r.idx + '">' + speakBtn(r.pali, 'speak-full', r.key) + esc(r.pali) + '</div>' +
          '<div class="r-meaning">' + esc(r.meaning) + '</div>' +
          '<div class="r-words">' + r.words.map(function (w, wi) { return '<span class="rw" data-idx="' + r.idx + '" data-wi="' + wi + '">' + speakBtn(w.p, null, w.p) + esc(w.p) + (w.z ? '(' + esc(w.z) + ')' : '') + '</span>'; }).join(' · ') + '</div></div>' +
          '<div class="r-box"><div class="dot ' + dotcls + '"></div>' + BOX_LABEL[box] + '</div></div>');
        rows.push(row);
      }
      if (!rows.length) return;
      var sec = el('<div class="browse-sec"><div class="sec-head"><span>' + esc(s.title) + '</span>' +
        '<span class="cnt">' + rows.length + ' 句</span></div><div class="sec-body"></div></div>');
      var body = sec.querySelector('.sec-body');
      rows.forEach(function (ro) { body.appendChild(ro); });
      sec.querySelector('.sec-head').onclick = function () { sec.classList.toggle('open'); };
      list.appendChild(sec);
    });
    // 默认展开前两个有内容的章节
    var opened = 0;
    list.querySelectorAll('.browse-sec').forEach(function (s) { if (opened < 2) { s.classList.add('open'); opened++; } });
    if (!list.childElementCount) {
      list.innerHTML = '<div class="empty-hint">没有匹配「' + esc(filter) + '」的句子。</div>';
    }
  }

  // ---------- 设置：重新导入源文件 ----------
  function handleImportFile(file) {
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function (e) {
      try {
        var html = e.target.result;
        var parsed = window.parsePatimokkha(html, file.name);
        var oldHash = HASH;
        // 进度按 rule.key 自动保留（key 为内容哈希）
        var kept = 0;
        Object.keys(state.progress).forEach(function (k) {
          if (parsed.rules.some(function (r) { return r.key === k; })) kept++;
        });
        // 替换运行期数据
        DATA = parsed; HASH = parsed.meta.hash;
        state.meta.hash = HASH; state.meta.importedAt = new Date().toISOString();
        save();
        if (HASH !== oldHash) {
          banner('✅ 源文件已更新（哈希 ' + HASH + '）。已按内容保留 ' + kept + ' 条学习进度；本会话内生效。需永久保存请让我重跑 build.js。', 'info');
        } else {
          banner('ℹ️ 源文件内容与当前一致，无需更新。进度原样保留。', 'info');
        }
        renderDashboard();
      } catch (err) {
        banner('❌ 解析失败：' + esc(err.message), 'err');
      }
    };
    reader.readAsText(file, 'utf-8');
  }

  // ---------- 初始化 ----------
  function bind() {
    if (typeof state.settings.speakRate !== 'number') state.settings.speakRate = 0.72;
    // 发音按钮全局委托（整句 / 逐词通用）
    document.addEventListener('click', function (e) {
      var t = e.target;

      // v1.4 按钮化：整句本身可点 → toggle 播放/停止
      var sentEl = (t && t.closest) ? t.closest('.pali-full.pali[data-idx], .recite-item[data-idx] .pali, .rule-row[data-idx] .r-pali') : null;
      if (sentEl) {
        var container = sentEl.closest('[data-idx]');
        var idx = container && parseInt(container.dataset.idx, 10);
        if (!isNaN(idx)) { e.preventDefault(); playSentenceToggle(idx); return; }
      }
      // v1.4 按钮化：逐词本身可点 → 播该词（不打断整句）
      var wordEl = (t && t.closest) ? t.closest('.word[data-idx][data-wi], .wm[data-idx][data-wi], .rw[data-idx][data-wi]') : null;
      if (wordEl) {
        e.preventDefault();
        playWordClick(parseInt(wordEl.dataset.idx, 10), parseInt(wordEl.dataset.wi, 10));
        return;
      }

      var b = (t && t.closest) ? t.closest('.speak') : null;
      if (b && b.dataset && b.dataset.speak) {
        e.preventDefault();
        // 真人录音优先：整句（data-key 经 key2idx 命中则播整句录音，否则回退 TTS）
        if (b.dataset.key && REC.key2idx && REC.key2idx[b.dataset.key] != null) {
          playRecSentence(REC.key2idx[b.dataset.key]); return;
        }
        if (window.PaliTTS) {
          var ok = window.PaliTTS.speak(b.dataset.speak, { rate: state.settings.speakRate || 0.72, key: b.dataset.key });
          if (!ok && window.PaliTTS.supported && !window.PaliTTS.supported()) banner('当前浏览器或环境不支持语音合成（Web Speech API）。', 'warn');
        }
        return;
      }
      // 整句真人录音（🔉 按钮，按唯一 idx）
      var rs = (t && t.closest) ? t.closest('.rec-sent') : null;
      if (rs && rs.dataset && rs.dataset.idx != null) {
        e.preventDefault();
        playRecSentence(parseInt(rs.dataset.idx, 10)); return;
      }
      // 逐词真人录音（🔊 按钮，在该句录音内 seek 到单词区间）
      var rw = (t && t.closest) ? t.closest('.rec-word') : null;
      if (rw && rw.dataset && rw.dataset.idx != null) {
        e.preventDefault();
        playRecWord(parseInt(rw.dataset.idx, 10), parseInt(rw.dataset.wi, 10));
      }
    });
    document.getElementById('tabs').addEventListener('click', function (e) {
      if (!e.target.dataset.view) return;
      if (e.target.dataset.view === 'study') enterStudy();
      else if (e.target.dataset.view === 'read') enterRead();
      else showView(e.target.dataset.view);
    });
    document.getElementById('startStudy').onclick = startStudy;
    document.getElementById('startRecite').onclick = function () { showView('recite'); };
    document.getElementById('gotoBrowse').onclick = function () { showView('browse'); };
    document.getElementById('reciteRefresh').onclick = renderRecite;
    document.getElementById('toggleBlur').onclick = function () { blurOn = !blurOn; renderRecite(); };

    var dn = document.getElementById('dailyNew');
    dn.value = state.settings.dailyNew;
    document.getElementById('dailyNewVal').textContent = state.settings.dailyNew;
    dn.oninput = function () { state.settings.dailyNew = +dn.value; document.getElementById('dailyNewVal').textContent = dn.value; save(); };

    var sr = document.getElementById('speakRate');
    if (sr) {
      sr.value = state.settings.speakRate;
      document.getElementById('speakRateVal').textContent = (state.settings.speakRate || 0.72).toFixed(2);
      sr.oninput = function () {
        state.settings.speakRate = +sr.value;
        document.getElementById('speakRateVal').textContent = (+sr.value).toFixed(2);
        save();
      };
    }

    var drop = document.getElementById('dropZone');
    var fi = document.getElementById('fileInput');
    fi.onchange = function () { handleImportFile(fi.files[0]); };
    drop.ondragover = function (e) { e.preventDefault(); drop.classList.add('drag'); };
    drop.ondragleave = function () { drop.classList.remove('drag'); };
    drop.ondrop = function (e) { e.preventDefault(); drop.classList.remove('drag'); if (e.dataTransfer.files[0]) handleImportFile(e.dataTransfer.files[0]); };

    // 浏览页搜索：输入即过滤（巴利 / 汉译）
    var bs = document.getElementById('browseSearch');
    if (bs) {
      bs.addEventListener('input', function () { renderBrowse(bs.value); });
    }

    document.getElementById('exportBtn').onclick = exportProgress;
    document.getElementById('importProgress').onchange = importProgress;
    document.getElementById('resetBtn').onclick = function () {
      if (confirm('确定清空全部学习进度？此操作不可撤销。')) {
        state.progress = {}; state.newToday = { date: todayStr(), count: 0 }; save();
        banner('已清空进度。', 'info'); renderDashboard();
      }
    };
    document.getElementById('dataInfo').textContent = '当前数据集哈希：' + HASH + ' · 来源：' + DATA.meta.source;

    // 全局快捷
    window.PM = { dash: function () { showView('dashboard'); }, recite: function () { showView('recite'); } };

    // v1.4 Header 吸附收起：滚下隐藏、滚上显示、到顶必展开
    (function () {
      var lastY = 0, accum = 0, raf = 0;
      var h = null;
      function tick() {
        raf = 0;
        var y = window.scrollY || window.pageYOffset || 0;
        var dy = y - lastY;
        lastY = y;
        if (!h) h = document.querySelector('header.top');
        if (!h) return;
        if (y < 80) { h.classList.remove('is-collapsed'); accum = 0; return; }
        if (dy > 3) { accum = Math.min(accum + dy, 220); if (accum > 60) h.classList.add('is-collapsed'); }
        else if (dy < -3) { accum = Math.max(accum + dy, -220); if (accum < -30) h.classList.remove('is-collapsed'); }
      }
      window.addEventListener('scroll', function () {
        if (!raf) raf = requestAnimationFrame(tick);
      }, { passive: true });
    }());
  }

  function exportProgress() {
    var blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = '巴帝摩卡进度_' + todayStr() + '.json';
    a.click(); URL.revokeObjectURL(a.href);
  }
  function importProgress(e) {
    var f = e.target.files[0]; if (!f) return;
    var reader = new FileReader();
    reader.onload = function (ev) {
      try {
        var s = JSON.parse(ev.target.result);
        if (s && s.progress) {
          if (confirm('导入将覆盖当前进度，确定？')) { state.progress = s.progress; if (s.settings) state.settings = s.settings; save(); banner('✅ 进度已导入。', 'info'); renderDashboard(); }
        }
      } catch (err) { banner('❌ 进度文件解析失败。', 'err'); }
    };
    reader.readAsText(f, 'utf-8');
  }

  // ---------- 深度链接：#idx=NNN 直接定位到浏览视图的某条 ----------
  function gotoRuleFromHash() {
    var m = /idx=(\d+)/.exec(location.hash || '');
    if (!m) return;
    var idx = parseInt(m[1], 10);
    showView('browse');
    setTimeout(function () {
      var node = document.getElementById('rule-' + idx);
      if (!node) { banner('⚠️ 未找到第 ' + idx + ' 条（数据集已变更？）', 'err'); return; }
      var sec = node.closest('.browse-sec');
      if (sec) sec.classList.add('open');
      node.scrollIntoView({ behavior: 'smooth', block: 'center' });
      node.classList.add('rule-flash');
      setTimeout(function () { node.classList.remove('rule-flash'); }, 2600);
    }, 80);
  }
  window.addEventListener('hashchange', gotoRuleFromHash);

  document.addEventListener('DOMContentLoaded', function () { bind(); renderDashboard(); gotoRuleFromHash(); });
})();
