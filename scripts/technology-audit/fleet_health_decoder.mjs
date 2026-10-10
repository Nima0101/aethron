// Audit-only flat JSON decoder prototype; no collector, transport or production API.
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

const fields = ['version', 'state', 'emitted_ms', 'status_expires_ms'];
const states = ['running', 'recovering', 'fault', 'stopped'];
const utf8 = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
function valid(value) {
  return value !== null && !Array.isArray(value) && typeof value === 'object'
    && Object.keys(value).length === 4 && fields.every(key => Object.hasOwn(value, key))
    && value.version === 1 && states.includes(value.state)
    && Number.isSafeInteger(value.emitted_ms) && value.emitted_ms >= 0
    && Number.isSafeInteger(value.status_expires_ms) && value.status_expires_ms >= 0
    && value.emitted_ms <= 1000 && 1000 < value.status_expires_ms
    && value.status_expires_ms - value.emitted_ms <= 2000;
}

function decode(raw, strict) {
  if (raw.length > 256) return false;
  try {
    const text = utf8.decode(raw);
    if (!strict) return valid(JSON.parse(text));
    // Preserve duplicate keys and integer token types before creating an object.
    // Flat scalar grammar is sufficient ONLY for the four-field health schema.
    const token = /"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"|-?(?:0|[1-9][0-9]*)/y;
    const whitespace = /[ \t\r\n]*/y;
    let position = 0;
    function space() {
      whitespace.lastIndex = position;
      whitespace.exec(text);
      position = whitespace.lastIndex;
    }
    function character(expected) {
      space();
      if (text[position++] !== expected) throw new Error('invalid');
    }
    function scalar() {
      space();
      token.lastIndex = position;
      const match = token.exec(text);
      if (match === null) throw new Error('invalid');
      position = token.lastIndex;
      return JSON.parse(match[0]);
    }
    character('{');
    const value = Object.create(null);
    for (let index = 0; index < 4; index++) {
      if (index) character(',');
      const key = scalar();
      if (typeof key !== 'string' || Object.hasOwn(value, key)) return false;
      character(':');
      value[key] = scalar();
    }
    character('}');
    space();
    return position === text.length && valid(value);
  } catch {
    return false;
  }
}

const cases = JSON.parse(readFileSync(0, 'utf8')).map(hex => Buffer.from(hex, 'hex'));
const strictResults = cases.map(raw => decode(raw, true));
const defaultResults = cases.map(raw => decode(raw, false));
const samples = [];
for (let sample = 0; sample < 5; sample++) {
  const start = performance.now();
  for (let iteration = 0; iteration < 2000; iteration++) {
    if (!decode(cases[0], true)) throw new Error('valid_report_rejected');
  }
  samples.push((performance.now() - start) * 1000 / 2000);
}
const sorted = [...samples].sort((a, b) => a - b);
console.log(JSON.stringify({
  node: process.version, strict_results: strictResults, default_results: defaultResults,
  peak_rss_kib: process.resourceUsage().maxRSS,
  timing: { unit: 'microseconds', iterations_per_sample: 2000, samples,
    median: sorted[2], max_sample: sorted[4] }
}));
