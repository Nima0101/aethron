import {Ajv2020} from 'ajv/dist/2020.js';
import schema from './scene.schema.json' with {type: 'json'};
import type {HealthEvent, SceneEnvelope} from './types.js';

const validator = new Ajv2020({strict: true});
const validate = validator.compile(schema);
const validateHealth = validator.compile({...schema, $ref: '#/$defs/HealthEvent'});

export class Observation {
  private scene: SceneEnvelope | null = null;
  private received = 0;
  private lastViewed = 0;

  accept(value: unknown, now = performance.now()): void {
    this.disconnect();
    if (!Number.isFinite(now) || now < 0) throw new Error('invalid_clock');
    // Validate an owned snapshot: callers must not mutate an admitted lease.
    let snapshot: unknown;
    try { snapshot = structuredClone(value); }
    catch { throw new Error('invalid_event'); }
    if (!validate(snapshot)) throw new Error('invalid_event');
    this.scene = snapshot as SceneEnvelope;
    this.received = now;
    this.lastViewed = now;
  }

  disconnect(): void { this.scene = null; }

  view(now = performance.now()) {
    if (!this.scene || !Number.isFinite(now) || now < 0 || now < this.lastViewed ||
        now - this.received > this.scene.clock.valid_for_ms) {
      this.disconnect();
      return {label: 'expired', current_state: 'UNKNOWN', observed_state: 'UNKNOWN', sources: [], uncertainty: []};
    }
    this.lastViewed = now;
    return {label: 'delayed_observation', current_state: 'UNKNOWN', observed_state: this.scene.result.state,
      sources: [...new Set(this.scene.result.tracks.flatMap(t => t.sources))],
      uncertainty: this.scene.result.tracks.map(t => [...t.covariance])};
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
  const stop = new AbortController();
  const eventSignal = AbortSignal.any([signal, stop.signal]);
  let renderFailed = false;
  let renderError: unknown;
  // Independent render-time expiry, including a stalled response with no next frame.
  const timer = setInterval(() => {
    if (renderFailed) return;
    try { display(value.view()); }
    catch (error) {
      renderFailed = true; renderError = error;
      value.disconnect(); stop.abort();
    }
  }, 20);
  try {
    const response = await fetch(`${base}/api/v1/sessions/${handle}/events`, {headers, signal: eventSignal});
    if (!response.ok || !response.body) throw new Error('stream_unavailable');
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8', {fatal: true});
    let pending = '';
    let lastSequence = -1;
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
          const incoming = message as SceneEnvelope | HealthEvent;
          if ((!validate(message) && !validateHealth(message)) ||
              incoming.session !== handle || incoming.sequence <= lastSequence) {
            value.disconnect();
            throw new Error('invalid_event');
          }
          lastSequence = incoming.sequence;
          if (incoming.kind === 'scene') value.accept(incoming);
          else value.disconnect();
          display(value.view());
        }
      }
    } finally { await reader.cancel(); }
    if (renderFailed) throw renderError;
  } catch (error) {
    // Surface the renderer failure through the observer promise, not the timer.
    throw renderFailed ? renderError : error;
  } finally {
    clearInterval(timer); stop.abort(); value.disconnect();
    try { if (!renderFailed) display(value.view()); }
    finally {
      await fetch(`${base}/api/v1/sessions/${handle}`, {method: 'DELETE', headers, signal: AbortSignal.timeout(2000)}).catch(() => {});
    }
  }
}
