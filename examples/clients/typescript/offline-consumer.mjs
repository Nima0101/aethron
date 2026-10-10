import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';

const invalid=()=>{throw new Error('invalid_consumer_lock');};
const record=value=>value&&typeof value==='object'&&!Array.isArray(value);
const canonical=value=>JSON.stringify(Object.entries(value??{}).sort(([a],[b])=>a<b?-1:a>b?1:0));
/** Build/test adapter for the committed npm lock-v3 runtime graph. npm ci remains
 * responsible for validating dependency satisfaction; this is not a resolver. */
export function renderOfflineConsumer(manifest,lock,filename,archive) {
  if(typeof filename!=='string'||!/^[-a-zA-Z0-9_.]+\.tgz$/.test(filename)||filename.startsWith('.'))throw new Error('invalid_consumer_archive');
  if(!record(manifest)||!record(lock)||lock.lockfileVersion!==3||!record(lock.packages)||
     !record(lock.packages[''])||!/^[-a-z0-9]+$/.test(manifest.name??'')||
     typeof manifest.version!=='string'||lock.packages[''].name!==manifest.name||lock.packages[''].version!==manifest.version||
     canonical(manifest.dependencies)!==canonical(lock.packages[''].dependencies)||manifest.optionalDependencies||manifest.peerDependencies)invalid();
  const runtime=Object.fromEntries(Object.entries(lock.packages).filter(([key,value])=>key&&value.dev!==true).map(([key,value])=>{
    if(!/^node_modules\/(?:@[-a-z0-9]+\/)?[-a-z0-9]+$/.test(key)||!record(value)||value.link||value.optional||value.peer||
       typeof value.version!=='string'||typeof value.resolved!=='string'||!value.resolved.startsWith('https://registry.npmjs.org/')||
       typeof value.integrity!=='string'||!/^sha512-[A-Za-z0-9+/]{86}==$/.test(value.integrity))invalid();
    return [key,structuredClone(value)];
  }));
  const reference=`file:${filename}`;
  const consumer={name:'aethron-external-consumer',version:'0.1.0',private:true,type:'module',dependencies:{[manifest.name]:reference}};
  const packages={'':{name:consumer.name,version:consumer.version,dependencies:consumer.dependencies},...runtime,
    [`node_modules/${manifest.name}`]:{version:manifest.version,resolved:reference,
      integrity:`sha512-${createHash('sha512').update(archive).digest('base64')}`,
      license:manifest.license,dependencies:structuredClone(manifest.dependencies??{})}};
  return {manifest:consumer,lock:{name:consumer.name,version:consumer.version,lockfileVersion:3,requires:true,packages}};
}

if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url) {
  const [directory,filename,...extra]=process.argv.slice(2);
  if(!directory||!filename||extra.length)throw new Error('expected_consumer_directory_and_archive');
  // Validate filename before using it to read an archive.
  if(!/^[-a-zA-Z0-9_.]+\.tgz$/.test(filename)||filename.startsWith('.'))throw new Error('invalid_consumer_archive');
  const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
  const result=renderOfflineConsumer(read('./package.json'),read('./package-lock.json'),filename,readFileSync(join(directory,filename)));
  writeFileSync(join(directory,'package.json'),JSON.stringify(result.manifest,null,2)+'\n');
  writeFileSync(join(directory,'package-lock.json'),JSON.stringify(result.lock,null,2)+'\n');
}
