# ROS image acquisition v1 focused evidence

Local Linux Python 3.13.5 process-boundary fixtures only. No Docker daemon,
container, image download, registry login or credential provisioning was used.

## Retained counterexamples

- Before implementation, all seven initial acquisition tests failed because
  the helper was absent.
- The inspection-timeout regression failed after the initial implementation:
  `exit_code` incorrectly retained `0` from a successful pull. Resetting the
  stage exit code before each subprocess now preserves `null` on timeout.
- The P2 handoff reported unauthenticated registry rate limiting in
  [hosted run 37992870352](https://github.com/Nima0101/aethron/actions/runs/37992870352).
  It is not independently reproduced locally or erased by this change.
- Initial Bandit output reported subprocess import and an environment variable
  name as low-severity findings. Narrow suppressions record the fixed CLI/no-shell
  boundary and that the string is a variable name, not a credential. Arbitrary
  command input is not exposed.

## Focused results

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests/integration -p test_ros_image_acquisition.py -v` | 8 PASS |
| `python -m unittest discover -s tests/integration -p test_ros_check_output.py -v` | 4 PASS |
| Ruff check and format check for helper and its tests | PASS |
| Bandit for `scripts/edge_ros_image_v1.py` | PASS with documented narrow suppressions |
| Workflow YAML parsing and diff whitespace check | PASS |

Fixtures cover exact image/platform arguments, anonymous versus authenticated
operation, stdin-only token transfer, credential-directory cleanup, partial
credential rejection, login failure without fallback, rate-limit receipt without
raw output, platform mismatch, timeout, missing CLI, and refusal to overwrite
existing evidence. The existing DDS output tests preserve failed logs and reject
evidence-directory reuse and symlinks.

Hosted tests must supply real Docker/digest/platform evidence. Optional secrets
are exposed only to manual dispatch on protected main, never PR jobs or dispatch
on another branch. Missing secrets leave anonymous acquisition subject to the
original rate limit. Authentication and registry availability remain unqualified;
neither image acquisition nor these fixtures qualify DDS, SITL or hardware.
