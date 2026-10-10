// Audit prototype only: validated layout supplied by the Python harness.
// Persistent synchronous worker, no network, device access or semantic inference.
'use strict';
const fs = require('node:fs');
const s = JSON.parse(process.argv[2]);
const fields = ['x', 'y', 'z', 'radial_velocity'].map(n => s.fields.find(f => f.name === n));
const input = Buffer.alloc(s.row_step * s.height);
const readers = fields.map(f => !f ? null : {
  offset: f.offset,
  read: input[`read${f.datatype === 7 ? 'Float' : 'Double'}${s.is_bigendian ? 'BE' : 'LE'}`].bind(input)
});
function readAll() {
  let offset = 0;
  while (offset < input.length) {
    const n = fs.readSync(0, input, offset, input.length - offset, null);
    if (!n) { if (offset) throw Error('truncated'); return false; }
    offset += n;
  }
  return true;
}
fs.writeSync(1, Buffer.from([1]));
while (readAll()) {
  const cpuStart = process.cpuUsage();
  const output = Buffer.alloc(s.width * s.height * 33 + 8);
  let ordinal = 0;
  for (let y = 0; y < s.height; y++) for (let x = 0; x < s.width; x++) {
    const start = y * s.row_step + x * s.point_step;
    const values = readers.map(f => !f ? 0 : f.read(start + f.offset));
    const valid = values.every(Number.isFinite);
    output[8 + ordinal * 33] = Number(valid);
    for (let i = 0; i < 4; i++) output.writeDoubleLE(valid ? values[i] : 0, 8 + ordinal * 33 + 1 + i * 8);
    ordinal++;
  }
  const cpu = process.cpuUsage(cpuStart);
  output.writeDoubleLE((cpu.user + cpu.system) / 1000, 0);
  let written = 0;
  while (written < output.length) written += fs.writeSync(1, output, written, output.length - written);
}
