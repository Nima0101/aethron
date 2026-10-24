# P16 package-input workflow review v3

Baseline `65dc44e1950c798284af79ed6616f594070763d8`, reviewed 2026-10-10.
Decision: **KEEP native workflow configuration; FIX omitted build/import triggers and
sensor-consumer source-manifest inclusion**. Runtime and frozen contracts are unchanged.

The sensor-conformance bridge matches its parent, eight recorded file hashes and noreply
identity, and is published on PR 35 at this baseline. Fresh source inspection of the task,
federation and inbox modules confirms their documented caller-provided trust/time and
non-authorizing boundaries; 43 focused interop methods pass. This is not full-phase or
whole-audit completion.

## Requirements and technology decision

The component schedules existing hosted package checks when their build/import inputs
change. It must preserve jobs, pinned actions, permissions and branch restrictions.
There is no native computation, throughput SLA or device timing requirement. GitHub's
[workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
provides path filtering directly in YAML. KEEP that native representation for this one
workflow: the missing dependency paths can be expressed directly without generated files.

[Dhall](https://dhall-lang.org/) is a credible typed configuration language outside the
current YAML/Python component, and [CUE](https://cuelang.org/docs/concept/how-cue-enables-data-validation/)
can validate declarative configuration. Either could help a fleet of generated workflows,
but both still need emitted GitHub YAML and do not infer this project's build/import
inputs automatically. No shared generation or configuration computation requirement
establishes a material migration win here. This decision does not rely on tooling
installation, familiarity, rewrite cost or an unmeasured performance ranking.

[Setuptools configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)
and the actual `pyproject.toml`, `setup.py` and `MANIFEST.in` establish the current package
boundary. KEEP the existing standard backend; manifest inclusion is the missing action.
No package-wide backend change is justified by this omission.

## Findings and correction

Both event filters missed `setup.py`, `MANIFEST.in`, `README.md`, `LICENSE`, `NOTICE` and
package initialization. `aethron.__init__` imports `core`, which imports `actions`,
`features` and `schema`; the feature module also names packaged model data. The filter
now covers `aethron/**` and six root inputs, including `setup.cfg` if introduced later.
This conservatively covers future package imports without pretending to establish whole
repository dependency closure. Peer runtime code and peer workflows are unchanged.

The previous sensor-conformance slice added an optional requirements file but did not
include it in the source-distribution manifest. One explicit include now selects it.
This correction does not change root runtime dependencies or install a sensor service.

A bounded probe using PyYAML BaseLoader, positive path-pattern matching and Setuptools
FileList found 24 uncovered sample paths across two event filters and the omitted
requirements file. The first probe used a prospective model filename; a corrected RED
run uses the actual `aethron/models/rules.json` and retains the same failures. `setup.cfg`
remains an explicitly prospective build input. Separate assertions confirmed the trigger
and manifest defects. After the change all 24 path checks and requirement selection pass.
This probe tests the workflow's positive pattern subset, not GitHub's full changed-file
selection algorithm; no remote event dispatch is claimed.

Parsed workflow comparison confirms that jobs, permissions and branch restrictions are
identical. Actionlint and whitespace checks pass. Five existing installed-source tests
and 43 interop tests pass with no skips. Initial host namespace/fork EAGAIN read failures
were retried successfully; they are not implementation test failures.

No new wheel/sdist archive, clean clone, full repository matrix or hosted run was made.
FileList checks selection by the root requirements include directives; it is not evidence
that an archive was built or published. Earlier archives are not retroactively changed.

[Source-bound result record](p16-packaging-inputs-v3-results.json) retains before/after
path controls and limits. Reproduce selection with Setuptools `FileList`, setting its
available filenames from root `requirements*` files and applying the `include requirements`
directives from `MANIFEST.in`. Reproduce workflow validation with
`actionlint .github/workflows/aethron-passports.yml`; inspect `on.pull_request.paths` and
`on.push.paths` for the 12 sample filenames in the result record.
