import validators from './validators.cjs';
import {WireDecoder} from './wire.js';
import {readSession} from './session.js';
import type {HealthEvent, SceneEnvelope} from './types.js';

const {validateScene: validate, validateHealth} = validators;

function localNow(): number {
  // A host clock failure must reach the same clearing path as an invalid sample.
  try { return performance.now(); }
  catch { return NaN; }
}

function discardResponse(response: Response): void {
  // Do not drain untrusted bodies or wait for an underlying cleanup promise.
  void response.body?.cancel().catch(() => {});
}

export class Observation {
  // Retain only the displayed aggregate, never the transport handle or track IDs.
  #projection: {
    validForMs: number;
    observedState: SceneEnvelope['result']['state'];
    sources: SceneEnvelope['result']['tracks'][number]['sources'];
    uncertainty: number[][];
  } | null = null;
  #received = 0;
  #lastViewed = 0;

  accept(value: unknown, now = localNow()): void {
    this.disconnect();
    if (!Number.isFinite(now) || now < 0) throw new Error('invalid_clock');
    // Validate an owned snapshot: callers must not mutate an admitted lease.
    let snapshot: unknown;
    try {
      snapshot = structuredClone(value);
      if (!validate(snapshot)) throw new Error('invalid_event');
    } catch {
      // structuredClone can invoke input getters, including reentrant callers.
      this.disconnect();
      throw new Error('invalid_event');
    }
    const scene = snapshot as SceneEnvelope;
    this.#projection = {
      validForMs: scene.clock.valid_for_ms, observedState: scene.result.state,
      sources: [...new Set(scene.result.tracks.flatMap(t => t.sources))],
      uncertainty: scene.result.tracks.map(t => [...t.covariance]),
    };
    this.#received = now;
    this.#lastViewed = now;
  }

  disconnect(): void { this.#projection = null; this.#received = 0; this.#lastViewed = 0; }

  view(now = localNow()) {
    if (!this.#projection || !Number.isFinite(now) || now < 0 || now < this.#lastViewed ||
        now - this.#received > this.#projection.validForMs) {
      this.disconnect();
      return {label: 'expired', current_state: 'UNKNOWN', observed_state: 'UNKNOWN', sources: [], uncertainty: []};
    }
    this.#lastViewed = now;
    return {label: 'delayed_observation', current_state: 'UNKNOWN', observed_state: this.#projection.observedState,
      sources: [...this.#projection.sources],
      uncertainty: this.#projection.uncertainty.map(covariance => [...covariance])};
  }
}

/** Authenticated fetch streaming; credentials never enter URLs or persistent storage. */
export async function observe(base: string, token: string, profile: string,
  display: (state: ReturnType<Observation['view']>) => void, signal: AbortSignal): Promise<void> {
  const headers = {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'};
  const request = await fetch(`${base}/api/v1/sessions`, {method: 'POST', headers, redirect: 'error',
    body: JSON.stringify({source_profile: profile, contract: 'warn'}), signal});
  if (!request.ok) {
    discardResponse(request);
    throw new Error('session_unavailable');
  }
  const handle = await readSession(request, profile);
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
    const response = await fetch(`${base}/api/v1/sessions/${handle}/events`, {headers, signal: eventSignal, redirect: 'error'});
    if (!response.ok || !response.body) {
      discardResponse(response);
      throw new Error('stream_unavailable');
    }
    const reader = response.body.getReader();
    const decoder = new WireDecoder();
    let lastSequence = -1;
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) { decoder.finish(); break; }
        for (const {name, value: message} of decoder.feed(chunk.value)) {
          const incoming = message as SceneEnvelope | HealthEvent;
          if ((!validate(message) && !validateHealth(message)) ||
              incoming.session !== handle || incoming.sequence <= lastSequence ||
              (name !== undefined && name !== incoming.kind)) {
            value.disconnect();
            throw new Error('invalid_event');
          }
          lastSequence = incoming.sequence;
          if (incoming.kind === 'scene') value.accept(incoming);
          else value.disconnect();
          display(value.view());
        }
      }
    } finally {
      value.disconnect(); decoder.clear(); stop.abort();
      // Source cleanup can remain pending after the stream closes. Do not let
      // it hold session deletion or replace the primary admission/render error.
      void reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    if (renderFailed) throw renderError;
  } catch (error) {
    // Surface the renderer failure through the observer promise, not the timer.
    throw renderFailed ? renderError : error;
  } finally {
    clearInterval(timer); stop.abort(); value.disconnect();
    try { if (!renderFailed) display(value.view()); }
    finally {
      await fetch(`${base}/api/v1/sessions/${handle}`, {method: 'DELETE', headers, signal: AbortSignal.timeout(2000), redirect: 'error'})
        .then(discardResponse).catch(() => {});
    }
  }
}
