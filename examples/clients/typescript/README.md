# AETHRON TypeScript observation example

This local package is an executed Node client example, not a published enterprise SDK. It uses the generated OpenAPI types plus strict AJV runtime validation. Node 22+ is the prepared CI target; run the locked package tests before using another runtime.

```sh
npm ci --ignore-scripts
npm test
npm pack
```

Install the resulting `.tgz` in an external Node project. Load an owner-only token file locally; do not put it in a URL or persistent browser storage:

```js
import {readFile} from 'node:fs/promises';
import {observe} from 'aethron-edge-client-example';

const token = (await readFile('token', 'utf8')).trim();
const controller = new AbortController();
process.once('SIGINT', () => controller.abort());
await observe('http://127.0.0.1:8765', token, 'bench', state => {
  console.log(state.label, state.current_state, state.sources);
}, controller.signal);
```

The named profile uses the `warn` contract in this example. Python's example accepts the other contract names explicitly; application SDKs should preserve the schema enum. `observe()` releases its viewer handle when aborted; the supervisor continues processing. An independent 20ms client timer expires stalled observations. Without a measured transit bound, current state remains UNKNOWN and observations are labeled delayed.

The implementation uses authenticated fetch streaming rather than EventSource token URLs. The candidate server rejects Origin headers and cross-origin access; the executed evidence is Node on loopback. Browser deployment needs a separately reviewed same-origin/authenticated TLS integration, and is not claimed from the Node test. No CDN is required.

From the repository root, `scripts/edge_node_e2e.py` installs the packed artifact outside this package and tests it against a real server. The server and Python client instructions are in [edge usage](../../../docs/usage-edge.md).
