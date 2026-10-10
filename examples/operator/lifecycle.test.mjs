import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {parseHTML} from 'linkedom';
import {Observation} from '../clients/typescript/dist/client.js';
import {Ajv2020} from '../clients/typescript/node_modules/ajv/dist/2020.js';

const module = await import('./dist/lifecycle.js').catch(error => {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  return {};
});
const result = JSON.parse(readFileSync(new URL('../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0];
const envelope = {api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),
  clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};

function setup(initialVisibility='visible') {
  assert.equal(typeof module.mountObservationHost,'function','lifecycle adapter must exist');
  const {document,Event: DOMEvent} = parseHTML('<html><body><main>previous host content</main><aside>other host</aside></body></html>');
  const window = new EventTarget();
  const timers = new Map();
  const listeners = new Set();
  let serial=0, visibility=initialVisibility, now=0, clears=0;
  window.setInterval = (callback,delay) => { assert.equal(delay,20); timers.set(++serial,callback); return serial; };
  window.clearInterval = id => timers.delete(id);
  Object.defineProperty(document,'defaultView',{value:window});
  Object.defineProperty(document,'visibilityState',{get:()=>visibility});
  for (const target of [document,window]) {
    const add=target.addEventListener.bind(target),remove=target.removeEventListener.bind(target);
    target.addEventListener=(name,callback,...rest)=>{listeners.add({target,name,callback});add(name,callback,...rest);};
    target.removeEventListener=(name,callback,...rest)=>{
      for(const record of listeners) if(record.target===target&&record.name===name&&record.callback===callback) listeners.delete(record);
      remove(name,callback,...rest);
    };
  }
  const observation=new Observation();
  const source={view:()=>observation.view(now),disconnect:()=>{clears++;observation.disconnect();}};
  const root=document.querySelector('main');
  return {root,document,window,DOMEvent,timers,listeners,observation,source,
    mount:locale=>module.mountObservationHost(root,source,locale),
    visibility(value){visibility=value;document.dispatchEvent(new DOMEvent('visibilitychange'));},
    emit(name){(name==='freeze'||name==='resume'?document:window).dispatchEvent(name==='freeze'||name==='resume'?new DOMEvent(name):new Event(name));},
    admit(){observation.accept(envelope,now);},
    tick(value){now=value;for(const callback of [...timers.values()])callback();},
    clears:()=>clears,
    state:()=>root.querySelector('[role=status]')?.getAttribute('data-state')};
}

test('mount clears old state; fresh SDK admission expires on requested refresh ticks',()=>{
  const s=setup();s.admit();const host=s.mount();
  assert.equal(s.state(),'expired');assert.equal(s.clears(),1);assert.equal(s.timers.size,1);assert.equal(s.listeners.size,5);
  s.admit();host.refresh();assert.equal(s.state(),'delayed');
  s.tick(100);assert.equal(s.state(),'delayed');
  s.tick(101);assert.equal(s.state(),'expired');host.dispose();
});
test('hidden input stays withdrawn through help and locale changes; resume clears background admissions',()=>{
  const s=setup();const host=s.mount();s.admit();host.refresh();s.visibility('hidden');
  assert.equal(s.state(),'expired');assert.equal(s.timers.size,0);
  s.admit();host.refresh();host.setLocale('sv-SE');
  const details=s.root.querySelector('details');details.setAttribute('open','');
  details.dispatchEvent(new s.DOMEvent('toggle'));
  assert.equal(s.state(),'expired');assert.equal(s.root.querySelector('h2').textContent,'Ingen aktuell observation');
  s.visibility('visible');assert.equal(s.state(),'expired');assert.equal(s.timers.size,1);
  s.admit();host.refresh();assert.equal(s.state(),'delayed');host.dispose();
});
for(const [leave,enter] of [['pagehide','pageshow'],['freeze','resume']]) test(`${leave} withdraws until ${enter} even if visibility still reports visible`,()=>{
  const s=setup();const host=s.mount();s.admit();host.refresh();s.emit(leave);
  s.admit();host.refresh();assert.equal(s.state(),'expired');assert.equal(s.timers.size,0);
  s.emit(enter);assert.equal(s.state(),'expired');assert.equal(s.timers.size,1);host.dispose();
});
test('unknown visibility fails closed without starting a timer',()=>{
  const s=setup(undefined);s.visibility('unknown');const host=s.mount();
  s.admit();host.refresh();assert.equal(s.state(),'expired');assert.equal(s.timers.size,0);host.dispose();
});
test('dispose clears source, timer, listeners and detached text; late callbacks remain inert',()=>{
  const s=setup();const host=s.mount();s.admit();host.refresh();
  const stale=[...s.timers.values()][0],status=s.root.querySelector('[role=status]');
  host.dispose();const clears=s.clears();
  stale();host.refresh();host.setLocale('en');host.dispose();s.emit('pageshow');s.visibility('visible');
  assert.equal(s.clears(),clears);assert.equal(s.timers.size,0);assert.equal(s.listeners.size,0);
  assert.equal(s.root.textContent,'');assert.equal(status.textContent,'');assert.equal(s.document.querySelector('aside').textContent,'other host');
});
test('source clearing failure latches unavailable without revealing its exception',()=>{
  const s=setup();s.source.disconnect=()=>{throw new Error('private source failure');};
  const host=s.mount();s.admit();host.refresh();s.emit('pageshow');host.setLocale('sv-SE');
  assert.equal(s.state(),'invalid');assert.equal(s.timers.size,0);assert.ok(!s.root.textContent.includes('private'));host.dispose();
});
for(const [locale,guidance] of [['en','Check the client and service status'],['sv-SE','Kontrollera klientens och tjänstens status']]) {
  test(`${locale}: lifecycle failure guidance does not misdiagnose an unsupported wire format`,()=>{
    const s=setup();s.source.disconnect=()=>{throw new Error('private');};const host=s.mount(locale);
    assert.ok(s.root.querySelector('details').textContent.includes(guidance));host.dispose();
  });
}
test('reader failure withdraws details and a later independent read can recover',()=>{
  const s=setup();const host=s.mount();const read=s.source.view;
  s.source.view=()=>{throw new Error('private reader failure');};host.refresh();
  assert.equal(s.state(),'invalid');assert.ok(!s.root.textContent.includes('private'));
  s.source.view=read;s.admit();host.refresh();assert.equal(s.state(),'delayed');host.dispose();
});
test('reader disposal cannot repopulate the panel or restart its timer',()=>{
  const s=setup();const host=s.mount();const read=s.source.view;
  s.source.view=()=>{const old=read();host.dispose();return old;};s.admit();host.refresh();
  assert.equal(s.root.textContent,'');assert.equal(s.timers.size,0);assert.equal(s.listeners.size,0);
});
test('unsupported locale fails before clearing the source or replacing host content',()=>{
  const s=setup();assert.throws(()=>s.mount('sv'),{message:'unsupported_locale'});
  assert.equal(s.root.textContent,'previous host content');assert.equal(s.clears(),0);assert.equal(s.timers.size,0);assert.equal(s.listeners.size,0);
});
test('scheduler failure withdraws details and never claims an active refresh loop',()=>{
  const s=setup();s.window.setInterval=()=>{throw new Error('private timer failure');};const host=s.mount();
  s.admit();host.refresh();assert.equal(s.state(),'invalid');assert.equal(s.timers.size,0);
  assert.ok(!s.root.textContent.includes('private'));host.dispose();assert.equal(s.listeners.size,0);
});
test('suspension during a source read cannot publish its interrupted view',()=>{
  const s=setup();const host=s.mount();const read=s.source.view;
  s.source.view=()=>{const old=read();s.emit('freeze');return old;};s.admit();host.refresh();
  assert.equal(s.state(),'expired');assert.equal(s.timers.size,0);host.dispose();
});
test('reentrant source clearing fails closed without unbounded callback recursion',()=>{
  const s=setup();let clears=0;
  s.source.disconnect=()=>{clears++;s.emit('pageshow');};const host=s.mount();
  assert.equal(clears,1);assert.equal(s.state(),'invalid');assert.equal(s.timers.size,0);host.dispose();
});
test('repeated activation replaces the single timer and clears old observations',()=>{
  const s=setup();const host=s.mount();
  for(let i=0;i<3;i++){s.admit();host.refresh();s.emit('pageshow');assert.equal(s.state(),'expired');assert.equal(s.timers.size,1);}
  host.dispose();assert.equal(s.timers.size,0);
});
test('lifecycle ADR uses a closed schema and cannot acquire unsupported qualification claims',()=>{
  const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
  const validate=new Ajv2020({strict:true}).compile(read('./lifecycle-adr.schema.json'));
  const adr=read('./lifecycle-adr.json');assert.equal(validate(adr),true,JSON.stringify(validate.errors));
  assert.equal(validate({...adr,qualified:true}),false);
  assert.equal(validate({...adr,c4:{...adr.c4,unreviewed:'claim'}}),false);
});

test('live SDK source composes with visibility withdrawal without caching callback views',async t=>{
  const {createObservationSource}=await import('../clients/typescript/dist/client.js');
  const s=setup(),source=createObservationSource(),caller=new AbortController(),requests=[];
  Object.assign(s.source,source);
  let controller,signal;
  t.mock.method(performance,'now',()=>0);
  t.mock.method(globalThis,'setInterval',()=>assert.fail('transport source must not create a second display timer'));
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    requests.push({url,options});
    if(options.method==='POST')return Response.json({source_profile:'bench',session:envelope.session});
    if(options.method==='DELETE')return new Response(null,{status:204});
    signal=options.signal;
    return new Response(new ReadableStream({start(value){controller=value;}}));
  });
  const host=s.mount('en');
  const done=source.start('http://127.0.0.1:8765','synthetic-token','bench',caller.signal).then(()=>undefined,error=>error);
  const turn=()=>new Promise(resolve=>setImmediate(resolve));
  try {
    await turn();controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(envelope)}\n\n`));await turn();
    host.refresh();assert.equal(s.state(),'delayed');assert.equal(s.timers.size,1);
    s.visibility('hidden');assert.equal(s.state(),'expired');assert.equal(signal.aborted,true);
    assert.equal(source.view().label,'expired');assert.equal(caller.signal.aborted,false);
    s.visibility('visible');host.setLocale('sv-SE');assert.equal(s.state(),'expired');
    assert.equal(requests.filter(r=>r.options.method==='POST').length,1,'visibility must not restart authentication');
  } finally {controller.close();await done;host.dispose();}
  assert.equal((await done)?.message,'stream_unavailable');assert.equal(requests.at(-1).options.method,'DELETE');
  assert.equal(s.root.textContent,'');assert.equal(s.listeners.size,0);assert.equal(s.timers.size,0);
});
