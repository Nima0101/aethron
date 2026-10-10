"""Install the packed TypeScript client offline and call a real local server."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/integration"))


def run():
    output = ROOT / "build/ecosystem-phase1/node-consumer.json"
    output.unlink(missing_ok=True)
    from test_edge_http import HTTPService

    archive = ROOT / "build/ecosystem-phase1/ts-package/aethron-edge-client-example-0.1.0.tgz"
    if not archive.is_file():
        raise ValueError("pack the TypeScript client first")
    with tempfile.TemporaryDirectory(
        prefix="node-client-", dir=ROOT / "build/ecosystem-phase1"
    ) as directory:
        work = Path(directory)
        (work / "package.json").write_text(
            json.dumps(
                {
                    "name": "aethron-external-consumer",
                    "version": "0.1.0",
                    "private": True,
                    "type": "module",
                }
            )
        )
        subprocess.run(
            [
                "npm",
                "--prefix",
                str(work),
                "--cache",
                str(ROOT / "build/ecosystem-phase1/npm-cache"),
                "install",
                "--offline",
                "--ignore-scripts",
                str(archive),
            ],
            cwd=work,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        HTTPService.setUpClass()
        try:
            code = """import {observe} from 'aethron-edge-client-example';
const controller=new AbortController();let displays=0;
try { await observe(process.argv[1],process.argv[2],'bench',value=>{
 if(value.current_state!=='UNKNOWN')throw new Error('unexpected_current_state');
 if(value.label==='delayed_observation' && ++displays>=3) controller.abort();
},controller.signal); } catch(error) {
 if(!controller.signal.aborted || !(error instanceof Error) ||
    error.message!=='stream_unavailable')throw error;
}
if(displays<3)throw new Error('no observations');
console.log(JSON.stringify({
 display_callbacks:displays,current_state:'UNKNOWN',installed_client:true
}));
"""
            result = subprocess.run(
                ["node", "--input-type=module", "-e", code, HTTPService.url, HTTPService.token],
                cwd=work,
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            record = json.loads(result.stdout)
            assert record["display_callbacks"] >= 3
            output.write_text(json.dumps(record, indent=2) + "\n")
            print(result.stdout.strip())
        finally:
            HTTPService.tearDownClass()


if __name__ == "__main__":
    run()
