"""Pytest configuration for Edini tests."""
import sys
import os

# Ensure python3.11libs is on sys.path for all tests.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
