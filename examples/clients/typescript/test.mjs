import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {Observation} from './dist/client.js';

const result=JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0];
const envelope={api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
test('expiry, disconnect, suspension and unbounded transit remain UNKNOWN',()=>{
 const o=new Observation();o.accept(envelope,0);
 assert.equal(o.view(50).label,'delayed_observation');assert.equal(o.view(50).current_state,'UNKNOWN');
 assert.equal(o.view(101).label,'expired');o.accept(envelope,100);assert.equal(o.view(0).label,'expired');
 o.accept(envelope,0);o.disconnect();assert.equal(o.view(0).label,'expired');
});
test('unknown enum or extra field rejects and clears old scene',()=>{
 const o=new Observation();o.accept(envelope,0);
 assert.throws(()=>o.accept({...envelope,result:{...result,state:'SAFE'}},0));
 assert.equal(o.view(0).label,'expired');
 assert.throws(()=>o.accept({...envelope,person_identity:'forbidden'},0));
});
