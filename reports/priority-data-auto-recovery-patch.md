# Priority LIVE transient data auto-recovery patch

Scope: recover only a persisted/in-process `data unavailable for ...` PriorityRuntime HALT caused by transient market-data/relay loss.

Safety contract:
- Existing stale detection and 25 second fail-closed HALT remain unchanged.
- Recovery is prohibited when controller owner, position, or pending operation exists.
- Recovery is prohibited when engine safety is halted for any reason other than the exact mirrored PriorityRuntime data HALT.
- Both 5m and 15m OHLCV and four-source volume fetches must succeed.
- Bitget must report FLAT twice per probe.
- Three consecutive healthy probes are required before clearing the data-only controller HALT and its exact mirrored engine safety HALT.
- Execution, reconciliation, position mismatch, protection, profile, pending-operation, and unrelated safety HALTs are never auto-cleared.
- No order sizing, 5m/15m priority, entry, TP/SL, or execution code is changed.
