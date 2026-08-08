"""Platform-specific "apply" backends (theme, night light, …).

Phase 1 targets Linux Mint / Cinnamon. Later phases add Windows and macOS
implementations behind the same function names.
"""

from .nightlight import nightlight_on, set_nightlight
from .theme import set_theme

__all__ = ["nightlight_on", "set_nightlight", "set_theme"]
