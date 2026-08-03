// 打印指定 idx 区间 rule 的完整 JSON, 以及 sections 概要
const fs = require('fs'), vm = require('vm'), path = require('path');
const APP = __dirname;
const ctx = { window: {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(APP, 'data.js'), 'utf8'), ctx);
const D = ctx.window.PATIMOKKHA_DATA;
const a = parseInt(process.argv[2], 10), b = parseInt(process.argv[3], 10);
console.log('ruleCount=', D.meta && D.meta.ruleCount, ' rules.length=', D.rules.length,
  ' sectionCount=', D.meta && D.meta.sectionCount, ' sections.length=', D.sections.length);
for (let i = a; i <= b && i < D.rules.length; i++) {
  console.log('--- idx ' + i + ' ---');
  console.log(JSON.stringify(D.rules[i], null, 1));
}
console.log('=== sections ===');
D.sections.forEach((s, k) => console.log(k, JSON.stringify({ order: s.order, title: s.title, ruleStart: s.ruleStart, ruleEnd: s.ruleEnd })));
