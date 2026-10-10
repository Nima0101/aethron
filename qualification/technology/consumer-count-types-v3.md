# Portable consumer count types — review v3

At baseline `9e36a15e5696d2c29d629a57ef9f0be92e031eae`, the fresh review
reread declaration admission, artifact matching, campaign coverage, reference
binding, bundle composition, both CLI sources and the latest portable consumer
runner. No production defect was demonstrated in that read. The consumer runner
had an executable mismatch: equality of capture-count dictionaries did not prove
the integer types described by its portable expectations. A Boolean or floating
substitution could pass. Existing production responses contain integers; this is
a test-assurance correction, not a production-validator repair.

## Constraints and technology choice

The boundary is a finite source-checkout test over a trusted, 32 KiB repository
fixture. It invokes real synchronous Python APIs and checks partial result
projections. It needs to preserve the APIs' runtime types, detect independently
wrong expectations and responses, retain negative outcomes, and restore temporary
patches. It has no network, device, procedure execution, hard deadline, installed
product or cryptographic attestation requirement.

| Candidate | Decisive property for this correction |
|---|---|
| Python unittest with exact type assertions | Observes the actual API objects before serialization; `type(value) is int` distinguishes Boolean, float and subclasses. Equality remains a separate value check. |
| Pydantic strict integer models | Provides a reusable validation schema with strict integer admission. It is credible for a published typed report boundary; these three internal assertions need no model construction or transformed output. |
| CUE validation | Useful for independently declared structured constraints. Validating exported data does not observe the original Python object types; a separate direct check would still be needed for this reference API. |
| F#/C# with System.Text.Json | A credible non-incumbent consumer implementation. JSON token kinds distinguish Boolean from Number, while the integer representation policy needs additional checks. Crossing serialization also loses Python runtime subtype information. |

**KEEP the direct Python runner; FIX exact count assertions.** Direct observation
of the required runtime values gives stronger evidence for this requirement than
checking only serialized data. The choice is not based on tool installation,
familiarity or rewrite cost. A published independent consumer or installed-report
protocol would require its own technology decision and parity tests. There is no
performance ranking or native implementation claim.

Primary sources inspected 2026-10-10:
[Python numeric comparisons](https://docs.python.org/3.13/library/stdtypes.html#numeric-types-int-float-complex),
[unittest identity assertions](https://docs.python.org/3.13/library/unittest.html#unittest.TestCase.assertIs),
[Pydantic strict integers](https://docs.pydantic.dev/latest/api/types/#pydantic.types.StrictInt),
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/), and
[System.Text.Json token kinds](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.jsonvaluekind?view=net-9.0).
The suitability comparison is this review's analysis.

## Executable evidence

Two negative-control methods cover all three count fields, both Boolean and float
substitutions, and both expectations and actual responses: twelve variations.
Each first requires the real bundle consumer test to pass. Fixture controls write
a temporary copy and change only one expected count; response controls call the
real evaluator and alter only a returned count's type where its value is zero or
one. Count two is preserved, preventing an unrelated value mismatch from hiding
the type defect. Each control requires assertion failures, zero execution errors,
zero skips and one executed consumer method. After patch cleanup the original
consumer method must pass again.

Before correction all twelve variations escaped detection, producing twelve
assertion failures in the two control methods and zero errors. Exact dictionary
keys and integer types are now checked in fixture loading and returned counts.
The five affected runner/control methods pass. The related run and source
observations are recorded in [consumer-count-types-v3.json](consumer-count-types-v3.json).
Historical evidence stays unchanged and does not establish this new property.

No production implementation, fixture bytes, finding code, time threshold or
qualification flag changed. These finite controls are neither full fuzzing nor
comprehensive report conformance. Procedure/domain content, authenticated source
evidence, installed consumer execution and P19 help acceptance remain unfinished
as listed in the [readiness inventory](../p15-readiness-v1.md). This correction
does not complete the full lane re-audit. The remaining audit-tool review precedes
new procedure-content work. Physical qualification remains external and false.
