"""Houdini Viewport screenshot capture for Edini."""
import io
import base64
import importlib

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


def capture_viewport() -> str | None:
    """Capture current Houdini viewport as base64 JPEG.

    Returns base64-encoded JPEG string, or None if not in Houdini.
    """
    if hou is None:
        return None

    try:
        desktop = hou.ui.curDesktop()
        viewport = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewport is None:
            return None

        buf = io.BytesIO()
        viewport.saveImage(buf, "JPEG", width=1280, height=720)
        buf.seek(0)
        img_bytes = buf.getvalue()

        if len(img_bytes) == 0:
            return None

        return base64.b64encode(img_bytes).decode("ascii")
    except Exception:
        return None


def is_vision_capable(provider: str, model: str) -> bool:
    """Check if the current model supports image input."""
    vision_providers = {"anthropic", "openai", "google"}
    return provider.lower() in vision_providers
