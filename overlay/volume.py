"""Volume control.

Prefers a uinput virtual keyboard emitting real KEY_VOLUMEUP/KEY_VOLUMEDOWN
events, so the desktop shows its own volume OSD and applies its own policies.
Falls back to setting the volume directly through pactl when uinput is not
available (no permission, no evdev module).

The virtual device is created once, at startup, because uinput registration
takes a moment and the first knob detent should not be delayed by it.
"""

import atexit

from . import audio

try:
    from evdev import UInput, ecodes
except Exception:  # pragma: no cover - depends on the host
    UInput = None
    ecodes = None

_device = None
_failed = False


def _get_device():
    global _device, _failed
    if _device is not None or _failed:
        return _device
    if UInput is None or ecodes is None:
        _failed = True
        return None
    try:
        _device = UInput(
            {ecodes.EV_KEY: [ecodes.KEY_VOLUMEUP, ecodes.KEY_VOLUMEDOWN]},
            name="Macro pad volume",
            version=0x1,
        )
        atexit.register(_device.close)
    except Exception as error:
        print(f"uinput unavailable, falling back to pactl: {error}")
        _failed = True
        _device = None
    return _device


def warm_up():
    """Create the virtual device early so the first keypress is instant."""
    _get_device()


def _tap(code, repeats):
    device = _get_device()
    if device is None:
        return False
    for _ in range(max(1, repeats)):
        device.write(ecodes.EV_KEY, code, 1)
        device.syn()
        device.write(ecodes.EV_KEY, code, 0)
        device.syn()
    return True


def step(direction, repeats=1):
    """direction: +1 louder, -1 quieter."""
    if ecodes is not None:
        code = ecodes.KEY_VOLUMEUP if direction > 0 else ecodes.KEY_VOLUMEDOWN
        if _tap(code, repeats):
            return
    audio.volume_step(direction)


def using_uinput():
    return _get_device() is not None
