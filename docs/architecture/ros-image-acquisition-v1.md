# ROS CI image acquisition v1

The P2 handoff reported Docker Hub rate limiting before DDS execution in
[run 37992870352](https://github.com/Nima0101/aethron/actions/runs/37992870352).
Later robotics head `9edd575` DDS checks passed; this does not erase the earlier
acquisition failure or establish repeatable registry availability.

## Decision, 2026-10-10

Requirements: hosted Linux acquisition only, unchanged frozen image digest and
ARM64 platform, optional credentials without persistence/exposure, bounded
subprocesses, retained failure evidence, and no acquisition failure promoted to
DDS success. No local Docker execution is part of the focused development tests.

[Docker pull](https://docs.docker.com/reference/cli/docker/image/pull/) supports
digest/platform selection; [Docker login](https://docs.docker.com/reference/cli/docker/login/)
supports password stdin. [Google's Docker Hub cache guidance](https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images)
requires daemon configuration and does not guarantee cached availability; a direct
mirror-reference substitution is not adopted. No privileged daemon changes or
unprovisioned registry are assumed.

Choose Python stdlib [subprocess](https://docs.python.org/3.13/library/subprocess.html),
[tempfile](https://docs.python.org/3.13/library/tempfile.html) and JSON for a small orchestration helper.
Shell can invoke the same CLI but complicates structured failure receipts and
credential cleanup across timeout/error branches. A new native program or cloud
SDK would add build/dependency boundaries without improving digest enforcement,
which remains Docker's responsibility. Selection follows these requirements,
not language incumbency; no SDK dependency is added.

## Contract

`python scripts/edge_ros_image_v1.py --out PATH` creates a fresh evidence directory
and writes a version 1 `result.json` before attempting Docker. Existing
directories/symlinks are refused. The only image is the frozen `ros@sha256:8f687fdf084482819aa7dab48c3887331edd0d3687b219951fdb66c418316ab1`,
with platform `linux/arm64`. No tags, alternate digests or caller registry inputs.

Optional `AETHRON_DOCKERHUB_USERNAME` and `AETHRON_DOCKERHUB_TOKEN` must both be
nonempty; a partial/invalid pair fails before Docker. Authentication failure
never falls back to anonymous. Login uses stdin, a temporary mode 0700 Docker
config directory, and a child environment with both credential variables removed.
No credential values or raw Docker output enter the receipt. Temporary config
and command output are removed on normal exit, handled errors and timeouts;
abrupt host/process termination is outside the cleanup guarantee.

The helper supports anonymous acquisition when neither variable is present.
It does not import the operator's default Docker config or `DOCKER_AUTH_CONFIG`.
A mode 0600 config with one empty Hub auth entry prevents automatic discovery of
host credential helpers: Docker's [config loader](https://github.com/docker/cli/blob/master/cli/config/config.go)
uses that discovery only when [ContainsAuth](https://github.com/docker/cli/blob/master/cli/config/configfile/file.go)
is false. This source review and process-boundary fixture do not qualify every
Docker CLI release; hosted execution still needs to verify the installed CLI.
Login has a 30 s timeout, pull 180 s, platform inspection 15 s; no retries.
The Docker daemon and executable
are trusted. Docker validates the digest, and inspection must confirm
`linux/arm64` before the receipt becomes `acquired`. Success proves acquisition
only; the existing offline DDS runner still performs its own checks.

Failures retain stage, fixed reason and optional exit code, not raw diagnostic
text. Rate-limit text in the first 64 KiB of pull output is classified as
`rate_limited`; other output, including any credential echo, is discarded.
Output is captured in a temporary file; the read limit is not a bound on that
file's size. The quiet, trusted Docker CLI and stage timeouts limit this exposure.
An unavailable daemon/CLI, failed login/pull/inspection, wrong platform or timeout
leaves `state=failed`; no container is started by this helper.

Workflow credentials are available only for manual dispatch of protected main,
using repository secrets `AETHRON_DOCKERHUB_USERNAME` and
`AETHRON_DOCKERHUB_TOKEN` with matching environment names.
PR jobs always run anonymously, including same-repository PRs. Administrator
provisioning of the two Docker Hub secrets is an external configuration gate;
neither secret availability nor authenticated hosted success is claimed here.
The initial failure and this limitation remain reportable until hosted evidence
exists. Authentication increases applicable limits; it does not promise immunity
from registry throttling or outages.
