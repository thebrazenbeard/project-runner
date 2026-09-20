# Discovery Census Consumer V1

Status: SOURCE EXPERIMENT / OBSERVATIONAL INPUT ONLY

Project Runner consumes Discovery's public-safe portfolio census as an exact
**drift/currentness observation**, not as its runtime project registry.

Bound subject:

- repository: `thebrazenbeard/discovery`
- exact subject: `vera/discovery-shared-substrate-v1@1316094edbed17fa5918b70793c95ffddfcf92ea`
- path: `portfolio/PORTFOLIO_CENSUS_V1.json`
- Git blob: `34cd2ab55d46f5a1ecc2c894f3e8cfdb8afa41df`
- total repositories: 57
- all-name SHA-256: `43dfda1fa3dd24dec39e2aa345d93ab192dbda777433feae384da632b3d008dd`

The loader verifies the exact Git blob bytes before trusting the embedded count
or digest. The test fixture is byte-identical to that public Discovery artifact.

This mechanism answers one narrow question: "Has the observed owner repository
inventory changed from the exact Discovery cut?" It does not answer which
projects are schedulable, authoritative, coupled, writable, or current.

Project Runner retains its own explicit runtime registry, private external
registry rules, scheduling states, capabilities, and target authority.

`DISCOVERABLE != COUPLED`
`CENSUS_MATCH != RUNTIME_REGISTRY`
`OBSERVATIONAL_INPUT != AUTHORITY`
