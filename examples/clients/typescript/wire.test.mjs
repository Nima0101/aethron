import assert from 'node:assert/strict';
import {test} from 'node:test';
import {WireDecoder} from './dist/wire.js';

function decode(text,stride) {
  const decoder=new WireDecoder(),bytes=new TextEncoder().encode(text),events=[];
  try {
    for(let offset=0;offset<bytes.length;offset+=stride)events.push(...decoder.feed(bytes.subarray(offset,offset+stride)));
    decoder.finish();return events;
  } finally {decoder.clear();}
}
test('bounded JSON lexical and chunk parity corpus',t=>{
  const strings=['', 'quote"slash\\', 'line\nreturn\rtab\t', '{}[],:', 'é😀', '\\u0073equence'];
  let cases=0;
  for(const string of strings)for(const stride of [1,2,3,7,64,65536]) {
    const value={string,nested:[{same:1},{same:2}],values:[null,true,false,0,-1,1.25,1e-20]};
    const frame=`data: ${JSON.stringify(value)}\n\n`;
    assert.deepEqual(decode(frame,stride),[{name:undefined,value}]);cases++;
  }
  t.diagnostic(`${cases} deterministic valid lexical/chunk cases`);
});
test('nested duplicates, malformed grammar and excessive depth fail closed',()=>{
  const invalid=['{"a":[{"x":0,"x":1}]}','{"a":1,"\\u0061":2}',
    '{"a":0}{}','{"a":"unterminated}', '{"a":01}', '{"a":NaN}',
    '{"a":1,}', '[]','null', '{"a":'+ '['.repeat(8)+'0'+']'.repeat(8)+'}'];
  for(const json of invalid)for(const stride of [1,7,65536]) {
    assert.throws(()=>decode(`data: ${json}\n\n`,stride),{message:'invalid_event'});
  }
});
test('byte-invalid UTF-8 and unsupported history fields fail closed',()=>{
  const decoder=new WireDecoder();
  try {assert.throws(()=>[...decoder.feed(Uint8Array.of(0xc3,0x28,10,10))],{message:'invalid_event'});}
  finally {decoder.clear();}
  for(const prefix of ['id: old\n','retry: 1\n','event: scene\nevent: scene\n','unknown: value\n']) {
    assert.throws(()=>decode(prefix+'data: {}\n\n',1),{message:'invalid_event'});
  }
});
test('comments do not dispatch state and supported multiline data joins once',()=>{
  assert.deepEqual(decode(': heartbeat\r\n\r\n',1),[]);
  assert.deepEqual(decode('data: {\r\ndata: "a": 1}\r\n\r\n',1),[{name:undefined,value:{a:1}}]);
});
