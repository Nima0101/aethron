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
