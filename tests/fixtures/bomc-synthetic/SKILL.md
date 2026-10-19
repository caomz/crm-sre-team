---
name: bomc-synthetic
description: Offline synthetic BOMC interface fixture. No network, credentials or real hosts.
---

# Synthetic query fixture

Only for offline unit tests and a separately configured Mac host test.
It writes deterministic synthetic JSON to --out, matching the assumed query
interface. It does not validate the real user-level skill's interface.
The TEST_* grades select timeout, failure and malformed-output scenarios.
It requires skill_root as cwd and an absolute --out. Optional --config accepts
an existing absolute file path without opening it; only a boolean is returned.
