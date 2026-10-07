# Tattler reasoning-surface results — 2026-10-07

Status: OBSERVATION NOTE / SCHEDULER SEMANTIC BOUNDARY

## Shared experiment result

On 2026-10-07, the same repository stress-test prompt was run through three ChatGPT surfaces while WorkLaptop was instrumented with Tattler plus a companion Codex process/network tracer.

Observed controlled windows:

- Desktop Chat, GPT-5.6 Sol High: **0 MXC launches** and **2 new established Codex TLS connections** in the companion tracer.
- ChatGPT Desktop Work, Ultra: **59 MXC launches** and **73 new established Codex TLS connections** using the same companion-tracer definitions.
- Firefox cloud Work, Max: browser-side traffic was observable locally, but the provider's server-side worker topology was not.

The bounded conclusion is that Desktop Work used materially different local orchestration from ordinary High Chat in this runtime. It does **not** establish that sockets or MXC processes equal agents, that connection fanout grants a reasoning tier, or that a client can promote High into Ultra/Max by imitating transport behavior.

Canonical detailed evidence is being preserved in `thebrazenbeard/tattler` PR #7 and the reasoning interpretation in `thebrazenbeard/rezon` PR #103.


## Why Project Runner needs this result

Project Runner schedules work, resources, lanes, and execution attempts. P.O.R.T.A.L. inherits those mechanics. The Tattler experiment shows that local process/network fanout must not be conflated with the scheduler's semantic worker model.

```text
Runner lane != model agent
execution attempt != reasoning turn
child process != independent reviewer
socket count != resource entitlement
```

If Project Runner later executes Rezon-style reasoning escalation, the requested reasoning class and selected product surface should be explicit task/worker metadata with bounded resource accounting. The runner should not infer either from MXC/process/socket activity.

## Verification implication

A reasoning result should remain bound to the exact task/subject version, worker/surface descriptor, attempt identity, context manifest, and resource receipt. Tattler evidence may support runtime diagnostics, but it cannot substitute for those semantic bindings.

The 2026-10-07 P.O.R.T.A.L. stress test also found execution-control defects above the Runner/host composition boundary. Higher-cost reasoning delegation should not weaken existing fencing, STOP/HOLD, replay, or ambiguous-effect protections.
