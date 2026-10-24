// Original audit-only strict subset, GPL-3.0-only. No network or transmit API.
import { readSync } from 'node:fs';
import { TextDecoder } from 'node:util';

const layouts = new Map([
  [30, ['ATTITUDE', 'body_euler', ['roll', 'pitch', 'yaw', 'rollspeed', 'pitchspeed', 'yawspeed'],
    ['rad', 'rad', 'rad', 'rad/s', 'rad/s', 'rad/s'], 39]],
  [32, ['LOCAL_POSITION_NED', 'local_ned_unregistered', ['x', 'y', 'z', 'vx', 'vy', 'vz'],
    ['m', 'm', 'm', 'm/s', 'm/s', 'm/s'], 185]],
]);

class Receiver {
  constructor(system, component) {
    this.system = system; this.component = component;
    this.last = null; this.sequence = null; this.boot = new Map(); this.samples = new Map();
    this.reason = 'no_observation'; this.latched = false;
  }
  withdraw(reason, latch = false) {
    this.samples.clear(); this.reason = reason; this.latched ||= latch;
  }
  clock(now) {
    if (this.latched) return false;
    if (typeof now !== 'bigint' || now < 0n || (this.last !== null && now < this.last)) {
      this.withdraw('local_clock_invalid', true); return false;
    }
    this.last = now; return true;
  }
  ingest(p, now) {
    if (!this.clock(now)) return;
    if (!Buffer.isBuffer(p) || p.length < 12 || p.length > 280) {
      this.withdraw('invalid_packet'); return;
    }
    if (p[0] !== 253 || p[2] !== 0 || p[3] !== 0) {
      this.withdraw('unsupported_packet'); return;
    }
    if (p.length !== p[1] + 12) { this.withdraw('invalid_packet'); return; }
    const id = p.readUIntLE(7, 3), layout = layouts.get(id);
    if (!layout) { this.withdraw('unsupported_message'); return; }
    if (p[1] < 1 || p[1] > 28) { this.withdraw('invalid_packet'); return; }
    if (p[5] !== this.system || p[6] !== this.component) { this.withdraw('sender_mismatch'); return; }
    let crc = 65535;
    for (const byte of [...p.subarray(1, -2), layout[4]]) {
      let tmp = byte ^ (crc & 255);
      tmp ^= (tmp << 4) & 255;
      crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 65535;
    }
    if (crc !== p.readUInt16LE(p.length - 2)) { this.withdraw('invalid_packet'); return; }
    const payload = Buffer.alloc(28);
    p.copy(payload, 0, 10, p.length - 2);
    const values = Array.from({length: 6}, (_, i) => payload.readFloatLE(4 + i * 4));
    if (!values.every(Number.isFinite)) { this.withdraw('invalid_values'); return; }
    const seq = p[4], boot = payload.readUInt32LE(0);
    const delta = this.sequence === null ? 1 : (seq - this.sequence + 256) % 256;
    if (delta < 1 || delta > 127) { this.withdraw('packet_order'); return; }
    if (this.boot.has(id) && boot <= this.boot.get(id)) {
      this.withdraw('source_clock_reset', true); return;
    }
    this.sequence = seq; this.boot.set(id, boot);
    this.samples.set(id, {system_id: this.system, component_id: this.component, message: layout[0], frame: layout[1],
      fields: layout[2], values, units: layout[3], source_boot_ms: boot, receive_ns: now,
      capture_ns: null, evidence: 'external_unverified', authenticated: false,
      link_id: null, signature_timestamp: null});
    this.reason = 'unmapped_source_clock';
  }
  snapshot(now) {
    if (this.clock(now)) {
      let stale = false;
      for (const [id, sample] of this.samples) {
        if (now - sample.receive_ns > 100000000n) { this.samples.delete(id); stale = true; }
      }
      if (stale && !this.samples.size) this.reason = 'receive_expired';
    }
    return {state: this.samples.size ? 'OBSERVED_UNVERIFIED' : 'UNKNOWN', reason: this.reason,
      samples: [...this.samples.entries()].sort((a, b) => a[0] - b[0]).map(([, sample]) => sample),
      perception_eligible: false};
  }
  close() {
    this.withdraw('closed', true); this.boot.clear(); this.sequence = null;
  }
}

