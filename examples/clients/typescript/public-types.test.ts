import {Observation, observe, createObservationSource, type LiveObservationSource} from 'aethron-edge-client-example';

const view = new Observation().view(0);
const current: 'UNKNOWN' = view.current_state;
const label: 'expired' | 'delayed_observation' = view.label;
if (view.label === 'expired') {
  const observed: 'UNKNOWN' = view.observed_state;
  const sources: [] = view.sources;
  const uncertainty: [] = view.uncertainty;
  void [observed, sources, uncertainty];
} else {
  const observed: 'PRESENT' | 'UNKNOWN' = view.observed_state;
  const sources: ('rgb' | 'lwir' | 'radar' | 'depth' | 'nir')[] = view.sources;
  const uncertainty: number[][] = view.uncertainty;
  void [observed, sources, uncertainty];
}
// @ts-expect-error A delayed transport view cannot certify current presence.
const present: 'PRESENT' = view.current_state;
// @ts-expect-error A transport display has no durable or ephemeral track ID field.
view.track_id;
void [current, label, present];

void observe('https://example.invalid', 'synthetic-token', 'bench', state => {
  const callbackCurrent: 'UNKNOWN' = state.current_state;
  void callbackCurrent;
}, new AbortController().signal);

const source: LiveObservationSource = createObservationSource();
const sourceState: 'UNKNOWN' = source.view().current_state;
source.disconnect();
void source.start('https://example.invalid', 'synthetic-token', 'bench', new AbortController().signal);
// @ts-expect-error Only the transport may admit data through this public source.
source.accept({});
void sourceState;
