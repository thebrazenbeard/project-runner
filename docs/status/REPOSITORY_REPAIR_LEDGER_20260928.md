# Repository Repair Ledger — 2026-09-28

Purpose: sequentially repair every repository in the owner estate and leave each
canonical default branch in a verified, truthful state before moving to the next.

Method for each repository:

1. read current default-branch source and declared purpose;
2. inspect open PRs/issues and identify superseded versus current work;
3. create/use an isolated Lappy workspace;
4. run the strongest available baseline tests/build/validation;
5. fix concrete defects or stale integration state;
6. run fresh verification on the exact candidate;
7. integrate only verified source into the canonical default branch;
8. record exact resulting head and evidence here.

No force-push, credential/provider mutation, destructive cleanup, deployment, or
fabricated qualification is implied by this ledger.

Current estate: 71 repositories — 69 active, 2 archived.

| # | Repository | Visibility | Default branch | Repair state |
|---:|---|---|---|---|
| 1 | `abil` | public | `main` | COMPLETE — `a93e345da27028df77e8c9047d1d32780038550b` |
| 2 | `Attune` | public | `main` | COMPLETE — `46461057e4d9ea25ec91a051fc17020e1113329a` |
| 3 | `axle` | public | `main` | COMPLETE — `d470544fb64875cb4789472ad4ef1b30f1fa65ee` |
| 4 | `brigit` | private | `main` | IN_PROGRESS |
| 5 | `brigit-unbound` | private | `main` | PENDING |
| 6 | `bt2` | public | `main` | PENDING |
| 7 | `bugops` | public | `main` | PENDING |
| 8 | `build-team-2.0` | public | `main` | PENDING |
| 9 | `ccb-core` | public | `main` | PENDING |
| 10 | `chat-communication-bus` | private | `main` | PENDING |
| 11 | `conations` | public | `main` | PENDING |
| 12 | `deepmemorystorage` | public | `main` | PENDING |
| 13 | `discovery` | public | `main` | PENDING |
| 14 | `driftguard` | public | `main` | PENDING |
| 15 | `empathy` | public | `main` | PENDING |
| 16 | `entropyinc` | private | `main` | PENDING |
| 17 | `firesafe` | private | `main` | PENDING |
| 18 | `freerowcochkar` | public | `main` | PENDING |
| 19 | `fuckup` | public | `main` | PENDING |
| 20 | `god-brain` | public | `main` | PENDING |
| 21 | `hc-brain` | public | `main` | PENDING |
| 22 | `hephaestus` | public | `main` | PENDING |
| 23 | `ingest` | public | `main` | PENDING |
| 24 | `intranel` | public | `main` | PENDING |
| 25 | `lgcm` | public | `main` | PENDING |
| 26 | `masamune` | public | `main` | PENDING |
| 27 | `mediaphile` | private | `main` | PENDING |
| 28 | `meso-crct` | public | `main` | PENDING |
| 29 | `mosaic` | public | `main` | PENDING |
| 30 | `noema` | public | `main` | PENDING |
| 31 | `on-theo` | public | `main` | PENDING |
| 32 | `orgasm` | private | `main` | PENDING |
| 33 | `personification` | public | `main` | PENDING |
| 34 | `pro-run` | public | `main` | PENDING |
| 35 | `project-achilles` | public | `main` | PENDING |
| 36 | `project-lantern` | public | `main` | PENDING |
| 37 | `project-runner` | public | `main` | PENDING |
| 38 | `RepairTracker` | public | `main` | PENDING |
| 39 | `rezon` | public | `main` | PENDING |
| 40 | `roots` | public | `main` | PENDING |
| 41 | `selfimage` | private | `main` | PENDING |
| 42 | `semanticatlas` | public | `main` | PENDING |
| 43 | `sexuality` | private | `main` | PENDING |
| 44 | `skeletonkey` | private | `main` | PENDING |
| 45 | `spm` | public | `main` | PENDING |
| 46 | `sql-connectome` | public | `main` | PENDING |
| 47 | `temporal` | public | `main` | PENDING |
| 48 | `testament` | public | `main` | PENDING |
| 49 | `transcendence` | public | `main` | PENDING |
| 50 | `trek-data-core` | private | `main` | PENDING |
| 51 | `unbound-sol` | public | `main` | PENDING |
| 52 | `unvtrslr` | public | `main` | PENDING |
| 53 | `vera` | public | `main` | PENDING |
| 54 | `vera_ark` | private | `main` | PENDING |
| 55 | `vera_model_training` | public | `main` | PENDING |
| 56 | `vera-apk` | private | `main` | PENDING |
| 57 | `vera-control-plane` | public | `main` | PENDING |
| 58 | `vera-habitat` | public | `main` | PENDING |
| 59 | `vera-mesh` | public | `main` | PENDING |
| 60 | `vera-mono` | public | `main` | PENDING |
| 61 | `vera-os` | private | `main` | PENDING |
| 62 | `vera-R9A0` | public | `main` | PENDING |
| 63 | `vera-synology` | public | `main` | PENDING |
| 64 | `vera-works` | private | `main` | PENDING |
| 65 | `voss` | public | `main` | PENDING |
| 66 | `wip` | public | `main` | PENDING |
| 67 | `WorkBridgeMCP` | public | `main` | PENDING |
| 68 | `world-zero` | public | `main` | PENDING |
| 69 | `wreckforge` | private | `main` | PENDING |
| 70 | `conditioning` | private | `main` | ARCHIVED_REVIEW_PENDING |
| 71 | `self` | private | `main` | ARCHIVED_REVIEW_PENDING |

## Completed checkpoints

### 1. abil

Canonical main after repair:

`a93e345da27028df77e8c9047d1d32780038550b`

Evidence:

- current architecture/R2 canonicalization preserved;
- 64 missing historical research/recovery artifacts recovered without overwriting canonical architecture;
- exact-source consolidation manifest added;
- repository validator and hosted validation workflow added;
- Windows/Lappy exact-main validation: PASS;
- PR exact-head hosted validation: PASS;
- post-merge main validation run status: []

### 2. Attune

Canonical main after repair:

`46461057e4d9ea25ec91a051fc17020e1113329a`

Evidence:

- foundation influence/memory contract suite: 9/9 PASS on exact merged main;
- compileall: PASS;
- stale implementation/branch status corrected;
- qualification workflow now targets canonical main;
- hosted PR exact-head qualification: PASS.

### 3. axle

Canonical main after repair:

`d470544fb64875cb4789472ad4ef1b30f1fa65ee`

Evidence:

- exact merged-main validator: 30/30 unit tests PASS;
- Python source/test compile: PASS;
- TOML and hardware JSON parse: PASS;
- touchscreen JavaScript parse: PASS;
- stale V1 integration state superseded by current V2 continuation;
- canonical cross-platform validator wired into CI;
- hosted PR exact-head CI: PASS.

## Current repository

`brigit` — sequential repair repository 4 of 71.
