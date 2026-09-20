# Discovery Effect Envelope Producer — Project Runner M6

Status: **SOURCE EXPERIMENT / ONE-WAY INTERCHANGE ONLY**

Exact native base:

`work/exodus-current-m6-discovery-v1-20260919@bee7e720ba923ef38ce87fca4c9c2560163a9360`

This adapter exports Project Runner's existing GitHub mutation lifecycle into
Discovery's experimental neutral effect-attempt envelope.

It does not change the Project Runner state machine.

Mappings:

- mutation work before execution → `PRE_EFFECT`;
- `VERIFYING` → `POST_EFFECT_UNVERIFIED`;
- `COMPLETE` → `POST_EFFECT_VERIFIED`;
- `FAILED_DETERMINISTIC` → `TERMINAL_FAILURE`;
- `OUTCOME_UNKNOWN` → `OUTCOME_UNKNOWN`.

`SUPERSEDED` is deliberately rejected by the adapter because it is a native
currentness/scheduling state, not an effect outcome.

A successful backend result alone is never enough for
`POST_EFFECT_VERIFIED`; Project Runner must already have produced native
`COMPLETE` after independent completion verification.

`OUTCOME_UNKNOWN` exports `INSPECT_BEFORE_RETRY` and an explicit receipt
ceiling that the effect may have occurred.

The envelope carries no lease/fence authority, target authority, scheduling
authority, retry authority, completion authority, or permission to execute.

Project Runner does not import Discovery and remains fully standalone.
