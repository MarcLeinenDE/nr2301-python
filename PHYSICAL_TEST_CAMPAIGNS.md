<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Physical test campaign policy

Physical-router verification should be organized as **batched campaigns** when tests share a functional domain, risk level, preflight state and recovery/cleanup strategy.

The goal is to reduce repeated manual setup and router interaction without weakening evidence quality.

## Default batching rule

Prefer one physical campaign over many tiny one-method runs when all of the following are true:

- the methods belong to the same functional domain or lifecycle;
- they use the same physical-test gate/risk tier;
- one preflight snapshot can safely cover the whole batch;
- each subtest can still emit an unambiguous result/checkpoint;
- cleanup can restore the exact initial state, or the campaign is explicitly destructive;
- a failure in one subtest does not make later cleanup impossible.

If one subtest fails, preserve its raw sanitized result, run the planned cleanup/recovery path, and then analyze the failure. Do not split every successful subtest into a separate manual router run merely for isolation.

## Maintainer-authorized scope

The connected NR2301 is a dedicated non-production test device. The maintainer authorizes read, write, disruptive and reset-capable coverage needed for complete API/SDK reconstruction.

A physical reset button is available as the final recovery path and loss of the current test configuration is acceptable when required.

**Current hard exclusion:** do not mutate USB/management mode. USB remains the active management/recovery channel.

## Risk gates

```text
NR2301_INTEGRATION=1              read-only physical campaigns
NR2301_WRITE_INTEGRATION=1        reversible/state-changing campaigns
NR2301_DESTRUCTIVE_INTEGRATION=1  disruptive/reset-capable campaigns
```

An actual factory-reset API test should additionally require a campaign-specific confirmation variable so a reset cannot be triggered accidentally by a broader destructive batch.

## Campaign structure

A physical campaign should normally follow:

```text
preflight/login
→ snapshot relevant initial state
→ run related subtests with labeled checkpoints
→ read back each intended effect
→ perform planned restores/cleanup
→ verify exact final state where restoration is expected
→ emit one final campaign PASS/FAIL summary
```

Use `try/finally` or equivalent cleanup protection for reversible/stateful tests.

For objects created by the campaign, prefer stable IDs/index deltas over names for ownership and cleanup when firmware may transform presentation fields.

## Division of work

GitHub CI should handle offline unit tests, supported-Python matrix and package/wheel validation. Do not ask the maintainer to repeat those locally when the exact tested commit is already green unless local reproduction is itself needed for diagnosis.

The maintainer should primarily run tests that require the physical router, local credentials, real reconnect/recovery behavior, or hardware observation.

## Evidence rule

Batching must not reduce protocol precision. Each newly established request shape, raw value, response behavior, success criterion, mutation semantic or recovery fact must still be normalized upstream in `nr2301-api` before the corresponding SDK surface is treated as final.

Sensitive values may be inspected locally when necessary, but public evidence must remain sanitized.