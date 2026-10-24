import assert from 'node:assert/strict';
import {test} from 'node:test';
import {cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
const repository=fileURLToPath(new URL('../../',import.meta.url));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');

// Run the real build entry point and real esbuild against copied compiled modules.
// Compilation alone is stubbed: these cases isolate post-compilation provenance.
function fixture(mode,check) {
 const parent=join(repository,'build/p33-sdk-linux');mkdirSync(parent,{recursive:true});
 const root=mkdtempSync(join(parent,'browser-provenance-')),operator=join(root,'examples/operator');
 try {
  for(const relative of ['examples/operator/dist','examples/operator/src','examples/clients/typescript/dist']) {
   cpSync(join(repository,relative),join(root,relative),{recursive:true});
  }
  for(const name of ['build-browser.mjs','help-inventory.mjs']) cpSync(join(repository,'examples/operator',name),join(operator,name));
  cpSync(join(repository,'LICENSE'),join(root,'LICENSE'));
  const dependencies=join(root,'examples/clients/typescript/node_modules');mkdirSync(dependencies,{recursive:true});
  symlinkSync(join(repository,'examples/clients/typescript/node_modules/typescript'),join(dependencies,'typescript'),'junction');
  for(const name of ['package.json','LICENSE','dist/runtime/ucs2length.js']) {
   const path=join(dependencies,'ajv',name);mkdirSync(join(path,'..'),{recursive:true});
   cpSync(join(repository,'examples/clients/typescript/node_modules/ajv',name),path);
  }
  const esbuild=join(operator,'node_modules/esbuild');mkdirSync(esbuild,{recursive:true});
  writeFileSync(join(esbuild,'package.json'),JSON.stringify({type:'module',exports:'./index.js'}));
  cpSync(join(repository,'examples/operator/node_modules/esbuild/LICENSE.md'),join(esbuild,'LICENSE.md'));
  const target=join(operator,'dist/client.js'),original=readFileSync(target);
  const real=pathToFileURL(join(repository,'examples/operator/node_modules/esbuild/lib/main.js')).href;
  writeFileSync(join(esbuild,'index.js'),`
   import {build as actualBuild,version} from ${JSON.stringify(real)};
   import {appendFileSync,readFileSync,writeFileSync} from 'node:fs';
   export {version};
   export async function build(options) {
    const result=await actualBuild(options);
    if(${JSON.stringify(mode)}==='compiled-change')appendFileSync(${JSON.stringify(target)},'\\n// changed after bundling\\n');
    if(${JSON.stringify(mode)}==='source-change-after-bundle'){
     const path=${JSON.stringify(join(operator,'src/connection.ts'))};
     writeFileSync(path,readFileSync(path,'utf8').replace('The application has not enabled this connection.','Changed guidance after bundling.'));
    }
    return result;
   }
  `);
  const bin=join(root,'bin');mkdirSync(bin);
  writeFileSync(join(bin,'npm'),`#!${process.execPath}
   const fs=require('node:fs');
   if(${JSON.stringify(mode)}==='source-change'&&process.argv.at(-1)==='examples/operator'){
    const name=${JSON.stringify(join(operator,'src/connection.ts'))};
    fs.writeFileSync(name,fs.readFileSync(name,'utf8').replace('The application has not enabled this connection.','Changed guidance during compilation.'));
   }
  `,{mode:0o755});
  const result=spawnSync(process.execPath,['build-browser.mjs'],{cwd:operator,encoding:'utf8',timeout:30000,maxBuffer:1024*1024,
   env:{...process.env,PATH:bin+':'+process.env.PATH}});
  assert.equal(result.error,undefined,result.error?.message);
  check({root,operator,result,original,target});
 }finally{rmSync(root,{recursive:true,force:true});}
}
test('browser manifest hashes the module bytes actually consumed by esbuild',()=>{
 fixture('compiled-change',({operator,result,original,target})=>{
  assert.equal(result.status,0,result.stdout+result.stderr);
  assert.notEqual(hash(readFileSync(target)),hash(original),'controlled mutation must occur after bundling');
  const manifest=JSON.parse(readFileSync(join(operator,'browser-dist/manifest.json')));
  assert.equal(manifest.inputs['examples/operator/dist/client.js'],hash(original));
 });
});
for(const mode of ['source-change','source-change-after-bundle'])test(`browser build withdraws artifacts on ${mode}`,()=>{
 fixture(mode,({operator,result})=>{
  assert.notEqual(result.status,0,'source drift must fail the build');
  assert.match(result.stderr,/changed_help_source/);
  for(const name of ['manifest.json','aethron-observation.mjs','STATE-HELP.json','ACTION-HELP.json','LICENSE','AJV-LICENSE','ESBUILD-LICENSE']) {
   assert.equal(existsSync(join(operator,'browser-dist',name)),false,name);
  }
 });
});
test('stable browser inputs retain the existing module and help contracts',()=>{
 fixture('stable',({operator,result})=>{
  assert.equal(result.status,0,result.stdout+result.stderr);
  const dir=join(operator,'browser-dist'),manifest=JSON.parse(readFileSync(join(dir,'manifest.json')));
  assert.equal(manifest.format,'aethron-browser-component-v1');assert.equal(Object.keys(manifest.inputs).length,12);
  for(const [name,digest] of Object.entries(manifest.artifacts))assert.equal(hash(readFileSync(join(dir,name))),digest);
  for(const name of ['STATE-HELP.json','ACTION-HELP.json'])assert.equal(JSON.parse(readFileSync(join(dir,name))).module_sha256,hash(readFileSync(join(dir,'aethron-observation.mjs'))));
 });
});
