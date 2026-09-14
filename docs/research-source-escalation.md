# Research source escalation policy

This project uses an evidence hierarchy for unresolved NR2301 protocol behavior.

## Escalation order

When the NR2301 contract cannot be completed from the primary project evidence, research in this order:

1. current `nr2301-api` evidence, captures, shipped/frontend assets, known firmware behavior and historical NR2301 project artifacts;
2. source-compatible or closely related Marvell/OEM firmware and backend implementations from the same platform family;
3. public Zyxel projects for routers from the same approximate product/firmware generation, including FWA/LTE/NR/VMG devices where relevant;
4. third-party integrations and reverse-engineering projects, including Home Assistant integrations, router managers, scripts, OpenWrt/OEM GPL drops and similar repositories;
5. broader same-generation router/OEM implementations only when they share a credible backend, WebUI, CGI, ubus or request-contract lineage.

Search GitHub and other public repository sources proactively once the primary evidence is exhausted; do not stop merely because the first NR2301-specific repositories do not contain the answer.

## Targeted WebUI crawl for quarantined contracts

When a capability is visibly configurable through the NR2301 WebUI but the API contract remains unresolved after source research, quarantine that capability rather than continuing to guess payloads.

Before the end-of-campaign reset, perform a targeted WebUI crawl for the quarantined set. Prefer observing the real browser action over broad crawling:

- capture the request triggered by the exact UI action that creates, edits, clears or deletes the state;
- record HTTP verb, endpoint/CGI path, query parameters, request body shape, content type and relevant response semantics;
- determine whether the UI uses a direct API call, multicall, legacy XML action, alternate CGI family or JavaScript-side transformation;
- compare create/edit/delete flows separately because firmware may use different methods for each;
- verify the resulting state through the normal API/read-back path after the UI action;
- sanitize cookies, credentials, private IP/MAC values and other device-specific secrets before committing evidence.

A WebUI-observed request on the physical NR2301 is stronger evidence than a cross-device hypothesis and should be normalized upstream once its effect is physically verified.

Keep a compact quarantine list during a campaign with at least: capability, unresolved operation, current residual state, evidence already tried, whether the residual state is functionally active, and required final recovery action. This prevents repeated blind probes and makes the final WebUI crawl efficient.

## How external findings may be used

A contract observed on another Zyxel model or related OEM device is a **test hypothesis**, not protocol truth for the NR2301.

For every cross-device hypothesis:

- record the source model/platform and transport family;
- identify why the implementation is plausibly related to the NR2301;
- prefer exact field names, request shapes, HTTP verbs, CGI paths, ubus methods and read-back semantics over UI-level descriptions;
- test the smallest reasonable candidate on the dedicated NR2301;
- decide success by endpoint-specific response semantics and/or read-back, not HTTP 200 alone;
- normalize only physically confirmed NR2301 behavior into `nr2301-api`;
- explicitly retain contradictions when another Zyxel family behaves differently.

Do not copy contracts blindly across Zyxel product lines. Zyxel devices from similar periods may use materially different API stacks (for example Marvell XML/ubus-style WebUI paths versus newer `/cgi-bin/DAL` families).

## Recovery and failed hypotheses

If an exploratory write leaves state behind:

- first use a physically evidenced or strongly source-backed inverse/clear operation;
- stop multiplying guessed payloads once source-backed candidates are exhausted;
- expand research to related Zyxel/OEM repositories before trying further speculative mutations;
- if the capability is available in the NR2301 WebUI, add it to the quarantine list for a targeted end-of-campaign WebUI crawl before reset;
- use the physical reset button as the final recovery path when necessary;
- keep USB-management-mode mutation excluded while USB remains the active control/recovery path.

Failed candidates are useful evidence and should be recorded when they materially narrow the contract.