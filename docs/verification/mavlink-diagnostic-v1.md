# MAVLink diagnostic v1 focused evidence

2026-10-10, Linux x86_64/CPython 3.13.5, source based on
`9edd575bc9f9de8e2a2b8b24e47f35cd0063b15f`. No P2 interfaces changed.

- RED: four initial CLI cases failed with eight assertions/subtests because the
  module did not exist (exit1 instead of the expected process behavior).
- GREEN: CLI plus existing datagram/passive tests, 30 PASS in31.435s.
- Added a deterministic stalled-clock/flood regression using a transport double;
  final five CLI tests PASS in5.923s. The other four CLI cases use real subprocesses
  and sockets. The double tests only the poll cap, not transport behavior.
- Ruff0.16.10 check and format PASS on both versioned adapters and their tests.
  The initial new test formatting check failed and was corrected without changing
  assertions. Bandit1.9.4 found no issues in the new CLI. Workflow YAML parsed.

The subprocess fixture sends synthetic ATTITUDE/LOCAL_POSITION_NED packets,
malformed private-marker bytes and a synthetic signed packet. Assertions verify
aggregate-only output, rejected signed traffic, withdrawal, no UDP response,
normal closure, invalid configuration, and a fixed occupied-port error. A stalled
duration clock still stops at1500 polls; no real-time exit guarantee is claimed.

These are focused software checks, not a performance benchmark, full fuzz,
installed-package/clean-clone reproduction or physical/SITL qualification.
The focused hosted workflow includes the new tests but has no result for this
change yet. Previous adapter/timing/aircraft negatives remain retained.
