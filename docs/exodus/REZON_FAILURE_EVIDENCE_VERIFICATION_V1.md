# Rezon Failure-Path Evidence Verification V1

Status: **EXPERIMENTAL / REAL FAILURE PATH / UNCHANGED VERIFIER**

This is the second real flow for Discovery candidate
`REZON_RUNNER_BOUNDARY_V1`.

The Project Runner verifier is unchanged from the successful-path experiment:

`runner/rezon_evidence.py`
Git blob:
`d7827dec743e69fff7f981d91d7a86f6cd4a4839`.

## Exact producer

Rezon R51:

`8289914ec500a1392b10fe1a3774dee166e73b40`

A real invalid-result execution was produced directly from this exact source
under Python 3.12 with no package installation.

The Rezon runner emitted:

- PLAN effect state;
- one execution;
- trace failure `contract_violation`;
- receipt failure `contract_violation`;
- no canonical output digest;
- no canonical producer ID;
- one unresolved invalid-contract marker.

Evidence digest:

`516146d1f01291510e5b31e645520ed5434760ff953139d6aba71ea4cc37e752`.

## Boundary under test

Project Runner must verify that the receipt covers the trace failure while
remaining agnostic to what the Rezon failure string *means*.

A hostile regression replaces both receipt and trace failure values with a
future unknown Rezon failure token and rehashes the evidence.

The unchanged Runner verifier must still accept it structurally.

That proves the cross-project contract is:

**failure coverage and binding**

not:

**shared failure ontology**.

Likewise, Rezon's unresolved marker remains opaque. A structurally valid failure
export never becomes Project Runner completion, Rezon admission, truth, or
qualification.

## Claim ceiling

A PASS can establish:

`REAL_SUCCESS_AND_FAILURE_PATH_MECHANICAL_INTEROP_WITH_UNCHANGED_VERIFIER`.

It still cannot establish:

- Rezon epistemic delegation;
- shared failure semantics;
- Project Runner authority over Rezon;
- external-effect authorization;
- net maintenance savings;
- mandatory Runner dependency;
- `PROVEN_REUSABLE`.
