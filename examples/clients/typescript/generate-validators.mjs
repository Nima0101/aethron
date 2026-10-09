import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {Ajv2020} from 'ajv/dist/2020.js';
import standalone from 'ajv/dist/standalone/index.js';

// Generate from the same versioned bundle used by the runtime compiler before
// migration. Never coerce, remove additional properties, or supply defaults.
const schema = JSON.parse(readFileSync(new URL('./src/scene.schema.json', import.meta.url), 'utf8'));
const ajv = new Ajv2020({strict: true, code: {source: true}});
ajv.addSchema(schema, 'scene');
ajv.addSchema({...schema, $ref: '#/$defs/HealthEvent'}, 'health');
const code = standalone(ajv, {validateScene: 'scene', validateHealth: 'health'});
mkdirSync(new URL('./dist/', import.meta.url), {recursive: true});
writeFileSync(new URL('./dist/validators.cjs', import.meta.url), code);
