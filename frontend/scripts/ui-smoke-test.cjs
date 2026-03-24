const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '..', 'src', 'components', 'ChatInterface.tsx');

if (!fs.existsSync(filePath)) {
  console.error('Missing ChatInterface.tsx:', filePath);
  process.exit(1);
}

const contents = fs.readFileSync(filePath, 'utf8');

const required = [
  'Executive Summary',
  'Export PDF',
  'Copy report',
  'api.getSummary',
];

const missing = required.filter((k) => !contents.includes(k));
if (missing.length) {
  console.error('UI smoke test missing tokens:', missing.join(', '));
  process.exit(1);
}

console.log('UI smoke test passed.');
