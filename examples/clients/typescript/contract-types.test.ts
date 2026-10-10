import type {Prediction, Track} from './src/types.js';

const centre: Prediction['centre'] = [0.25, 0.5];
const box: Track['box'] = [0, 0, 1, 1];
const covariance: Track['covariance'] = [1, 1];
const velocity: Track['velocity_normalized_per_s'] = [0, 0];
const absent: Track['velocity_normalized_per_s'] = null;
void [centre, box, covariance, velocity, absent];
// @ts-expect-error A centre requires exactly two coordinates.
const emptyCentre: Prediction['centre'] = [];
// @ts-expect-error A box requires exactly four coordinates.
const shortBox: Track['box'] = [0, 0, 1];
// @ts-expect-error A covariance requires exactly two entries.
const longCovariance: Track['covariance'] = [1, 1, 2];
// @ts-expect-error A velocity requires exactly two coordinates when present.
const shortVelocity: Track['velocity_normalized_per_s'] = [0];
void [emptyCentre, shortBox, longCovariance, shortVelocity];
