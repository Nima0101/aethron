import type {Locale} from './presenter.js';

type Action = 'connection.start' | 'connection.stop' | 'locale.en' | 'locale.sv-SE';
const actionGuidance = {
  en: {
    'connection.start': ['Start', 'Request an observation session when the application enables Start. This does not confirm current conditions.'],
    'connection.stop': ['Stop', 'Withdraw the local observation and request session cancellation. Wait for cleanup before starting again.'],
    'locale.en': ['English', 'Show this observation view and its help in English. Changing language does not start a session.'],
    'locale.sv-SE': ['Svenska', 'Show this observation view and its help in Swedish. Changing language does not start a session.'],
  },
  'sv-SE': {
    'connection.start': ['Starta', 'Begär en observationssession när programmet aktiverar Starta. Detta bekräftar inte aktuella förhållanden.'],
    'connection.stop': ['Stoppa', 'Ta bort den lokala observationen och begär att sessionen avbryts. Vänta tills rensningen är klar innan du startar igen.'],
    'locale.en': ['English', 'Visa denna observationsvy och dess hjälp på engelska. Ett språkbyte startar inte en session.'],
    'locale.sv-SE': ['Svenska', 'Visa denna observationsvy och dess hjälp på svenska. Ett språkbyte startar inte en session.'],
  },
} as const;
// DOM element identifiers only. One scalar per live Document; no observation data.
const sequences = new WeakMap<Document, number>();
function descriptionId(scope: HTMLElement): string {
  const document = scope.ownerDocument;
  // Buttons are still detached during construction. Use the mount root's tree,
  // including a shadow root or detached subtree, when checking host collisions.
  const tree = scope.getRootNode() as Document | DocumentFragment | Element;
  for (let attempt = 0; attempt < 32; attempt++) {
    const next = (sequences.get(document) ?? 0) + 1;
    if (!Number.isSafeInteger(next)) break;
    sequences.set(document, next);
    const id = `aethron-action-help-${next}`;
    if (!document.getElementById(id) &&
        !(tree.nodeType === 1 && (tree as Element).id === id) &&
        !tree.querySelector(`[id="${id}"]`)) return id;
  }
  throw new Error('help_id_unavailable');
}

/** Internal, exclusively owned button. Caller inserts element beside the button
 * and forwards locale/disposal. scope is the containing mount root before the
 * detached button is inserted. No listeners, source reads, timers or transport. */
export function bindActionHelp(button: HTMLButtonElement, action: Action, locale: Locale, scope: HTMLElement = button) {
  function check(next: Locale): void {if (next !== 'en' && next !== 'sv-SE') throw new Error('unsupported_locale');}
  check(locale);
  if (!Object.hasOwn(actionGuidance.en, action)) throw new Error('unsupported_action');
  const element = button.ownerDocument.createElement('p');
  element.id = descriptionId(scope);
  element.setAttribute('data-help-action', action);
  button.setAttribute('data-feature', action);
  button.setAttribute('aria-describedby', element.id);
  let disposed = false;
  function setLocale(next: Locale): void {
    if (disposed) return;
    check(next);
    if (element.lang !== next) element.lang = next;
    const body = actionGuidance[next][action][1];
    if (element.textContent !== body) element.textContent = body;
  }
  function dispose(): void {
    if (disposed) return;
    disposed = true;element.textContent = '';element.remove();
    button.removeAttribute('aria-describedby');button.removeAttribute('data-feature');
  }
  setLocale(locale);
  return {element,setLocale,dispose};
}
