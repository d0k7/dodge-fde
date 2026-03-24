const fs = require('fs');
const path = require('path');

const typesPath = path.join(__dirname, '..', 'src', 'types', 'index.ts');

if (!fs.existsSync(typesPath)) {
  console.error('Missing types file:', typesPath);
  process.exit(1);
}

const contents = fs.readFileSync(typesPath, 'utf8');

const required = [
  'interface AnalyticsSummary',
  'top_products_revenue',
  'top_countries',
  'top_regions',
  'top_plants',
];

const missing = required.filter((k) => !contents.includes(k));
if (missing.length) {
  console.error('Missing AnalyticsSummary fields:', missing.join(', '));
  process.exit(1);
}

console.log('Frontend smoke test passed.');
