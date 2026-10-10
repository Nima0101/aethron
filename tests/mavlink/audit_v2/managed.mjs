// Original audit-only strict subset, GPL-3.0-only. No network or transmit API.
import { readFileSync } from 'node:fs';

const layouts = new Map([
  [30, ['ATTITUDE', 'body_euler', ['roll', 'pitch', 'yaw', 'rollspeed', 'pitchspeed', 'yawspeed'],
    ['rad', 'rad', 'rad', 'rad/s', 'rad/s', 'rad/s'], 39]],
  [32, ['LOCAL_POSITION_NED', 'local_ned_unregistered', ['x', 'y', 'z', 'vx', 'vy', 'vz'],
    ['m', 'm', 'm', 'm/s', 'm/s', 'm/s'], 185]],
]);

class Receiver {
  constructor() {
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
    if (p[5] !== 1 || p[6] !== 1) { this.withdraw('sender_mismatch'); return; }
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
    this.samples.set(id, {system_id: 1, component_id: 1, message: layout[0], frame: layout[1],
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

const raw = readFileSync(0);
if (raw.length > 65536) throw new Error('audit_input_limit');
const cases = JSON.parse(raw);
if (!Array.isArray(cases) || cases.length < 1 || cases.length > 64) {
  throw new Error('audit_case_limit');
}
const names = new Set();
for (const c of cases) {
  if (c === null || typeof c !== 'object' || Array.isArray(c) ||
      Object.keys(c).length !== 2 || !Object.hasOwn(c, 'name') || !Object.hasOwn(c, 'steps')) {
    throw new Error('audit_case_record');
  }
  if (typeof c.name !== 'string' || c.name.length === 0 || names.has(c.name)) {
    throw new Error('audit_case_name');
  }
  names.add(c.name);
  if (!Array.isArray(c.steps) || c.steps.length < 1 || c.steps.length > 64) {
    throw new Error('audit_step_limit');
  }
}
const results = cases.map(c => {
  const receiver = new Receiver();
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
    const now = typeof step.now === 'string' ? BigInt(step.now) : step.now;
    if (step.op === 'ingest') receiver.ingest(Buffer.from(step.hex, 'hex'), now);
    else if (step.op === 'close') receiver.close();
    else if (step.op !== 'snapshot') throw new Error('audit_operation');
    return receiver.snapshot(now);
  });
});
console.log(JSON.stringify({results, peak_rss_kib: process.resourceUsage().maxRSS,
  runtime: process.version}, (_, value) => typeof value === 'bigint' ? value.toString() : value));
