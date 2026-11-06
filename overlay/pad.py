"""Encoder events from the CH57x macro pad.

The knob is programmed (see ../mapping.yaml) to emit F13 (counter-clockwise),
F14 (clockwise) and F15 (press). Using F-keys instead of volume keys means
scrolling cannot disturb system volume while the overlay menu is open.

Reports are read straight from the hidraw nodes, which are world accessible,
so neither root nor membership of the `input` group is required.
"""

import glob
import os

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

ENC_CCW = 0x68    # F13
ENC_CW = 0x69     # F14
ENC_PRESS = 0x6A  # F15

# HID usage -> logical action
KNOB = {ENC_CCW: "ccw", ENC_CW: "cw", ENC_PRESS: "press"}

VENDOR_PRODUCT = "1189:8890"


def pad_nodes():
    """hidraw nodes belonging to the macro pad.

    Resolved from sysfs rather than by hardcoding hidrawN, because node
    numbers shift whenever any USB device is added or removed — hardcoding
    them silently attaches the reader to an unrelated device.
    """
    nodes = []
    for link in glob.glob("/sys/class/hidraw/hidraw*"):
        try:
            device_path = os.path.realpath(link)
        except OSError:
            continue
        if VENDOR_PRODUCT in device_path:
            nodes.append("/dev/" + os.path.basename(link))
    return sorted(nodes)


def pressed_keys(report):
    """Currently-held keycodes from one keyboard input report."""
    if not report:
        return []
    if report[0] != 1:
        return []  # consumer-control or mouse report, not our concern

    # 6KRO:  [id, mods, reserved, k1..k6]   (9 bytes)
    # 17KRO: [id, mods, const,    k1..k9]   (12 bytes)
    slots = report[3:9] if len(report) == 9 else report[3:12]
    return [code for code in slots if code]


class PadReader:
    """Watches the pad's hidraw nodes and reports knob activity."""

    def __init__(self, on_event):
        self._on_event = on_event
        self._held = {}   # fd -> set of keycodes held as of the last report
        self._fds = []
        self.nodes = []

    def start(self):
        """Open whatever pad interfaces are present. Returns the node paths."""
        for node in pad_nodes():
            try:
                fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self._fds.append(fd)
            self._held[fd] = set()
            self.nodes.append(node)
            GLib.io_add_watch(fd, GLib.IO_IN, self._on_readable)
        return self.nodes

    def _on_readable(self, fd, _condition):
        while True:
            try:
                report = os.read(fd, 64)
            except BlockingIOError:
                break
            except OSError:
                return False
            if not report:
                break

            now = set(pressed_keys(report))
            # Only act on key-down edges, so a held key is reported once.
            for code in now - self._held[fd]:
                action = KNOB.get(code)
                if action:
                    self._on_event(action)
            self._held[fd] = now
        return True
