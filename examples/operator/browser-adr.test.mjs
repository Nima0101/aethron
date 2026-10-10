import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {Ajv2020} from '../clients/typescript/node_modules/ajv/dist/2020.js';

test('browser component decision has a closed ADR and four architecture views',()=>{
  const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
  const validate=new Ajv2020({strict:true}).compile(read('./browser-adr.schema.json'));
  const adr=read('./browser-adr.json');assert.equal(validate(adr),true,JSON.stringify(validate.errors));
  assert.equal(validate({...adr,qualified:true}),false);
  assert.equal(validate({...adr,c4:{...adr.c4,unreviewed:'claim'}}),false);
});
