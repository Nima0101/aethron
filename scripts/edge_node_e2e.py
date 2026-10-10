"""Install the packed TypeScript client offline and call a real local server."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/integration"))


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            result.update(chunk)
    return result.hexdigest()


def client_inputs():
    package = ROOT / "examples/clients/typescript"
    paths = {
        path
        for path in package.iterdir()
        if path.is_file()
        and (path.suffix in {".mjs", ".ts", ".json", ".md"} or path.name == "LICENSE")
    }
    paths.update(path for path in (package / "src").rglob("*") if path.is_file())
    paths.add(ROOT / "contracts/openapi/aethron-edge-v1.json")
    return {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted(paths)}


def run():
    output = ROOT / "build/ecosystem-phase1/node-consumer.json"
    output.unlink(missing_ok=True)
    from test_edge_http import HTTPService

    package = ROOT / "examples/clients/typescript"
    inputs = client_inputs()
    cache = ROOT / "build/ecosystem-phase1/npm-cache"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="node-client-", dir=ROOT / "build/ecosystem-phase1"
    ) as directory:
        work = Path(directory)
        subprocess.run(
            ["npm", "run", "build", "--ignore-scripts", "--cache", str(cache)],
            cwd=package,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=60,
        )
        packed = subprocess.run(
            [
                "npm", "pack", "--offline", "--ignore-scripts", "--json",
                "--cache", str(cache), "--pack-destination", str(work),
            ],
            cwd=package,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        entries = json.loads(packed.stdout)
        if not isinstance(entries, list) or len(entries) != 1:
            raise ValueError("invalid_pack_result")
        filename = entries[0].get("filename") if isinstance(entries[0], dict) else None
        if (
            not isinstance(filename, str) or not filename.endswith(".tgz")
            or "/" in filename or "\\" in filename or ":" in filename
        ):
            raise ValueError("invalid_pack_result")
        archive = work / filename
        archive_sha256 = digest(archive)

        def check_inputs():
            if client_inputs() != inputs:
                raise ValueError("client_inputs_changed")
            if digest(archive) != archive_sha256:
                raise ValueError("client_archive_changed")

        check_inputs()
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
                str(cache),
                "install",
                "--offline",
                "--ignore-scripts",
                str(archive),
            ],
            cwd=work,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=30,
        )
        check_inputs()
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
        finally:
            HTTPService.tearDownClass()
        check_inputs()
        record.update(archive_sha256=archive_sha256, input_sha256=inputs)
        output.write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record))


if __name__ == "__main__":
    run()
