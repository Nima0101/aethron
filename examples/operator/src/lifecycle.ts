import {mountObservationPanel} from './panel.js';
import {presentObservation, type Locale} from './presenter.js';

/** A host-owned SDK Observation or equivalent fresh, revocable view source.
 * This interface does not authenticate sources or establish transport freshness. */
export interface ObservationSource {
  view(): unknown;
  disconnect(): void;
}

/** Owns display scheduling only. The caller still owns ingress and authorization. */
export function mountObservationHost(root: HTMLElement, source: ObservationSource, locale: Locale = 'en',
  requestLocale?: (locale: Locale) => void) {
  presentObservation(null, locale); // Validate before mutating the host or source.
  const document = root.ownerDocument;
  const window = document.defaultView;
  if (!window) throw new Error('unsupported_host');
  if (!source || typeof source.view !== 'function' || typeof source.disconnect !== 'function') {
    throw new Error('invalid_source');
  }
  let disposed = false, active = false, failed = false, clearing = false;
  let epoch: object = {};
  let timer: number | undefined;
  const expired = () => ({label:'expired',current_state:'UNKNOWN',observed_state:'UNKNOWN',sources:[],uncertainty:[]});
  const visible = () => document.visibilityState === 'visible';
  const panel = mountObservationPanel(root, () => {
    if (failed) return null;
    if (disposed || !active || !visible()) return expired();
    const ticket = epoch;
    const view = source.view();
    return disposed || !active || !visible() || epoch !== ticket ? expired() : view;
  }, locale, requestLocale);

  function stopTimer(): void {
    const previous = timer; timer = undefined;
    if (previous !== undefined) window!.clearInterval(previous);
  }
  function reset(activate: boolean): void {
    if (disposed) return;
    active = false;
    const ticket = {}; epoch = ticket;
    stopTimer();
    // A reentrant reset cannot recursively invoke an arbitrary source clearer.
    if (clearing) { failed = true; panel.refresh(); return; }
    clearing = true;
    try { source.disconnect(); }
    catch { failed = true; }
    finally { clearing = false; }
    if (disposed || epoch !== ticket) return;
    active = activate && !failed && visible();
    if (active) {
      try { timer = window!.setInterval(refresh, 20); }
      catch { active = false; failed = true; }
    }
    panel.refresh();
  }
  function refresh(): void {
    if (disposed) return;
    if (active && !visible()) reset(false);
    else panel.refresh();
  }
  const onVisibility = () => reset(visible());
  const suspend = () => reset(false);
  const resume = () => reset(true);
  const events: [EventTarget, string, () => void][] = [
    [document,'visibilitychange',onVisibility], [document,'freeze',suspend],
    [document,'resume',resume], [window,'pagehide',suspend], [window,'pageshow',resume],
  ];
  function dispose(): void {
    if (disposed) return;
    disposed = true; active = false; epoch = {};
    stopTimer();
    for (const [target,name,callback] of events) target.removeEventListener(name,callback);
    try { if (!clearing) source.disconnect(); }
    catch { /* Disposal must still withdraw the local display. */ }
    finally { panel.dispose(); }
  }
  for (const [target,name,callback] of events) target.addEventListener(name,callback);
  reset(visible());
  return {refresh, setLocale: panel.setLocale, dispose};
}
