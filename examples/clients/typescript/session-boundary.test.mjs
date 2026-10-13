import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readSession} from './dist/session.js';

const handle = 'a'.repeat(32);
const encode = value => new TextEncoder().encode(value);
const body = profile => JSON.stringify({session: handle, source_profile: profile});
function response(bytes, stride) {
  let offset = 0;
  return new Response(new ReadableStream({pull(controller) {
    if (offset === bytes.length) controller.close();
    else {
      controller.enqueue(bytes.slice(offset, offset + stride));
      offset = Math.min(offset + stride, bytes.length);
    }
  }}));
}

test('session preserves split multibyte profiles without normalization', async () => {
  for (const profile of ['räddning-😀', 'e\u0301', 'é', '\ufffd']) {
    const reply = response(encode(body(profile)), 1);
    assert.equal(await readSession(reply, profile), handle);
    assert.equal(reply.body.locked, false);
  }
  await assert.rejects(readSession(response(encode(body('e\u0301')), 1), 'é'),
    {message: 'invalid_session'});
});

for (const [name, invalid] of [
  ['isolated continuation', [0x80]],
  ['overlong slash', [0xc0, 0xaf]],
  ['surrogate', [0xed, 0xa0, 0x80]],
  ['out of Unicode range', [0xf4, 0x90, 0x80, 0x80]],
  ['truncated scalar', [0xf0, 0x9f]],
]) {
  test(`session rejects ${name} even when replacement text matches requested profile`, async () => {
    // A nonfatal decoder would turn this into valid JSON with the same profile.
    const repaired = new TextDecoder().decode(Uint8Array.from(invalid));
    const bytes = Uint8Array.from([
      ...encode(`{"session":"${handle}","source_profile":"`),
      ...invalid, ...encode('"}'),
    ]);
    for (const stride of [1, 7, bytes.length]) {
      const reply = response(bytes, stride);
      await assert.rejects(readSession(reply, repaired), error => {
        assert.equal(error.message, 'invalid_session');
        assert.equal(error.cause, undefined);
        return true;
      });
      assert.equal(reply.body.locked, false);
    }
  });
}

for (const excess of [0, 1]) {
  test(`session accumulates fragmented multibyte byte limit with ${excess} excess`, async () => {
    const profile = 'é'.repeat(100);
    const json = body(profile);
    const bytes = encode(' '.repeat(65536 + excess - encode(json).length) + json);
    assert.equal(bytes.length, 65536 + excess);
    assert.ok(new TextDecoder().decode(bytes).length < 65536);
    const reply = response(bytes, 997);
    if (excess) await assert.rejects(readSession(reply, profile), {message: 'invalid_session'});
    else assert.equal(await readSession(reply, profile), handle);
    assert.equal(reply.body.locked, false);
  });
}

test('valid session prefix followed by a read failure never releases a handle', async () => {
  let pulls = 0;
  const reply = new Response(new ReadableStream({pull(controller) {
    if (pulls++ === 0) controller.enqueue(encode(body('bench')));
    else controller.error(new Error('private_transport_marker'));
  }}));
  await assert.rejects(readSession(reply, 'bench'), {message: 'invalid_session'});
  assert.equal(reply.body.locked, false);
});
