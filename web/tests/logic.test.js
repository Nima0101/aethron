import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizedObservations, evidenceStatus } from '../src/logic.js';

test('maps human, vehicle and animal boxes into bounded coordinates', () => {
  const items = normalizedObservations([
    {class:'person', score:0.95, bbox:[10,20,20,20]},
    {class:'dog', score:0.9, bbox:[60,70,100,100]},
    {class:'car', score:0.8, bbox:[40,40,10,10]},
  ], 100, 100);
  assert.equal(items.length, 3);
  assert.deepEqual(items[0].box, [0.1,0.2,0.2,0.2]);
  assert.deepEqual(items[1].box, [0.6,0.7,0.4,0.3]);
});
test('filters unknown, low-score, malformed and out-of-frame detections', () => {
  const objects = normalizedObservations([
    {class:'spaceship',score:1,bbox:[1,1,2,2]},
    {class:'person',score:0.2,bbox:[1,1,2,2]},
    {class:'person',score:0.9,bbox:[5,5,-1,3]},
    {class:'person',score:0.9,bbox:[5,5,NaN,3]},
    {class:'person',score:0.9,bbox:[10,10,12,12]}
  ],20,20);
  assert.equal(objects.length,1);
  assert.deepEqual(objects[0].box,[0.5,0.5,0.5,0.5]);
});
test('never calls old or invalid inferences fresh', () => {
  assert.equal(evidenceStatus(75),'CURRENT');
  assert.equal(evidenceStatus(100),'CURRENT');
  assert.equal(evidenceStatus(101),'DELAYED');
  assert.equal(evidenceStatus(-1),'UNKNOWN');
  assert.equal(evidenceStatus(NaN),'UNKNOWN');
});
