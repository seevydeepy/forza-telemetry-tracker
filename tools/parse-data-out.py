#!/usr/bin/env python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telemetry_tracker.data_out.parse_data_out import main

if __name__ == "__main__":
    raise SystemExit(main())
