import validators from './validators.cjs';
import {strictObject} from './wire.js';
import type {SessionHandle} from './types.js';

// Local client response policy, not a new server limit or a network memory bound.
const MAX_SESSION_BYTES = 65536;

export async function readSession(response: Response, profile: string): Promise<string> {
  const buffer = new Uint8Array(MAX_SESSION_BYTES);
  let length = 0;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    if (!response.body) throw new Error();
    reader = response.body.getReader();
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      if (chunk.value.byteLength > MAX_SESSION_BYTES - length) throw new Error();
      buffer.set(chunk.value, length);
      length += chunk.value.byteLength;
    }
    const text = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(buffer.subarray(0, length));
    const value = strictObject(text);
    if (!validators.validateSession(value)) throw new Error();
    const session = value as SessionHandle;
    if (session.source_profile !== profile) throw new Error();
    return session.session;
  } catch {
    throw new Error('invalid_session');
  } finally {
    buffer.fill(0, 0, length);
    if (reader) {
      void reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }
}
