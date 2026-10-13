"""Repository-selection preflight for developer evidence checkers."""

import subprocess
import threading
import time

# Per-command developer-tool waiting budget, not a product latency threshold.
GIT_COMMAND_TIMEOUT_SECONDS = 30
GIT_OUTPUT_MAX_BYTES = 16 * 1024 * 1024

REPOSITORY_OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)


def require_default_git_context(environment):
    """Reject these explicit overrides, including empty values; never echo them.

    This is not environment isolation: Git configuration, executable selection
    and the stable checkout remain trusted. The caller's mapping is unchanged.
    """
    if any(name in environment for name in REPOSITORY_OVERRIDES):
        raise ValueError("git_repository_override")


def git_output(args, *, cwd, timeout, env=None):
    """Read capped stdout; discard diagnostics and reject every incomplete result.

    Trusted direct Git children only, not process-tree containment. A descendant
    retaining stdout can outlive cleanup with a daemon reader until it closes
    the pipe. Process creation and direct-child reaping have no hard time bound.
    """
    limit = GIT_OUTPUT_MAX_BYTES
    data = bytearray()
    errors = []
    done = threading.Event()
    stop = threading.Event()
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )
    deadline = time.monotonic() + timeout

    def read():
        try:
            with process.stdout as stream:
                while not stop.is_set():
                    chunk = stream.read(min(65536, limit - len(data) + 1))
                    if not chunk:
                        break
                    if len(data) + len(chunk) > limit:
                        raise ValueError("git_output_limit")
                    data.extend(chunk)
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()

    started = False
    try:
        reader = threading.Thread(target=read, name="git-output", daemon=True)
        reader.start()
        started = True
        if not done.wait(max(0, deadline - time.monotonic())):
            raise subprocess.TimeoutExpired(args, timeout)
        if errors:
            raise errors[0]
        process.wait(timeout=max(0, deadline - time.monotonic()))
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, args)
        return bytes(data)
    finally:
        stop.set()
        if process.poll() is None:
            process.kill()
        process.wait()
        if started:
            reader.join(timeout=1)
        else:
            process.stdout.close()
