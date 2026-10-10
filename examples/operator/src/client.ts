import {mountConnectionControls} from './connection.js';
import {mountObservationHost, type ObservationSource} from './lifecycle.js';
import {presentObservation, type Locale} from './presenter.js';

/** Host-authorized read-only session. start covers reception AND cleanup; the
 * adapter must honor cancellation and exclusively own its source. */
export interface ObservationSession extends ObservationSource {
  start(signal: AbortSignal): Promise<void>;
}

/** One display/connection lifetime and locale. UI availability is not authority;
 * the host and service must enforce actual access. No credentials or storage. */
export function mountObservationClient(root: HTMLElement, session: ObservationSession, locale: Locale = 'en') {
  presentObservation(null, locale);
  if (!session || typeof session.view !== 'function' || typeof session.disconnect !== 'function' ||
      typeof session.start !== 'function') throw new Error('invalid_session_adapter');
  if (!root.ownerDocument.defaultView) throw new Error('unsupported_host');
  const container = root.ownerDocument.createElement('div');
  const observationRoot = root.ownerDocument.createElement('div');
  const connectionRoot = root.ownerDocument.createElement('div');
  container.append(observationRoot, connectionRoot);root.replaceChildren(container);
  let disposed = false, enabled = false, observing = false;
  let epoch: object = {};
  let host: ReturnType<typeof mountObservationHost> | undefined;
  let controls: ReturnType<typeof mountConnectionControls> | undefined;
  const expired = () => ({label:'expired',current_state:'UNKNOWN',observed_state:'UNKNOWN',sources:[],uncertainty:[]});
  function disconnect(): void {
    observing = false;epoch = {};
    try {session.disconnect();}
    finally {host?.refresh();}
  }
  function setLocale(next: Locale): void {
    if (disposed) return;
    presentObservation(null, next);
    controls?.setLocale(next);host?.setLocale(next);
  }
  function dispose(): void {
    if (disposed) return;
    disposed = true;enabled = false;observing = false;epoch = {};
    try {controls?.dispose();}
    finally {try {host?.dispose();} finally {container.remove();}}
  }
  try {
    host = mountObservationHost(observationRoot, {
      view() {
        if (disposed || !enabled || !observing) return expired();
        const ticket = epoch, value = session.view();
        return disposed || !enabled || !observing || epoch !== ticket ? expired() : value;
      }, disconnect,
    }, locale, setLocale);
    controls = mountConnectionControls(connectionRoot, {
      start(signal) {
        if (disposed || !enabled || signal.aborted) throw new Error('session_unavailable');
        observing = true;epoch = {};
        return session.start(signal);
      }, disconnect,
    }, locale);
  } catch {
    dispose();throw new Error('client_unavailable');
  }
  function setEnabled(next: boolean): void {
    if (disposed) return;
    if (typeof next !== 'boolean') throw new Error('invalid_permission');
    enabled = next;controls!.setEnabled(next);
  }
  return {setEnabled, setLocale, dispose};
}
