"""Platform-specific "apply" backends (theme, night light, …).

Phase 1 targets Linux Mint / Cinnamon. Later phases add Windows and macOS
implementations behind the same function names.
"""

from .theme import set_theme
from .nightlight import set_nightlight

__all__ = ["set_theme", "set_nightlight"]
