def open_chat_window(**kwargs):
    from edini.ui.windows import open_chat_window as _open
    return _open(**kwargs)

def open_settings(**kwargs):
    from edini.ui.windows import open_settings as _open
    return _open(**kwargs)

__all__ = ["open_chat_window", "open_settings"]
