export type Locale = 'en' | 'sv-SE';
export type PresentationState = 'expired' | 'delayed' | 'invalid';
export interface OperatorStatus {
  locale: Locale;
  state: PresentationState;
  currentState: 'UNKNOWN';
  observedState: 'PRESENT' | 'UNKNOWN';
  sources: string[];
  title: string;
  explanation: string;
  helpId: `observation.${PresentationState}`;
}

const guidance = {
  en: {
    expired: ['No current observation', 'The observation has expired or was cleared. No sensor details are available. Wait for a new validated observation.'],
    delayed: ['Delayed observation', 'These sensor details describe an earlier observation. Current conditions are UNKNOWN because transport freshness is not established.'],
    invalid: ['Observation unavailable', 'The display received an unsupported observation. Sensor details were withdrawn. Check the client and service versions before retrying.'],
  },
  'sv-SE': {
    expired: ['Ingen aktuell observation', 'Observationen har löpt ut eller rensats. Inga sensoruppgifter är tillgängliga. Vänta på en ny validerad observation.'],
    delayed: ['Fördröjd observation', 'Sensoruppgifterna beskriver en tidigare observation. Det aktuella tillståndet är UNKNOWN eftersom överföringens aktualitet inte har fastställts.'],
    invalid: ['Observationen är inte tillgänglig', 'Visningen tog emot en observation som inte stöds. Sensoruppgifterna har tagits bort. Kontrollera klientens och tjänstens versioner innan du försöker igen.'],
  },
} as const;
const sensors = new Set(['rgb', 'lwir', 'radar', 'depth', 'nir']);
const fields = ['current_state', 'label', 'observed_state', 'sources', 'uncertainty'];

/** Presentation admission only: neither source authentication nor a freshness lease.
 * Call with a fresh SDK view at render time. Returned text is plain text, not HTML. */
export function presentObservation(input: unknown, locale: Locale): OperatorStatus {
  if (locale !== 'en' && locale !== 'sv-SE') throw new Error('unsupported_locale');
  let state: PresentationState = 'invalid';
  let observedState: 'PRESENT' | 'UNKNOWN' = 'UNKNOWN';
  let sources: string[] = [];
  try {
    // Snapshot caller data; like direct SDK object admission this is not a
    // pre-clone byte/allocation bound. Wire bytes belong to the SDK ingress.
    const view = structuredClone(input) as Record<string, unknown>;
    if (!view || typeof view !== 'object' || Array.isArray(view) ||
        Object.keys(view).sort().join(',') !== fields.join(',') ||
        view.current_state !== 'UNKNOWN' ||
        (view.observed_state !== 'PRESENT' && view.observed_state !== 'UNKNOWN') ||
        !Array.isArray(view.sources) || view.sources.length > 5 ||
        Array.from(view.sources).some(source => typeof source !== 'string' || !sensors.has(source)) ||
        new Set(view.sources).size !== view.sources.length ||
        !Array.isArray(view.uncertainty) || view.uncertainty.length > 32 ||
        Array.from(view.uncertainty).some(row => !Array.isArray(row) || row.length !== 2 ||
          Array.from(row).some(value => typeof value !== 'number' || !Number.isFinite(value)))) {
      throw new Error();
    }
    if (view.label === 'expired' && view.observed_state === 'UNKNOWN' &&
        view.sources.length === 0 && view.uncertainty.length === 0) state = 'expired';
    else if (view.label === 'delayed_observation') {
      state = 'delayed'; observedState = view.observed_state; sources = [...view.sources];
    }
  } catch { /* Fixed unavailable output; never copy caller exception details. */ }
  const [title, explanation] = guidance[locale][state];
  return {locale, state, currentState: 'UNKNOWN', observedState, sources,
    title, explanation, helpId: `observation.${state}`};
}
