const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const data = sandbox.window.PM_PALI_WORDS;
fs.writeFileSync(process.argv[3], JSON.stringify(data));
console.log('OK', Object.keys(data).length, 'keys');