"""
Pytest configuration for Open WebUI tests.

This file configures pytest to properly discover and run tests.
"""

import sys
from pathlib import Path

# Add the backend directory to sys.path so tests can import from open_webui
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Create aliases for test modules to support both import styles
# This allows: `from test.util.xxx import ...`
# Instead of: `from open_webui.test.util.xxx import ...`
import open_webui.test as test_module
sys.modules["test"] = test_module
