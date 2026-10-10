import assert from 'node:assert/strict';
import {test} from 'node:test';
import {parseHTML} from 'linkedom';
import {readFileSync} from 'node:fs';
import {Ajv2020} from '../clients/typescript/node_modules/ajv/dist/2020.js';
import {Observation} from '../clients/typescript/dist/client.js';

const module = await import('./dist/panel.js').catch(error => {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  return {};
});
const expired = {label:'expired',current_state:'UNKNOWN',observed_state:'UNKNOWN',sources:[],uncertainty:[]};
const delayed = {label:'delayed_observation',current_state:'UNKNOWN',observed_state:'PRESENT',sources:['lwir'],uncertainty:[[1,2]]};
function setup(read = () => delayed, locale = 'en') {
  assert.equal(typeof module.mountObservationPanel, 'function', 'renderer must exist');
  const {document, Event} = parseHTML('<html><body><main></main><aside>host content</aside></body></html>');
  const root = document.querySelector('main');
  const panel = module.mountObservationPanel(root, read, locale);
  return {root, panel, document, Event};
}
for (const locale of ['en','sv-SE']) {
  test(`${locale}: renders UNKNOWN, delayed sensor details and contextual help`, () => {
    const {root} = setup(() => delayed, locale);
    assert.equal(root.querySelector('section').lang, locale);
    const status = root.querySelector('[role=status]');
    assert.equal(status.getAttribute('aria-atomic'), 'true');
    assert.equal(status.getAttribute('aria-live'), 'polite');
    assert.match(status.textContent, /UNKNOWN/);
    assert.match(status.textContent, /PRESENT/);
    assert.match(status.textContent, /lwir/);
    assert.equal(root.querySelector('details').getAttribute('data-help-topic'), 'observation.delayed');
    assert.equal(root.querySelector('summary').textContent, locale === 'en' ? 'Help' : 'Hjälp');
    assert.match(root.querySelector('details p').textContent, /UNKNOWN/);
    assert.equal(root.querySelectorAll('button[type=button]').length, 2);
    assert.equal(root.querySelector('button[aria-pressed=true]').lang, locale);
  });
}
test('language button obtains a fresh view and preserves control nodes', () => {
  let current = delayed, reads = 0;
  const {root, Event} = setup(() => { reads++; return current; });
  const button = root.querySelector('button[lang="sv-SE"]');
  current = expired;
  button.dispatchEvent(new Event('click'));
  assert.equal(reads, 2);
  assert.equal(root.querySelector('section').lang, 'sv-SE');
  assert.ok(root.querySelector('button[lang="sv-SE"]') === button, 'language control must survive refresh');
  assert.equal(root.querySelector('details').getAttribute('data-help-topic'), 'observation.expired');
  assert.ok(!root.textContent.includes('lwir'));
  assert.ok(!root.textContent.includes('PRESENT'));
});
test('opening contextual help refreshes expired data without closing the disclosure', () => {
  let current = delayed;
  const {root, Event} = setup(() => current);
  const details = root.querySelector('details');
  current = expired;
  details.setAttribute('open', '');
  details.dispatchEvent(new Event('toggle'));
  assert.ok(root.querySelector('details') === details, 'help disclosure must survive refresh');
  assert.ok(details.hasAttribute('open'));
  assert.equal(details.getAttribute('data-help-topic'), 'observation.expired');
  assert.ok(!root.textContent.includes('lwir'));
});
test('read failures and markup-like input withdraw details without disclosing error text', () => {
  let current = delayed, fail = false;
  const {root, panel} = setup(() => { if (fail) throw Error('private'); return current; });
  fail = true; panel.refresh();
  assert.equal(root.querySelector('details').getAttribute('data-help-topic'), 'observation.invalid');
  assert.ok(!root.textContent.includes('lwir'));
  assert.ok(!root.textContent.includes('private'));
  fail = false; current = {...delayed,sources:['<img src=x onerror=secret()>']};
  panel.refresh();
  assert.equal(root.querySelectorAll('img,script').length, 0);
  assert.ok(!root.textContent.includes('secret'));
});
test('disposal removes only owned content and revokes late callbacks', () => {
  let reads = 0;
  const {root, panel, document, Event} = setup(() => { reads++; return delayed; });
  const button = root.querySelector('button');
  const details = root.querySelector('details');
  panel.dispose(); panel.dispose(); panel.refresh(); panel.setLocale('sv-SE');
  button.dispatchEvent(new Event('click'));
  details.setAttribute('open', ''); details.dispatchEvent(new Event('toggle'));
  assert.equal(root.childNodes.length, 0);
  assert.equal(reads, 1);
  assert.equal(document.querySelector('aside').textContent, 'host content');
});
test('unsupported locale is rejected before reading or replacing host content', () => {
  const {document} = parseHTML('<main>preserve</main>');
  const root = document.querySelector('main');
  assert.equal(typeof module.mountObservationPanel, 'function');
  assert.throws(() => module.mountObservationPanel(root, () => assert.fail('must not read'), 'sv'), {message:'unsupported_locale'});
  assert.equal(root.textContent, 'preserve');
});
test('all states expose matching English and Swedish contextual guidance', () => {
  for (const [view, state] of [[expired,'expired'],[delayed,'delayed'],[null,'invalid']]) {
    const en = setup(() => view), sv = setup(() => view, 'sv-SE');
    for (const {root} of [en,sv]) assert.equal(root.querySelector('details').getAttribute('data-help-topic'), `observation.${state}`);
    assert.notEqual(en.root.querySelector('details p').textContent, sv.root.querySelector('details p').textContent);
    assert.notEqual(en.root.querySelector('h2').textContent, sv.root.querySelector('h2').textContent);
  }
});
for (const reentrant of [false,true]) test(`disposal clears retained text nodes, getter disposal=${reentrant}`, () => {
  let input = delayed;
  const {root,panel} = setup(() => input);
  const textNodes = [...root.querySelectorAll('[role=status] h2,[role=status] p,details p')];
  if (reentrant) {
    input = {...delayed,get label() { panel.dispose(); return 'delayed_observation'; }};
    panel.refresh();
  } else panel.dispose();
  assert.equal(root.childNodes.length, 0);
  for (const node of textNodes) assert.equal(node.textContent, '');
});
test('real SDK expiry and invalid admission remove earlier sensor details on refresh', () => {
  const result=JSON.parse(readFileSync(new URL('../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0];
  const envelope={api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
  const observation = new Observation(); let now=0;
  observation.accept(envelope,now);
  const {root,panel} = setup(() => observation.view(now));
  now=100; panel.refresh();
  assert.equal(root.querySelector('[role=status]').getAttribute('data-state'),'delayed');
  now=101; panel.refresh();
  assert.equal(root.querySelector('[role=status]').getAttribute('data-state'),'expired');
  assert.ok(!root.textContent.includes('PRESENT'));
  assert.throws(() => observation.accept({...envelope,private:true},now));
  panel.refresh();
  assert.equal(root.querySelector('[role=status]').getAttribute('data-state'),'expired');
});
test('panel ADR is closed and describes all four C4 views', () => {
  const read = name => JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
  const validate = new Ajv2020({strict:true}).compile(read('./panel-adr.schema.json'));
  const adr=read('./panel-adr.json');
  assert.equal(validate(adr),true,JSON.stringify(validate.errors));
  assert.equal(validate({...adr,certified:true}),false);
  const missing=structuredClone(adr); delete missing.c4.code;
  assert.equal(validate(missing),false);
});
test('unchanged refresh reads again without replacing live-region text nodes', () => {
  let reads=0;
  const {root,panel}=setup(() => { reads++; return delayed; });
  const nodes=[...root.querySelectorAll('[role=status] h2,[role=status] p,details p')];
  const children=nodes.map(node => node.firstChild);
  panel.refresh();
  assert.equal(reads,2);
  nodes.forEach((node,index) => assert.ok(node.firstChild === children[index], 'unchanged text node must survive refresh'));
});
