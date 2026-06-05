"""Houdini Viewport utilities for Edini.

Viewport capture has moved to edini.media_manager for unified image handling.
This module keeps backward-compatible re-exports.
"""
import importlib

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


# Re-export from media_manager for backward compatibility
from edini.media_manager import capture_viewport, is_viewport_available


def is_vision_capable(provider: str, model: str) -> bool:
    """Check if the current model supports image input natively.

    Note: With pi-visionizer, even text-only models can handle images.
    This function only checks native support.
    """
    vision_providers = {"anthropic", "openai", "google"}
    return provider.lower() in vision_providers
