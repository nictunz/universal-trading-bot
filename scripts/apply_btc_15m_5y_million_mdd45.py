from __future__ import annotations

import runpy
from pathlib import Path

# Canonical launcher for the selected BTC 15m strategy.
# The legacy target filename is retained so existing server commands keep working.
TARGET = Path(__file__).with_name("apply_elite_50x_15x3_profile.py")
runpy.run_path(str(TARGET), run_name="__main__")
