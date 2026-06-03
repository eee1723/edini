def open_chat_window():
    from edini.ui.windows import open_chat_window as _open
    return _open()

def open_settings():
    from edini.ui.windows import open_settings as _open
    return _open()

__all__ = ["open_chat_window", "open_settings"]
