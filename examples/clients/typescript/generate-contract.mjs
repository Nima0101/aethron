import {readFileSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {Ajv2020} from 'ajv/dist/2020.js';

const prefix = '#/components/schemas/';
const primitives = new Map(Object.entries({string: 'string', number: 'number', integer: 'number', boolean: 'boolean', null: 'null'}));
const keywords = new Set(['$ref', 'additionalProperties', 'anyOf', 'const', 'enum',
  'exclusiveMinimum', 'items', 'maxItems', 'maxLength', 'maximum', 'minItems',
  'minimum', 'pattern', 'properties', 'required', 'title', 'description', 'type']);
const canonical = value => Array.isArray(value) ? value.map(canonical) :
  value && typeof value === 'object' ? Object.fromEntries(Object.entries(value)
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, child]) => [key, canonical(child)])) : value;
const invalid = () => { throw new Error('unsupported_contract_schema'); };
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const schemaChecker = new Ajv2020({strict: true});

// Deliberately supports only the checked API-v1 schema vocabulary, not all OpenAPI.
export function renderContract(spec) {
  if (!record(spec) || !record(spec.components) || !record(spec.components.schemas)) invalid();
  const schemas = spec.components.schemas;
  // Validate keyword value shapes before emitting declarations. This does not
  // resolve schema references or fetch anything; the local subset checks below
  // still own supported vocabulary and reference policy.
  if (!schemaChecker.validateSchema({$defs: schemas})) invalid();
  const names = Object.keys(schemas);
  if (!names.includes('SceneEnvelope') || names.some(name => !/^[A-Z][A-Za-z0-9_]*$/.test(name))) invalid();
  const reference = ref => {
    if (typeof ref !== 'string' || !ref.startsWith(prefix) || !names.includes(ref.slice(prefix.length))) invalid();
    return ref.slice(prefix.length);
  };
  const literal = value => {
    if (value !== null && !['string', 'boolean', 'number'].includes(typeof value)) invalid();
    if (typeof value === 'number' && !Number.isFinite(value)) invalid();
    return JSON.stringify(value);
  };
  const type = schema => {
    if (!schema || typeof schema !== 'object' || Array.isArray(schema) ||
        Object.keys(schema).some(key => !keywords.has(key))) invalid();
    // Selector branches must not silently discard validation siblings. This is
    // a closed declaration subset, not a general JSON Schema intersection engine.
    const only = keys => {
      if (Object.keys(schema).some(key => !['title', 'description', ...keys].includes(key))) invalid();
    };
    const scalar = value => {
      const rendered = literal(value);
      if ('type' in schema && !(schema.type === 'null' ? value === null :
          schema.type === 'integer' ? Number.isInteger(value) :
          ['string', 'number', 'boolean'].includes(schema.type) && typeof value === schema.type)) invalid();
      return rendered;
    };
    if ('$ref' in schema) {
      only(['$ref']);
      return reference(schema.$ref);
    }
    if ('const' in schema) {
      only(['const', 'type']);
      return scalar(schema.const);
    }
    if ('enum' in schema) {
      only(['enum', 'type']);
      if (!Array.isArray(schema.enum) || schema.enum.length === 0) invalid();
      const values = schema.enum.map(scalar);
      if (new Set(values).size !== values.length) invalid();
      return values.join(' | ');
    }
    if ('anyOf' in schema) {
      only(['anyOf']);
      if (!Array.isArray(schema.anyOf) || schema.anyOf.length === 0) invalid();
      return schema.anyOf.map(type).join(' | ');
    }
    if (schema.type === 'array') {
      only(['type', 'items', 'minItems', 'maxItems']);
      const item = type(schema.items);
      if (schema.minItems !== undefined && schema.minItems === schema.maxItems) {
        if (!Number.isInteger(schema.minItems) || schema.minItems < 0 || schema.minItems > 32) invalid();
        return '[' + Array(schema.minItems).fill(item).join(', ') + ']';
      }
      return '(' + item + ')[]';
    }
    if (schema.type === 'object') {
      only(['type', 'properties', 'required', 'additionalProperties']);
      if (schema.additionalProperties !== false || !record(schema.properties) ||
          schema.required?.some(key => !Object.hasOwn(schema.properties, key))) invalid();
      return '{ ' + Object.entries(schema.properties).map(([key, child]) =>
        JSON.stringify(key) + (schema.required?.includes(key) ? '' : '?') + ': ' + type(child)).join('; ') + ' }';
    }
    if (schema.type === 'string') only(['type', 'pattern', 'maxLength']);
    else if (schema.type === 'number' || schema.type === 'integer') only(['type', 'minimum', 'maximum', 'exclusiveMinimum']);
    else only(['type']);
    return primitives.get(schema.type) ?? invalid();
  };
  const bundleSchema = schema => {
    const result = {...schema};
    if ('$ref' in result) result.$ref = '#/$defs/' + reference(result.$ref);
    if (result.properties) result.properties = Object.fromEntries(Object.entries(result.properties).map(([k, v]) => [k, bundleSchema(v)]));
    if (result.items) result.items = bundleSchema(result.items);
    if (result.anyOf) result.anyOf = result.anyOf.map(bundleSchema);
    return result;
  };
  const types = '// Generated by generate-contract.mjs; do not hand edit.\n' +
    names.map(name => 'export type ' + name + ' = ' + type(schemas[name]) + ';').join('\n') + '\n';
  const bundle = {$ref: '#/$defs/SceneEnvelope', $defs: Object.fromEntries(names.map(name => [name, bundleSchema(schemas[name])]))};
  return {'types.ts': types, 'scene.schema.json': JSON.stringify(canonical(bundle), null, 2) + '\n'};
}

export function checkGenerated(outputs, directory) {
  for (const [name, contents] of Object.entries(outputs)) {
    if (readFileSync(new URL(name, directory), 'utf8') !== contents) throw new Error('generated_contract_drift');
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const mode = process.argv.slice(2);
  if (mode.length !== 1 || !['--check', '--write'].includes(mode[0])) throw new Error('expected_check_or_write');
  const outputs = renderContract(JSON.parse(readFileSync(new URL('../../../contracts/openapi/aethron-edge-v1.json', import.meta.url), 'utf8')));
  const directory = new URL('./src/', import.meta.url);
  if (mode[0] === '--check') checkGenerated(outputs, directory);
  else for (const [name, contents] of Object.entries(outputs)) writeFileSync(new URL(name, directory), contents);
}
