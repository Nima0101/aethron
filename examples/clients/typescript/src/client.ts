import {Ajv2020} from 'ajv/dist/2020.js';
import schema from './scene.schema.json' with {type: 'json'};
import type {SceneEnvelope} from './types.js';

const validate = new Ajv2020({strict: true}).compile(schema);

export class Observation {
  private scene: SceneEnvelope | null = null;
  private received = 0;

  accept(value: unknown, now = performance.now()): void {
    this.disconnect();
    if (!validate(value)) throw new Error('invalid_event');
    this.scene = value as SceneEnvelope;
    this.received = now;
  }

  disconnect(): void { this.scene = null; }

  view(now = performance.now()) {
    if (!this.scene || now < this.received || now - this.received > this.scene.clock.valid_for_ms) {
      this.disconnect();
      return {label: 'expired', current_state: 'UNKNOWN', observed_state: 'UNKNOWN', sources: [], uncertainty: []};
    }
    return {label: 'delayed_observation', current_state: 'UNKNOWN', observed_state: this.scene.result.state,
      sources: [...new Set(this.scene.result.tracks.flatMap(t => t.sources))],
      uncertainty: this.scene.result.tracks.map(t => t.covariance)};
  }
}

/** Authenticated fetch streaming; credentials never enter URLs or persistent storage. */
export async function observe(base: string, token: string, profile: string,
  display: (state: ReturnType<Observation['view']>) => void, signal: AbortSignal): Promise<void> {
  const headers = {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'};
  const request = await fetch(`${base}/api/v1/sessions`, {method: 'POST', headers,
    body: JSON.stringify({source_profile: profile, contract: 'warn'}), signal});
  if (!request.ok) throw new Error('session_unavailable');
  const handle: unknown = (await request.json()).session;
  if (typeof handle !== 'string' || !/^[a-f0-9]{32}$/.test(handle)) throw new Error('invalid_session');
  const value = new Observation();
  // Independent render-time expiry, including a stalled response with no next frame.
  const timer = setInterval(() => display(value.view()), 20);
  try {
    const response = await fetch(`${base}/api/v1/sessions/${handle}/events`, {headers, signal});
    if (!response.ok || !response.body) throw new Error('stream_unavailable');
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8', {fatal: true});
    let pending = '';
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        pending += decoder.decode(chunk.value, {stream: true});
        if (pending.length > 65536) throw new Error('event_limit');
        let index: number;
        while ((index = pending.indexOf('\n\n')) >= 0) {
          const event = pending.slice(0, index); pending = pending.slice(index + 2);
          const data = event.split('\n').find(line => line.startsWith('data: '));
          if (!data) throw new Error('invalid_event');
          const message: unknown = JSON.parse(data.slice(6));
          if ((message as {kind?: string})?.kind === 'scene') value.accept(message);
          else value.disconnect();
          display(value.view());
        }
      }
    } finally { await reader.cancel(); }
  } finally {
    clearInterval(timer); value.disconnect(); display(value.view());
    await fetch(`${base}/api/v1/sessions/${handle}`, {method: 'DELETE', headers, signal: AbortSignal.timeout(2000)}).catch(() => {});
  }
}
