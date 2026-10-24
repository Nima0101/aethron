import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {Observation} from '../clients/typescript/dist/client.js';
import {presentObservation} from './dist/presenter.js';
import {Ajv2020} from '../clients/typescript/node_modules/ajv/dist/2020.js';

const expired = {label:'expired',current_state:'UNKNOWN',observed_state:'UNKNOWN',sources:[],uncertainty:[]};
const delayed = {label:'delayed_observation',current_state:'UNKNOWN',observed_state:'PRESENT',sources:['lwir'],uncertainty:[[0.1,0.2]]};
for (const locale of ['en','sv-SE']) {
 test(`${locale}: expired view has UNKNOWN and no residual sensor details`,()=>{
  const value=presentObservation(expired,locale);
  assert.equal(value.state,'expired');assert.equal(value.currentState,'UNKNOWN');
  assert.deepEqual(value.sources,[]);assert.equal(value.locale,locale);
  assert.ok(value.explanation.length>20);assert.equal(value.helpId,'observation.expired');
 });
 test(`${locale}: delayed presence never implies current presence`,()=>{
  const value=presentObservation(delayed,locale);
  assert.equal(value.state,'delayed');assert.equal(value.currentState,'UNKNOWN');
  assert.equal(value.observedState,'PRESENT');assert.deepEqual(value.sources,['lwir']);
  assert.equal(value.helpId,'observation.delayed');assert.ok(value.title.length>0);
  assert.equal('uncertainty' in value,false);assert.equal('track_id' in value,false);
 });
 test(`${locale}: missing or malformed projections withdraw all details`,()=>{
  for(const input of [null,{},[],{...delayed,current_state:'PRESENT'},
    {...delayed,observed_state:'SAFE'}, {...delayed,sources:['<script>secret</script>']},
    {...delayed,sources:['lwir','lwir']}, {...delayed,uncertainty:[[NaN,1]]},
    {...delayed,uncertainty:[[1]]}, {...delayed,uncertainty:Array(33).fill([1,1])},
    {...delayed,secret:'private'}, {...expired,sources:['lwir']},
    {...expired,observed_state:'PRESENT'}, {...delayed,uncertainty:[[1,Infinity]]}]) {
   const value=presentObservation(input,locale);
   assert.equal(value.state,'invalid');assert.equal(value.currentState,'UNKNOWN');
   assert.equal(value.observedState,'UNKNOWN');assert.deepEqual(value.sources,[]);
   assert.equal(value.helpId,'observation.invalid');assert.ok(!JSON.stringify(value).includes('secret'));
  }
 });
}
test('unsupported locale fails explicitly instead of mixing language',()=>{
 assert.throws(()=>presentObservation(delayed,'sv'),{message:'unsupported_locale'});
});
test('source and output mutation cannot alter later presentation',()=>{
 const input=structuredClone(delayed);const value=presentObservation(input,'en');
 input.sources.length=0;assert.deepEqual(value.sources,['lwir']);
 value.sources.push('rgb');assert.deepEqual(presentObservation(delayed,'en').sources,['lwir']);
});
test('hostile getters fail closed without returning source exception text',()=>{
 const input={get label(){throw new Error('private');}};
 assert.equal(presentObservation(input,'en').state,'invalid');
});
for (const [name, patch] of [
 ['source holes', {sources:Array(1)}],
 ['row holes', {uncertainty:Array(1)}],
 ['coordinate holes', {uncertainty:[Array(2)]}],
]) test(`sparse ${name} cannot pass presentation admission`,()=>{
 assert.equal(presentObservation({...delayed,...patch},'en').state,'invalid');
});
test('actual SDK admission, expiry and invalid input compose with presenter',()=>{
 const result=JSON.parse(readFileSync(new URL('../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0];
 const envelope={api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
 const observation=new Observation();observation.accept(envelope,0);
 assert.equal(presentObservation(observation.view(100),'en').state,'delayed');
 assert.equal(presentObservation(observation.view(101),'en').state,'expired');
 assert.throws(()=>observation.accept({...envelope,untrusted:true},200));
 assert.equal(presentObservation(observation.view(200),'sv-SE').state,'expired');
});
test('language coverage includes all states with distinct translated guidance',()=>{
 for(const view of [expired,delayed,null]) {
  const en=presentObservation(view,'en'),sv=presentObservation(view,'sv-SE');
  assert.equal(en.helpId,sv.helpId);assert.notEqual(en.title,sv.title);
  assert.notEqual(en.explanation,sv.explanation);
 }
});
test('ADR conforms to its closed versioned schema and rejects added claims',()=>{
 const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
 const validate=new Ajv2020({strict:true}).compile(read('./adr.schema.json'));
 const adr=read('./adr.json');assert.equal(validate(adr),true,JSON.stringify(validate.errors));
 assert.equal(validate({...adr,qualified:true}),false);
 assert.equal(validate({...adr,c4:{...adr.c4,unreviewed:'claim'}}),false);
});
