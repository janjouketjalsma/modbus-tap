"""Load the integration's pure-Python modules without Home Assistant."""

import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).parents[1] / "custom_components" / "modbus_sniffer"

# A bare package object, so `from .rtu import ...` works inside regmap.py
# without executing __init__.py (which imports Home Assistant).
if "msn" not in sys.modules:
    pkg = types.ModuleType("msn")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules["msn"] = pkg
