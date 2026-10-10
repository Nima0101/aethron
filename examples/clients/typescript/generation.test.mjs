import assert from 'node:assert/strict';
import {mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {test} from 'node:test';
import {checkGenerated, renderContract} from './generate-contract.mjs';

const spec = JSON.parse(readFileSync(new URL('../../../contracts/openapi/aethron-edge-v1.json', import.meta.url), 'utf8'));

test('committed declarations and bundle match the published OpenAPI input', () => {
  checkGenerated(renderContract(spec), new URL('./src/', import.meta.url));
});

test('bundling rewrites reference locations without changing descriptive text', () => {
  const input = structuredClone(spec);
  input.components.schemas.SceneEnvelope.description = 'Keep #/components/schemas/Clock as descriptive text';
  const before = JSON.stringify(input);
  const result = JSON.parse(renderContract(input)['scene.schema.json']);
  assert.equal(result.$defs.SceneEnvelope.description, input.components.schemas.SceneEnvelope.description);
  assert.equal(result.$defs.SceneEnvelope.properties.clock.$ref, '#/$defs/Clock');
  assert.equal(JSON.stringify(input), before);
});

for (const field of ['types.ts', 'scene.schema.json']) {
  test(`drift check rejects changed ${field} without rewriting it`, () => {
    const parent = new URL('../../../build/p33-sdk-linux/', import.meta.url);
    mkdirSync(parent, {recursive: true});
    const directory = mkdtempSync(new URL('contract-probe-', parent));
    try {
      const outputs = renderContract(spec);
      for (const [name, contents] of Object.entries(outputs)) writeFileSync(join(directory, name), contents);
      const changed = outputs[field] + '\n';
      writeFileSync(join(directory, field), changed);
      assert.throws(() => checkGenerated(outputs, pathToFileURL(directory + '/')), /generated_contract_drift/);
      assert.equal(readFileSync(join(directory, field), 'utf8'), changed);
    } finally { rmSync(directory, {recursive: true, force: true}); }
  });
}

for (const [name, mutate] of [
  ['external reference', schema => {schema.$ref = 'https://example.invalid/Clock';}],
  ['unknown type', schema => {schema.type = 'constructor';}],
  ['unsupported composition', schema => {schema.allOf = [{type: 'string'}];}],
  ['open object', schema => {schema.additionalProperties = true;}],
  ['unbounded fixed tuple expansion', schema => {schema.type = 'array'; schema.items = {type: 'number'}; schema.minItems = 1000000; schema.maxItems = 1000000;}],
]) {
  test(`generator rejects ${name}`, () => {
    const input = structuredClone(spec);
    mutate(input.components.schemas.Clock);
    assert.throws(() => renderContract(input), /unsupported_contract_schema/);
  });
}

for (const [name, schema] of [
  ['reference validation sibling', {$ref: '#/components/schemas/Clock', type: 'string'}],
  ['reference nested unsupported schema', {$ref: '#/components/schemas/Clock', anyOf: [{type: 'constructor'}]}],
  ['constant type conflict', {const: 'fixed', type: 'integer'}],
  ['constant validation sibling', {const: 1, type: 'integer', minimum: 2}],
  ['enum type conflict', {enum: ['fixed', 2], type: 'string'}],
  ['enum validation sibling', {enum: ['fixed'], type: 'string', pattern: '^other$'}],
  ['empty enum', {enum: [], type: 'string'}],
  ['non-array enum', {enum: 'fixed', type: 'string'}],
  ['duplicate enum', {enum: ['fixed', 'fixed'], type: 'string'}],
  ['empty union', {anyOf: []}],
  ['non-array union', {anyOf: {type: 'string'}}],
  ['union validation sibling', {anyOf: [{type: 'string'}], type: 'number'}],
]) {
  test(`generator rejects unsupported selector shape: ${name}`, () => {
    const input = structuredClone(spec);
    input.components.schemas.Probe = schema;
    assert.throws(() => renderContract(input), {message: 'unsupported_contract_schema'});
  });
}

test('supported selector annotations and scalar literals preserve declaration output', () => {
  const input = structuredClone(spec);
  Object.assign(input.components.schemas, {
    ProbeRef: {$ref: '#/components/schemas/Clock', title: 'Clock alias', description: 'description'},
    ProbeConst: {const: null, type: 'null'},
    ProbeEnum: {enum: [0, 1], type: 'integer'},
    ProbeUnion: {anyOf: [{type: 'string'}, {type: 'null'}], title: 'Nullable'},
  });
  const result = renderContract(input);
  assert.match(result['types.ts'], /export type ProbeRef = Clock;/);
  assert.match(result['types.ts'], /export type ProbeConst = null;/);
  assert.match(result['types.ts'], /export type ProbeEnum = 0 \| 1;/);
  assert.match(result['types.ts'], /export type ProbeUnion = string \| null;/);
});


test('generator selector decision uses a closed component-only schema', async () => {
  const {Ajv2020} = await import('ajv/dist/2020.js');
  const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url)));
  const validate = new Ajv2020({strict: true}).compile(read('./generator-selectors-adr.schema.json'));
  const decision = read('./generator-selectors-adr.json');
  assert.equal(validate(decision), true, JSON.stringify(validate.errors));
  assert.equal(validate({...decision, production_qualified: true}), false);
  assert.equal(validate({...decision, c4: {...decision.c4, certified: true}}), false);
});

