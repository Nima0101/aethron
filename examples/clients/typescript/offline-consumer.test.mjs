import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
const helper=await import('./offline-consumer.mjs').catch(e=>{if(e.code!=='ERR_MODULE_NOT_FOUND')throw e;return {};});
const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url)));
function build(manifest=read('./package.json'),lock=read('./package-lock.json')) {
 assert.equal(typeof helper.renderOfflineConsumer,'function');
 return helper.renderOfflineConsumer(manifest,lock,'client.tgz',new Uint8Array([1,2,3]));
}
test('consumer lock pins the archive and only the committed runtime graph',()=>{
 const value=build();assert.deepEqual(value.manifest.dependencies,{'aethron-edge-client-example':'file:client.tgz'});
 assert.equal(value.lock.packages[''].dependencies['aethron-edge-client-example'],'file:client.tgz');
 assert.equal(value.lock.packages['node_modules/aethron-edge-client-example'].resolved,'file:client.tgz');
 assert.match(value.lock.packages['node_modules/aethron-edge-client-example'].integrity,/^sha512-/);
 assert.equal(value.lock.packages['node_modules/typescript'],undefined);
 assert.deepEqual(value.lock.packages['node_modules/ajv'],read('./package-lock.json').packages['node_modules/ajv']);
});
test('dependency manifest drift fails closed before writing an install fixture',()=>{
 const manifest=read('./package.json');manifest.dependencies.ajv='1.0.0';assert.throws(()=>build(manifest),{message:'invalid_consumer_lock'});
});
test('unsupported lock formats and unpinned runtime packages are rejected',()=>{
 for(const mutate of [l=>l.lockfileVersion=1,l=>delete l.packages['node_modules/ajv'].integrity,l=>l.packages['node_modules/ajv'].resolved='http://registry.npmjs.org/ajv.tgz']){
  const lock=read('./package-lock.json');mutate(lock);assert.throws(()=>build(undefined,lock),{message:'invalid_consumer_lock'});
 }
});
test('archive paths cannot escape the external fixture directory',()=>{
 assert.equal(typeof helper.renderOfflineConsumer,'function');
 for(const name of ['../client.tgz','C:client.tgz','/tmp/client.tgz','a\\b.tgz'])assert.throws(()=>helper.renderOfflineConsumer(read('./package.json'),read('./package-lock.json'),name,new Uint8Array([1])),{message:'invalid_consumer_archive'});
});

for (const [label, entry] of [['null', null], ['array', []], ['string', 'private-marker'],
  ['number', 1], ['boolean', true]]) {
 test(`non-record ${label} lock entry fails with the fixed error`,()=>{
  const lock=read('./package-lock.json');lock.packages['node_modules/ajv']=entry;
  assert.throws(()=>build(undefined,lock),{name:'Error',message:'invalid_consumer_lock'});
 });
}
for (const dev of [null, 'true', 'false', 0, 1, [], {}]) {
 test(`non-boolean dev marker ${JSON.stringify(dev)} cannot classify a package`,()=>{
  const lock=read('./package-lock.json');lock.packages['node_modules/ajv'].dev=dev;
  assert.throws(()=>build(undefined,lock),{name:'Error',message:'invalid_consumer_lock'});
 });
}
test('explicit false dev marker retains the runtime package without modifying input',()=>{
 const manifest=read('./package.json'),lock=read('./package-lock.json');
 lock.packages['node_modules/ajv'].dev=false;
 const before=structuredClone(lock),value=build(manifest,lock);
 assert.deepEqual(value.lock.packages['node_modules/ajv'],before.packages['node_modules/ajv']);
 value.lock.packages['node_modules/ajv'].version='mutated';
 assert.deepEqual(lock,before);
});

test('offline consumer decision is closed and does not permit qualification extensions',async()=>{
 const {Ajv2020}=await import('ajv/dist/2020.js');const validate=new Ajv2020({strict:true}).compile(read('./offline-consumer-adr.schema.json'));
 const value=read('./offline-consumer-adr.json');assert.equal(validate(value),true,JSON.stringify(validate.errors));
 assert.equal(validate({...value,production_qualified:true}),false);assert.equal(validate({...value,c4:{...value.c4,certified:true}}),false);
});

 test('transport and install review uses a closed schema',async()=>{
  const {Ajv2020}=await import('ajv/dist/2020.js');
  const validate=new Ajv2020({strict:true}).compile(read('./transport-install-adr.schema.json'));
  const value=read('./transport-install-adr.json');
  assert.equal(validate(value),true,JSON.stringify(validate.errors));
  assert.equal(validate({...value,production_qualified:true}),false);
  assert.equal(validate({...value,c4:{...value.c4,certified:true}}),false);
 });
