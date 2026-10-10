import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
const module=await import('./help-inventory.mjs').catch(error=>{if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;return {};});
const sources=()=>Object.fromEntries(['presenter','connection'].map(name=>[name,readFileSync(new URL(`./src/${name}.ts`,import.meta.url),'utf8')]));
function build(input=sources(),revision={head:'a'.repeat(40),modified:true}) {assert.equal(typeof module.createStateHelpInventory,'function');return module.createStateHelpInventory(input,new Uint8Array([1,2,3]),revision);}
test('inventory derives every typed state and both translations from source',()=>{
 const value=build();assert.equal(value.topics.length,10);assert.deepEqual(value.locales,['en','sv-SE']);assert.equal(value.release_sha,null);assert.equal(value.product_help_complete,false);
 assert.deepEqual(value.topics.map(t=>t.id).sort(),['connection.failed','connection.idle','connection.paused','connection.requested','connection.stopped','connection.stopping','connection.unavailable','observation.delayed','observation.expired','observation.invalid']);
 assert.match(value.topics.find(t=>t.id==='observation.delayed').translations['sv-SE'].title,/Fördröjd/);
});
for(const [name,mutate] of [
 ['missing translated state',s=>{s.presenter=s.presenter.replace("    delayed: ['Fördröjd observation',", "    removed: ['Fördröjd observation',");}],
 ['undocumented new state',s=>{s.presenter=s.presenter.replace("'expired' | 'delayed' | 'invalid'","'expired' | 'delayed' | 'invalid' | 'new_state'");}],
 ['unshipped help claim',s=>{s.connection=s.connection.replace("    paused:['Connection paused'","    unshipped:['Unavailable','Not implemented'],\n    paused:['Connection paused'");}],
 ['duplicate help key',s=>{s.connection=s.connection.replace("    paused:['Connection paused'","    paused:['Duplicate','Duplicate body'],\n    paused:['Connection paused'");}],
 ['runtime expression in help',s=>{s.connection=s.connection.replace("paused:['Connection paused'","paused:[privateFunction()");}],
 ['missing locale',s=>{s.presenter=s.presenter.replace("  'sv-SE': {","  fr: {");}],
 ['blank help text',s=>{s.presenter=s.presenter.replace("'No current observation'","''");}],
 ['malformed source',s=>{s.presenter+='\nconst = ;';}],
])test(`help inventory rejects ${name}`,()=>{const input=sources();mutate(input);assert.throws(()=>build(input),{message:'unsupported_help_source'});});
test('source and artifact bindings change with their actual bytes',()=>{
 const input=sources(),first=build(input);input.presenter+='\n// source change\n';const second=build(input);assert.notEqual(first.source_sha256.presenter,second.source_sha256.presenter);
 const third=module.createStateHelpInventory(input,new Uint8Array([4]),{head:'a'.repeat(40),modified:true});assert.notEqual(second.module_sha256,third.module_sha256);
});
test('only an exact clean source revision is eligible for a release SHA binding',()=>{
 assert.equal(build(sources(),{head:'b'.repeat(40),modified:false}).release_sha,'b'.repeat(40));
 for(const revision of [{head:'main',modified:false},{head:'a'.repeat(40),modified:'false'},{head:'a'.repeat(40),modified:false,qualified:true}])assert.throws(()=>build(sources(),revision),{message:'invalid_help_revision'});
});

test('state-help decision rejects unqualified extra claims',async()=>{
 const {Ajv2020}=await import('../clients/typescript/node_modules/ajv/dist/2020.js');const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url)));
 const value=read('./state-help-adr.json'),validate=new Ajv2020({strict:true}).compile(read('./state-help-adr.schema.json'));
 assert.equal(validate(value),true,JSON.stringify(validate.errors));assert.equal(validate({...value,product_complete:true}),false);assert.equal(validate({...value,c4:{...value.c4,certified:true}}),false);
});
