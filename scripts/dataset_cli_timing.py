"""Bounded fresh-process comparison probe; elapsed samples are not latency qualification."""

import argparse
import hashlib
import json
import os
import platform
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import aethron
from aethron.evaluation.proposals import run as compare
from aethron.evaluation.splits import MAX_BYTES, _parse
from aethron.evaluation.synthetic import _dataset, _json

MAX_OUTPUT = 65536
TIMEOUT = 10
STAGES = ("startup", "import_start", "import_end", "read_start", "read_end", "done")

# Trusted bootstrap: mark before application imports, then invoke the real CLI.
# The parent caps stderr and publishes only stage labels and stack-line hashes.
_SPLIT_CHILD = """import sys,time
started=time.monotonic_ns()
def mark(name):
    print('AETHRON_STAGE',name,time.monotonic_ns()-started,file=sys.stderr,flush=True)
mark('startup')
import faulthandler
faulthandler.dump_traceback_later(5)
mark('import_start')
from aethron.evaluation import splits
mark('import_end')
original=splits._read_document
def read(path):
    mark('read_start')
    try:
        return original(path)
    finally:
        mark('read_end')
splits._read_document=read
sys.argv=['splits',sys.argv[1]]
code=splits.main()
mark('done')
faulthandler.cancel_dump_traceback_later()
print('{"returncode":%d}'%code)
"""


def _diagnostics(data):
    stages, stacks, valid = [], [], True
    for line in bytes(data).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == b"AETHRON_STAGE":
            index = len(stages)
            if (
                index < len(STAGES)
                and fields[1] == STAGES[index].encode()
                and len(fields[2]) <= 11
                and fields[2].isdigit()
                and (not stages or int(fields[2]) >= stages[-1]["elapsed_ns"])
            ):
                stages.append({"stage": STAGES[index], "elapsed_ns": int(fields[2])})
            else:
                valid = False
        elif line != b"invalid_split_manifest":
            valid = False
            if line.lstrip().startswith(b'File "') and len(stacks) < 16:
                stacks.append(hashlib.sha256(line).hexdigest())
    return {
        "stages": stages,
        "stack_line_sha256": stacks,
        "stderr_sha256": hashlib.sha256(data).hexdigest(),
        "complete": valid and len(stages) == len(STAGES),
    }


def sample(command, expected, *, timeout=TIMEOUT, diagnostics=False):
    """Run a trusted argv without a shell; never return child payloads or paths."""
    if (
        type(timeout) not in (int, float)
        or not 0 < timeout <= TIMEOUT
        or type(diagnostics) is not bool
    ):
        raise ValueError("invalid_timing_input")
    start = time.monotonic()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    status, returncode = "spawn_error", None
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                with selectors.DefaultSelector() as selector:
                    for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, name)
                    status = None
                    while selector.get_map() or process.poll() is None:
                        remaining = timeout - (time.monotonic() - start)
                        if remaining <= 0:
                            status = "timeout"
                            break
                        for key, _ in selector.select(min(remaining, 0.05)):
                            data = os.read(key.fileobj.fileno(), 4096)
                            if not data:
                                selector.unregister(key.fileobj)
                                continue
                            room = MAX_OUTPUT - sum(len(value) for value in output.values())
                            output[key.data].extend(data[:room])
                            if len(data) > room:
                                status = "output_limit"
                                break
                        if status is not None:
                            break
                    if status is None:
                        returncode = process.wait()
                        status = "nonzero_exit" if returncode else "invalid_report"
                        stderr_ok = (
                            not output["stderr"]
                            if not diagnostics
                            else _diagnostics(output["stderr"])["complete"]
                        )
                        if not returncode and stderr_ok:
                            try:
                                if _json(_parse(bytes(output["stdout"]))) == _json(expected):
                                    status = "ok"
                            except (ValueError, TypeError, OverflowError):
                                pass  # Fixed status only; never disclose child payloads.
            finally:
                if process.poll() is None:
                    process.kill()
                returncode = process.wait()
    except OSError:
        status = "spawn_error"
    result = {
        "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
        "status": status,
        "returncode": returncode,
        "stdout_bytes": len(output["stdout"]),
        "stderr_bytes": len(output["stderr"]),
    }
    if diagnostics:
        result["diagnostics"] = _diagnostics(output["stderr"])
    return result