for (const [name, schema] of [
  ['required is a string', {type: 'object', properties: {id: {type: 'string'}}, required: 'id', additionalProperties: false}],
  ['required contains duplicate', {type: 'object', properties: {id: {type: 'string'}}, required: ['id', 'id'], additionalProperties: false}],
  ['required undeclared property', {type: 'object', properties: {}, required: ['id'], additionalProperties: false}],
  ['properties missing', {type: 'object', additionalProperties: false}],
  ['properties array', {type: 'object', properties: [], additionalProperties: false}],
  ['array foreign keyword', {type: 'array', items: {type: 'string'}, properties: {hidden: {type: 'constructor'}}}],
  ['scalar foreign keyword', {type: 'string', items: {type: 'constructor'}}],
  ['boolean numeric bound', {type: 'boolean', minimum: 0}],
  ['negative variable array bound', {type: 'array', items: {type: 'number'}, minItems: -1}],
  ['fractional variable array bound', {type: 'array', items: {type: 'number'}, maxItems: 1.5}],
  ['numeric string bound', {type: 'number', maximum: '10'}],
  ['invalid string bound', {type: 'string', maxLength: -1}],
  ['invalid annotation', {type: 'string', description: 1}],
]) {
  test(`generator rejects malformed structural schema: ${name}`, () => {
    const input = structuredClone(spec);
    input.components.schemas.Probe = schema;
    assert.throws(() => renderContract(input), {message: 'unsupported_contract_schema'});
  });
}

test('generator rejects malformed contract containers with its fixed error', () => {
  for (const input of [null, {}, {components: null}, {components: {schemas: null}}, {components: {schemas: []}}]) {
    assert.throws(() => renderContract(input), {message: 'unsupported_contract_schema'});
  }
});

test('structural projection preserves optional fields and runtime-only bounds', () => {
  const input = structuredClone(spec);
  input.components.schemas.Probe = {type: 'object', additionalProperties: false, properties: {
    optional: {type: 'string', pattern: '^a$', maxLength: 1},
    required: {type: 'array', items: {type: 'integer', minimum: 0}, minItems: 1, maxItems: 3},
  }, required: ['required']};
  const output = renderContract(input);
  assert.match(output['types.ts'], /export type Probe = \{ "optional"\?: string; "required": \(number\)\[\] \};/);
  assert.deepEqual(JSON.parse(output['scene.schema.json']).$defs.Probe, input.components.schemas.Probe);
});


test('generator structure migration has a closed component-only decision', async () => {
  const {Ajv2020} = await import('ajv/dist/2020.js');
  const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url)));
  const validate = new Ajv2020({strict: true}).compile(read('./generator-structure-adr.schema.json'));
  const decision = read('./generator-structure-adr.json');
  assert.equal(validate(decision), true, JSON.stringify(validate.errors));
  assert.equal(validate({...decision, production_qualified: true}), false);
  assert.equal(validate({...decision, c4: {...decision.c4, certified: true}}), false);
});
