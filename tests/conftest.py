"""Load the integration's plain-Python modules without Home Assistant installed."""

import sys
import types
from pathlib import Path

PACKAGE_DIR = Path(__file__).parents[1] / "custom_components" / "modbus_tap"

# A bare package, so relative imports work without running __init__.py.
if "tap" not in sys.modules:
    package = types.ModuleType("tap")
    package.__path__ = [str(PACKAGE_DIR)]
    sys.modules["tap"] = package
