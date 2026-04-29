"""
app/tests/conftest.py — Shared pytest fixtures and configuration.

Ensures the project root is on sys.path so all app.* imports resolve
correctly regardless of how pytest is invoked.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
