import {bindActionHelp} from './action-help.js';
import {presentObservation, type Locale} from './presenter.js';

const labels = {
  en: {panel:'Observation', current:'Current conditions', observed:'Earlier observation',
    sources:'Earlier sensor sources', none:'No sensor details', help:'Help'},
  'sv-SE': {panel:'Observation', current:'Aktuellt tillstånd', observed:'Tidigare observation',
    sources:'Tidigare sensorkällor', none:'Inga sensoruppgifter', help:'Hjälp'},
} as const;

/** Host owns transport, authorization and refresh scheduling. Supply a fresh SDK
 * view reader and an exclusively owned root; no network, timers or storage here. */
export function mountObservationPanel(root: HTMLElement, readView: () => unknown, locale: Locale = 'en',
  requestLocale?: (locale: Locale) => void) {
  // Reject unsupported locale before changing the host DOM or invoking its reader.
  presentObservation(null, locale);
  const document = root.ownerDocument;
  const section = document.createElement('section');
  const status = document.createElement('div');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.setAttribute('aria-atomic', 'true');
  const title = document.createElement('h2');
  const current = document.createElement('p');
  const observed = document.createElement('p');
  const sources = document.createElement('p');
  status.append(title, current, observed, sources);
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  const explanation = document.createElement('p');
  details.append(summary, explanation);
  const controls = document.createElement('div');
  let disposed = false;
  let latestRefresh: object | undefined;
  const buttons = (['en', 'sv-SE'] as const).map(language => {
    const button = document.createElement('button');
    button.type = 'button'; button.lang = language;
    button.textContent = language === 'en' ? 'English' : 'Svenska';
    const select = () => { if (!disposed) (requestLocale ?? setLocale)(language); };
    button.addEventListener('click', select);
    const help = bindActionHelp(button, `locale.${language}`, locale, root);
    controls.append(button, help.element);
    return {button, language, select, help};
  });
  section.append(controls, status, details);
  root.replaceChildren(section);

  function text(node: HTMLElement, value: string): void {
    if (node.textContent !== value) node.textContent = value;
  }
  function attribute(node: HTMLElement, name: string, value: string): void {
    if (node.getAttribute(name) !== value) node.setAttribute(name, value);
  }

  function refresh(): void {
    if (disposed) return;
    // Reader callbacks and structuredClone getters can synchronously reenter.
    // Only the newest invocation may publish, including a newer withdrawal.
    const ticket = {};
    latestRefresh = ticket;
    let input: unknown;
    try { input = readView(); }
    catch { input = null; }
    // Host callbacks may dispose the panel while obtaining the view.
    if (disposed || latestRefresh !== ticket) return;
    const view = presentObservation(input, locale);
    // Snapshotting direct object input can invoke getters too.
    if (disposed || latestRefresh !== ticket) return;
    const copy = labels[locale];
    attribute(section, 'lang', locale);
    attribute(section, 'aria-label', copy.panel);
    attribute(status, 'data-state', view.state);
    text(title, view.title);
    text(current, `${copy.current}: ${view.currentState}`);
    text(observed, `${copy.observed}: ${view.observedState}`);
    text(sources, view.sources.length ? `${copy.sources}: ${view.sources.join(', ')}` : copy.none);
    text(summary, copy.help);
    text(explanation, view.explanation);
    attribute(details, 'data-help-topic', view.helpId);
    for (const {button, language, help} of buttons) {
      attribute(button, 'aria-pressed', String(language === locale));help.setLocale(locale);
    }
  }
  function setLocale(next: Locale): void {
    if (disposed) return;
    presentObservation(null, next);
    locale = next; refresh();
  }
  const onToggle = () => { if (details.hasAttribute('open')) refresh(); };
  details.addEventListener('toggle', onToggle);
  function dispose(): void {
    if (disposed) return;
    disposed = true;
    latestRefresh = undefined;
    for (const {button, select, help} of buttons) {button.removeEventListener('click', select);help.dispose();}
    details.removeEventListener('toggle', onToggle);
    // Clear detached references as well as the visible root.
    for (const node of [title, current, observed, sources, explanation]) node.textContent = '';
    status.replaceChildren();
    section.remove();
  }
  refresh();
  return {refresh, setLocale, dispose};
}
