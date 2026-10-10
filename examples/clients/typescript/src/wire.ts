const LIMIT = 65536;

/** Preflight duplicate decoded keys and depth before native JSON parsing.
 * JSON.parse remains responsible for the complete JSON grammar. */
function strictObject(text: string): unknown {
  const stack: {object: boolean; key: boolean; keys: Set<string>}[] = [];
  try {
    for (let i = 0; i < text.length; i++) {
      const character = text[i];
      if (character === '"') {
        const start = i++;
        while (i < text.length && text[i] !== '"') {
          if (text[i] === '\\') i++;
          i++;
        }
        if (i >= text.length) throw new Error();
        const scope = stack.at(-1);
        if (scope?.object && scope.key) {
          const key: string = JSON.parse(text.slice(start, i + 1));
          if (scope.keys.has(key)) throw new Error();
          scope.keys.add(key); scope.key = false;
        }
      } else if (character === '{' || character === '[') {
        if (stack.length >= 8) throw new Error();
        stack.push({object: character === '{', key: true, keys: new Set()});
      } else if (character === '}' || character === ']') {
        const scope = stack.pop();
        if (!scope || scope.object !== (character === '}')) throw new Error();
      } else if (character === ',') {
        const scope = stack.at(-1);
        if (scope?.object) scope.key = true;
      }
    }
    const result: unknown = JSON.parse(text);
    if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error();
    return result;
  } catch { throw new Error('invalid_event'); }
}

/** AETHRON API-v1 profile: LF/CRLF fields, one bounded JSON object per event.
 * No retry/history interpretation and no general EventSource implementation. */
export class WireDecoder {
  #buffer = new Uint8Array(LIMIT);
  #length = 0;
  #lineStart = 0;
  #utf8 = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true});

  *feed(chunk: Uint8Array): Generator<{name: string | undefined; value: unknown}> {
    for (const byte of chunk) {
      if (this.#length === LIMIT) throw new Error('event_limit');
      this.#buffer[this.#length++] = byte;
      if (byte !== 10) continue;
      let end = this.#length - 1;
      if (end > this.#lineStart && this.#buffer[end - 1] === 13) end--;
      if (end !== this.#lineStart) { this.#lineStart = this.#length; continue; }
      let text: string;
      try { text = this.#utf8.decode(this.#buffer.subarray(0, this.#length)); }
      catch { throw new Error('invalid_event'); }
      this.clear();
      const data: string[] = [];
      let name: string | undefined;
      for (const line of text.split(/\r?\n/)) {
        if (line.includes('\r')) throw new Error('invalid_event');
        if (!line || line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        if (colon < 0) throw new Error('invalid_event');
        const field = line.slice(0, colon);
        const value = line.slice(colon + 1).replace(/^ /, '');
        if (field === 'data') data.push(value);
        else if (field === 'event' && name === undefined && /^(scene|health|gap)$/.test(value)) name = value;
        else throw new Error('invalid_event');
      }
      if (!data.length) {
        if (name !== undefined) throw new Error('invalid_event');
        continue; // Bounded comment/blank heartbeat; cannot refresh a lease.
      }
      yield {name, value: strictObject(data.join('\n'))};
    }
  }

  finish(): void { if (this.#length) throw new Error('invalid_event'); }
  clear(): void {
    this.#buffer.fill(0, 0, this.#length);
    this.#length = 0; this.#lineStart = 0;
  }
}