// One bounded input buffer, including an over-limit sentinel; tolerate short reads.
const raw = Buffer.alloc(65537);
let used = 0;
while (true) {
  const count = readSync(0, raw, used, raw.length - used, null);
  if (count === 0) break;
  used += count;
  if (used > 65536) throw new Error('audit_input_limit');
}
// Preserve a BOM for JSON rejection, and never substitute malformed UTF-8.
const decoder = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true});
const text = decoder.decode(raw.subarray(0, used));
const cases = JSON.parse(text);
// JSON numbers in this grammar are unsigned integer configuration only. Preserve
// token distinctions (1.0 / 1e0 / -0) that JavaScript Number would otherwise erase.
for (const [token] of text.matchAll(/"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g)) {
  if (!token.startsWith('"') && !/^(0|[1-9][0-9]*)$/.test(token)) {
    throw new Error('audit_integer_token');
  }
}
// JSON.parse establishes valid grammar but discards duplicate members. Scan
// the original bounded text before using the result. Whole string tokens hide
// their punctuation; each colon follows a key string in the validated grammar.
const scopes = [];
let stringToken;
for (const [token] of text.matchAll(/"(?:[^"\\]|\\.)*"|[{}\[\]:]/g)) {
  if (token === '{') scopes.push(new Set());
  else if (token === '[') scopes.push(null);
  else if (token === '}' || token === ']') scopes.pop();
  else if (token === ':') {
    const key = JSON.parse(stringToken);
    const members = scopes.at(-1);
    if (members.has(key)) throw new Error('audit_duplicate_member');
    members.add(key);
  } else stringToken = token;
}
if (!Array.isArray(cases) || cases.length < 1 || cases.length > 64) {
  throw new Error('audit_case_limit');
}
function sender(c) {
  if (c === null || typeof c !== 'object' || Array.isArray(c)) {
    throw new Error('audit_case_record');
  }
  const fields = Object.hasOwn(c, 'version') ? ['version', 'name', 'sender', 'steps'] : ['name', 'steps'];
  if (Object.keys(c).length !== fields.length || !fields.every(k => Object.hasOwn(c, k))) {
    throw new Error('audit_case_record');
  }
  if (fields.length === 2) return [1, 1];
  if (c.version !== 4) throw new Error('audit_case_version');
  const s = c.sender;
  if (s === null || typeof s !== 'object' || Array.isArray(s) || Object.keys(s).length !== 2 ||
      !Object.hasOwn(s, 'system') || !Object.hasOwn(s, 'component')) {
    throw new Error('audit_sender_record');
  }
  const ids = [s.system, s.component];
  if (!ids.every(v => Number.isInteger(v) && v >= 1 && v <= 255)) {
    throw new Error('audit_sender_domain');
  }
  return ids;
}
const names = new Set();
for (const c of cases) {
  sender(c);
  if (typeof c.name !== 'string' || c.name.length === 0 || names.has(c.name)) {
    throw new Error('audit_case_name');
  }
  names.add(c.name);
  if (!Array.isArray(c.steps) || c.steps.length < 1 || c.steps.length > 64) {
    throw new Error('audit_step_limit');
  }
}
const results = cases.map(c => {
  const receiver = new Receiver(...sender(c));
  return c.steps.map(step => {
    if (step === null || typeof step !== 'object' || Array.isArray(step)) {
      throw new Error('audit_operation_record');
    }
    if (!['ingest', 'snapshot', 'close'].includes(step.op)) throw new Error('audit_operation');
    const fields = step.op === 'ingest' ? ['op', 'now', 'hex'] : ['op', 'now'];
    const keys = Object.keys(step);
    if (keys.length !== fields.length || !fields.every(key => Object.hasOwn(step, key))) {
      throw new Error('audit_operation_record');
    }
    if (typeof step.now !== 'boolean' &&
        (typeof step.now !== 'string' || step.now.length < 1 || step.now.length > 39 ||
         /[^0-9]/.test(step.now) || BigInt(step.now) >= (1n << 128n))) {
      throw new Error('audit_clock_domain');
    }
    if (step.op === 'ingest' &&
        (typeof step.hex !== 'string' || step.hex.length > 640 || step.hex.length % 2 !== 0 ||
         /[^0-9a-fA-F]/.test(step.hex))) {
      throw new Error('audit_packet_domain');
    }
    const now = typeof step.now === 'string' ? BigInt(step.now) : step.now;
    if (step.op === 'ingest') receiver.ingest(Buffer.from(step.hex, 'hex'), now);
    else if (step.op === 'close') receiver.close();
    else if (step.op !== 'snapshot') throw new Error('audit_operation');
    return receiver.snapshot(now);
  });
});
console.log(JSON.stringify({results, peak_rss_kib: process.resourceUsage().maxRSS,
  runtime: process.version}, (_, value) => typeof value === 'bigint' ? value.toString() : value));
