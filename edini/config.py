"""Edini configuration constants."""
import os
from pathlib import Path

# Project root (parent of edini/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pi executable (from npm global install)
PI_EXECUTABLE = os.environ.get("EDINI_PI_PATH", "pi")

# Pi extensions directory
PI_EXTENSIONS_DIR = PROJECT_ROOT / "pi-extensions"

# Tool executor HTTP server
TOOL_EXECUTOR_HOST = "127.0.0.1"
TOOL_EXECUTOR_PORT = 9876

# Default model
DEFAULT_MODEL_PROVIDER = os.environ.get("EDINI_MODEL_PROVIDER", "anthropic")
DEFAULT_MODEL_ID = os.environ.get("EDINI_MODEL_ID", "claude-sonnet-4-5")

# Panel dimensions
PANEL_DEFAULT_WIDTH = 500
PANEL_DEFAULT_HEIGHT = 600

def get_pi_command() -> list[str]:
    """Build the Pi subprocess command."""
    return [
        PI_EXECUTABLE,
        "--mode", "rpc",
        "--no-session",
        "-e", str(PI_EXTENSIONS_DIR / "edini-tools" / "index.ts"),
        "-e", str(PI_EXTENSIONS_DIR / "edini-context" / "index.ts"),
    ]
