# RescueSense implementation plan
Goal: complete the allowed reference software and all independent verification, release and presentation work; expose exact hardware blockers.
Architecture: protocol.md defines the closed boundary. schema.py validates bytes; features.py extracts eligible rules; core.py fuses; actions.py recommends; render.py renders expiring coarse outputs; adapters.py minimizes reference inputs. CLI evaluates one bounded file. No sub-agents; owner authorized autonomous execution.
Stack: Python 3.9+ stdlib runtime. Development tools isolated locally.
Review focus: future timestamps, bool-as-int, misleading thermal human localization, same-sensor duplicates, expired visual replay; each gets a negative test.

1. Write schema/fusion/darkness/privacy/action tests with literal expectations and run red. Implement parser, bounded feature/model loading, fusion and recommendations. Run whole suite.
2. Write adapter/renderer/CLI expiry tests and run red. Implement local snapshot renderer, minimized adapter contracts, executable synthetic demos and data evaluation. Run full suite and 2000+ oracle properties.
3. Add security/static checks and 60-second parser fuzz; preserve failure log and fix regressions. Freeze dataset protocol before metrics.
4. Build deterministic source archive/zipapp, SBOM, manifest and hashes; clone locally, run README commands and standalone consumer, reproduce artifacts twice. Audit exact content.
5. Reinspect Flutter presentation, create original vector identity/architecture and command-derived visual replay, finalize contributor experience/CI/release workflows.
6. Re-run gates on committed candidate, list passed/blocked rows and hardware evidence. Publish only if publication prerequisites pass; never claim live production readiness without H evidence.
