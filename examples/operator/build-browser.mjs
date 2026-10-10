import {readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const root=fileURLToPath(new URL('../../',import.meta.url));
const output=resolve(root,'examples/operator/browser-dist');
const names=['manifest.json','aethron-observation.mjs','LICENSE','AJV-LICENSE','ESBUILD-LICENSE'];
mkdirSync(output,{recursive:true});
// Invalidate the previous component before any compiler or dependency can fail.
for(const name of names) rmSync(resolve(output,name),{force:true});
try {
  for(const prefix of ['examples/clients/typescript','examples/operator']) {
    execFileSync('npm',['run','build','--prefix',prefix],{cwd:root,stdio:'inherit',timeout:60000});
  }
  const {build,version}=await import('esbuild');
  const result=await build({
    absWorkingDir:root,entryPoints:['examples/operator/dist/browser.js'],
    outfile:'examples/operator/browser-dist/aethron-observation.mjs',
    bundle:true,platform:'browser',format:'esm',target:'es2022',
    write:false,metafile:true,sourcemap:false,minify:false,legalComments:'inline',
    logLevel:'silent',
  });
  const allowed=new Set([
    'examples/operator/dist/browser.js','examples/operator/dist/presenter.js','examples/operator/dist/client.js',
    'examples/operator/dist/panel.js','examples/operator/dist/lifecycle.js','examples/operator/dist/connection.js',
    'examples/clients/typescript/dist/client.js','examples/clients/typescript/dist/wire.js',
    'examples/clients/typescript/dist/session.js','examples/clients/typescript/dist/validators.cjs',
    'examples/clients/typescript/node_modules/ajv/dist/runtime/ucs2length.js',
  ]);
  const inputs=Object.keys(result.metafile.inputs).sort();
  if(inputs.some(name=>!allowed.has(name)) || inputs.length!==allowed.size ||
     result.outputFiles.length!==1 || result.warnings.length!==0 ||
     Object.values(result.metafile.outputs).some(item=>item.imports.length!==0)) {
    throw new Error('unsupported_browser_dependency_graph');
  }
  const artifacts={
    'aethron-observation.mjs':result.outputFiles[0].contents,
    LICENSE:readFileSync(resolve(root,'LICENSE')),
    'AJV-LICENSE':readFileSync(resolve(root,'examples/clients/typescript/node_modules/ajv/LICENSE')),
    'ESBUILD-LICENSE':readFileSync(new URL('./node_modules/esbuild/LICENSE.md',import.meta.url)),
  };
  const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
  const manifest={format:'aethron-browser-component-v1',builder:{name:'esbuild',version},
    qualified_browser:false,external_imports:[],
    inputs:Object.fromEntries(inputs.map(name=>[name,hash(readFileSync(resolve(root,name)))])),
    artifacts:Object.fromEntries(Object.entries(artifacts).map(([name,bytes])=>[name,hash(bytes)])),
  };
  for(const [name,bytes] of Object.entries(artifacts)) writeFileSync(resolve(output,name),bytes);
  // The manifest is the last file: absence means the build is incomplete.
  writeFileSync(resolve(output,'manifest.json'),`${JSON.stringify(manifest,null,2)}\n`);
  console.log(`Browser component: ${result.outputFiles[0].contents.length} bytes; ${inputs.length} bundled inputs; no external imports`);
} catch(error) {
  for(const name of names) rmSync(resolve(output,name),{force:true});
  throw error;
}
