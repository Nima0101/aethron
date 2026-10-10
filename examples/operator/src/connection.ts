import type {Locale} from './presenter.js';

/** Trusted host adapter. start settles only after the session and cleanup finish.
 * disconnect must synchronously withdraw its source and refresh any display.
 * This UI gate is not authentication or server authorization. */
export interface ConnectionOperation {
  start(signal: AbortSignal): Promise<void>;
  disconnect(): void;
}
type State = 'unavailable' | 'paused' | 'idle' | 'requested' | 'stopping' | 'stopped' | 'failed';
const copy = {
  en: {
    title:'Observation connection', start:'Start', stop:'Stop', help:'Connection help',
    unavailable:['Connection unavailable','The application has not enabled this connection. Check your access with the administrator.'],
    paused:['Connection paused','Return to this page before starting. Returning does not restart a session.'],
    idle:['Ready to request observations','Start requests a session through the application. It does not establish sensor freshness or current conditions.'],
    requested:['Observation session requested','The request is in progress. Read the observation panel for data availability. Stop withdraws the local observation.'],
    stopping:['Stopping the session','The local observation was withdrawn. Wait for cleanup to finish before starting another session.'],
    stopped:['Session ended','No automatic restart is performed. Select Start for a new request when access is enabled.'],
    failed:['Connection unavailable','The operation could not complete. Check application and service status. If Start remains disabled, close and reopen this view.'],
  },
  'sv-SE': {
    title:'Observationsanslutning', start:'Starta', stop:'Stoppa', help:'Anslutningshjälp',
    unavailable:['Anslutningen är inte tillgänglig','Programmet har inte aktiverat anslutningen. Kontrollera din behörighet med administratören.'],
    paused:['Anslutningen är pausad','Återgå till denna sida innan du startar. Återgång startar inte om en session.'],
    idle:['Redo att begära observationer','Starta begär en session via programmet. Det fastställer inte sensoruppgifternas aktualitet eller aktuella förhållanden.'],
    requested:['Observationssession begärd','Begäran pågår. Se observationspanelen för datatillgänglighet. Stoppa tar bort den lokala observationen.'],
    stopping:['Sessionen stoppas','Den lokala observationen har tagits bort. Vänta tills rensningen är klar innan du startar en ny session.'],
    stopped:['Sessionen har avslutats','Ingen automatisk omstart sker. Välj Starta för en ny begäran när behörigheten är aktiverad.'],
    failed:['Anslutningen är inte tillgänglig','Åtgärden kunde inte slutföras. Kontrollera programmets och tjänstens status. Om Starta förblir inaktiverad, stäng och öppna vyn igen.'],
  },
} as const;
function checkLocale(locale: Locale): void {
  if (locale !== 'en' && locale !== 'sv-SE') throw new Error('unsupported_locale');
}

/** Exclusively owns root and one asynchronous host operation. No timers or storage. */
export function mountConnectionControls(root: HTMLElement, operation: ConnectionOperation, locale: Locale = 'en') {
  checkLocale(locale);
  const document = root.ownerDocument, window = document.defaultView;
  if (!window) throw new Error('unsupported_host');
  if (!operation || typeof operation.start !== 'function' || typeof operation.disconnect !== 'function') throw new Error('invalid_operation');
  const section = document.createElement('section'), heading = document.createElement('h2');
  const status = document.createElement('p'), details = document.createElement('details');
  const summary = document.createElement('summary'), guidance = document.createElement('p');
  const start = document.createElement('button'), stop = document.createElement('button');
  start.type = stop.type = 'button';
  start.setAttribute('data-feature','connection.start');stop.setAttribute('data-feature','connection.stop');
  status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.setAttribute('aria-atomic','true');
  details.append(summary,guidance);section.append(heading,status,start,stop,details);root.replaceChildren(section);
  let disposed = false, enabled = false, suspended = false, clearing = false, fault = false;
  let outcome: State = 'idle';
  type Run = {controller: AbortController; stopping: boolean};
  let run: Run | undefined;
  const visible = () => !suspended && document.visibilityState === 'visible';
  function render(): void {
    if (disposed) return;
    const state: State = fault ? 'failed' : run?.stopping ? 'stopping' : !enabled ? 'unavailable' :
      !visible() ? 'paused' : run ? 'requested' : outcome;
    const text = copy[locale];
    section.lang = locale;section.setAttribute('aria-label',text.title);
    heading.textContent = text.title;status.textContent = text[state][0];guidance.textContent = text[state][1];
    status.setAttribute('data-state',state);details.setAttribute('data-help-topic',`connection.${state}`);
    summary.textContent = text.help;start.textContent = text.start;stop.textContent = text.stop;
    start.disabled = fault || !!run || !enabled || !visible();stop.disabled = !run || run.stopping;
  }
  function withdraw(): void {
    if (clearing) {fault = true;return;}
    clearing = true;
    try {operation.disconnect();} catch {fault = true;} finally {clearing = false;}
  }
  function cancel(): void {
    const previous = run;
    if (previous) previous.stopping = true;
    withdraw();previous?.controller.abort();render();
  }
  async function begin(): Promise<void> {
    if (disposed || fault || run || !enabled || !visible()) return;
    let current: Run;
    try {current = {controller:new AbortController(),stopping:false};}
    catch {fault = true;render();return;}
    run = current;outcome = 'stopped';render();
    try {
      await operation.start(current.controller.signal);
    } catch {if (!current.stopping) outcome = 'failed';}
    finally {
      if (!disposed && run === current) {
        current.stopping = true;withdraw();current.controller.abort();run = undefined;render();
      }
    }
  }
  const onStart = () => {void begin();};
  const onStop = () => {if (!disposed && run && !run.stopping) cancel();};
  const onVisibility = () => {if (!visible()) cancel();else render();};
  const suspend = () => {suspended = true;cancel();};
  const resume = () => {suspended = false;cancel();};
  const events: [EventTarget,string,() => void][] = [
    [start,'click',onStart],[stop,'click',onStop],[document,'visibilitychange',onVisibility],
    [document,'freeze',suspend],[document,'resume',resume],[window,'pagehide',suspend],[window,'pageshow',resume],
  ];
  function setEnabled(next: boolean): void {
    if (disposed) return;
    if (typeof next !== 'boolean') throw new Error('invalid_permission');
    enabled = next;if (!enabled) cancel();else render();
  }
  function setLocale(next: Locale): void {if (!disposed) {checkLocale(next);locale = next;render();}}
  function dispose(): void {
    if (disposed) return;
    disposed = true;enabled = false;
    for (const [target,name,callback] of events) target.removeEventListener(name,callback);
    cancel();run = undefined;
    for (const node of [heading,status,guidance,summary,start,stop]) node.textContent = '';
    section.remove();
  }
  for (const [target,name,callback] of events) target.addEventListener(name,callback);
  withdraw();render();
  return {setEnabled,setLocale,dispose};
}
