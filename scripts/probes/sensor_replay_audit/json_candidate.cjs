// Bounded admission counterexamples for a stock Node JSON.parse replacement.
// This is not a complete replay implementation or a claim about all JS parsers.
'use strict';
const vectors = [
  ['duplicate', '{"sequence":1,"sequence":2}'],
  ['escaped_duplicate', '{"sequence":1,"seq\\u0075ence":2}'],
  ['nested_duplicate', '{"layout":{"width":1,"width":2}}'],
  ['int64', '{"acquisition_ns":9223372036854775807}'],
];
console.log(JSON.stringify({node:process.version, cases:vectors.map(([name, text]) => {
  try {
    const value = JSON.parse(text);
    return {name, accepted:true, serialized:JSON.stringify(value),
      exact_int64:name === 'int64' ? BigInt(value.acquisition_ns) === 9223372036854775807n : null};
  } catch { return {name, accepted:false}; }
})}, null, 2));
