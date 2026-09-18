# Android rebuild verification

Requested after install failure of 1.1.350.

Verified before rebuild:
- Priority LIVE backtest explicit routing is present (PRIORITY_5M_15M -> ACTION_START -> run_priority_live_backtest).
- Priority requests force db_only=false and reject DB-download routing.
- Full GitHub test matrix for source commit bf0376fd passed on Python 3.10, 3.11, and 3.12.
- Android 1.1.350 build/sign/publish workflow completed successfully, but the device reported installation failure; this commit intentionally triggers a fresh monotonically-versioned signed rebuild without changing trading/runtime logic.
