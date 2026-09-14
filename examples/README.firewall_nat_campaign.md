# Firewall/NAT physical campaign

`explore_firewall_nat_campaign.py` is a gated research harness for the dedicated NR2301 test device.

It requires `NR2301_WRITE_INTEGRATION=1`, snapshots every tested state before mutation, performs read-back after each write, and restores the original state in `finally` blocks where a mutation is attempted.

The campaign deliberately continues after an individual phase failure so later independent contracts can still be characterized in the same physical session. The final result is therefore `PASS` or `PARTIAL`, with a phase failure list.

Synthetic values are used for test-only rules. Public evidence must remain sanitized. USB/management-mode mutation remains outside the campaign scope.