def _read(path, limit=MAX_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("invalid_timing_input")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("invalid_timing_input")
    return data


def _sources():
    root = Path(aethron.__file__).parent
    files = {"scripts/dataset_cli_timing.py": Path(__file__)}
    for path in root.rglob("*.py"):
        if len(files) >= 256:
            raise ValueError("invalid_timing_input")
        files["aethron/" + path.relative_to(root).as_posix()] = path
    hashes = {}
    total = 0
    for name, path in sorted(files.items()):
        data = _read(path, 1024 * 1024)
        total += len(data)
        if total > 16 * 1024 * 1024:
            raise ValueError("invalid_timing_input")
        hashes[name] = hashlib.sha256(data).hexdigest()
    return hashes


def run(dataset_dir, *, repetitions=3):
    """Probe the exact generated v1 test fixture; setup/reference work is untimed."""
    try:
        if type(repetitions) is not int or not 1 <= repetitions <= 5:
            raise ValueError("invalid_timing_input")
        root = Path(dataset_dir).resolve()
        pins = _dataset()[3]
        if _json(_parse(_read(root / "pins.json"))) != _json(pins):
            raise ValueError("invalid_timing_input")
        sources = _sources()
        expected = compare(
            _read(root / "manifest.json"),
            root / "blobs",
            "test",
            baseline="all",
            expected_manifest_sha256=pins["manifest_sha256"],
            expected_protocol_sha256=pins["protocol_sha256"],
            annotations=_read(root / "annotations-test.json"),
            expected_annotations_sha256=pins["annotations_sha256"]["test"],
        )
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.proposals",
            str(root / "manifest.json"),
            "--blob-dir",
            str(root / "blobs"),
            "--split",
            "test",
            "--baseline",
            "all",
            "--manifest-sha256",
            pins["manifest_sha256"],
            "--protocol-sha256",
            pins["protocol_sha256"],
            "--annotations",
            str(root / "annotations-test.json"),
            "--annotations-sha256",
            pins["annotations_sha256"]["test"],
        ]
        samples = [sample(command, expected) for _ in range(repetitions)]
        try:
            stable = _sources() == sources
        except (OSError, ValueError, TypeError, AttributeError, NotImplementedError):
            stable = False  # Preserve completed observations even if binding is lost.
        return {
            "version": 1,
            "probe": "dataset_cli_timing_v1",
            "qualified": False,
            "manifest_sha256": pins["manifest_sha256"],
            "protocol_sha256": pins["protocol_sha256"],
            "annotations_sha256": pins["annotations_sha256"]["test"],
            "reference_sha256": hashlib.sha256(_json(expected)).hexdigest(),
            "source_sha256": sources,
            "source_stable": stable,
            "python": platform.python_version(),
            "platform": platform.system() + " " + platform.machine(),
            "timeout_s": TIMEOUT,
            "samples": samples,
            "all_succeeded": stable and all(row["status"] == "ok" for row in samples),
        }
    except (OSError, ValueError, TypeError, AttributeError, NotImplementedError):
        raise ValueError("invalid_timing_input") from None


def probe_documents(*, repetitions=3):
    """Instrument owned rejection fixtures; no user paths or data are inspected."""
    try:
        if type(repetitions) is not int or not 1 <= repetitions <= 5:
            raise ValueError("invalid_timing_input")
        sources = _sources()
        manifest = _dataset()[1]
        with tempfile.TemporaryDirectory(prefix="aethron-cli-stages-") as temporary:
            root = Path(temporary)
            (root / "manifest").write_bytes(manifest)
            (root / "symlink").symlink_to(root / "manifest")
            (root / "malformed").write_bytes(b"{}")
            os.mkfifo(root / "fifo")
            samples = []
            for _ in range(repetitions):
                for kind in ("fifo", "symlink", "malformed"):
                    observation = sample(
                        [sys.executable, "-c", _SPLIT_CHILD, str(root / kind)],
                        {"returncode": 2},
                        diagnostics=True,
                    )
                    samples.append({"kind": kind, **observation})
        try:
            stable = _sources() == sources
        except (OSError, ValueError, TypeError, AttributeError, NotImplementedError):
            stable = False
        return {
            "version": 1,
            "probe": "dataset_document_stages_v1",
            "qualified": False,
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "source_sha256": sources,
            "source_stable": stable,
            "python": platform.python_version(),
            "platform": platform.system() + " " + platform.machine(),
            "timeout_s": TIMEOUT,
            "samples": samples,
            "all_succeeded": stable and all(row["status"] == "ok" for row in samples),
        }
    except (OSError, ValueError, TypeError, AttributeError, NotImplementedError):
        raise ValueError("invalid_timing_input") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", nargs="?")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--documents", action="store_true")
    args = parser.parse_args()
    try:
        if args.documents:
            if args.dataset_dir is not None:
                raise ValueError("invalid_timing_input")
            report = probe_documents(repetitions=args.repetitions)
        else:
            if args.dataset_dir is None:
                raise ValueError("invalid_timing_input")
            report = run(args.dataset_dir, repetitions=args.repetitions)
    except ValueError:
        print("invalid_timing_input", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["all_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
