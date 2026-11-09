"""Encoder events from the CH57x macro pad.

The knob is programmed (see ../mapping.yaml) to emit F13 (counter-clockwise),
F14 (clockwise) and F15 (press). Using F-keys instead of volume keys means
scrolling cannot disturb system volume while the overlay menu is open.

Reports are read from the hidraw nodes, which are readable once the udev rule
in ../setup-udev.sh is installed, so no root is required.

Reconnects
----------
The pad re-enumerates when it is unplugged, replugged or power-cycled, and its
hidraw node numbers change every time (hidraw6/7/8 -> hidraw9/10/11 -> ...).
A descriptor held across that change goes permanently silent, which looks
exactly like "nobody is turning the knob" — there is no error and no hangup on
a removed hidraw fd, so waiting for one never fires.

So the reader listens on the kernel uevent netlink socket, which is
event-driven, and re-syncs its descriptors on add/remove events for this
device. A slow periodic re-scan is kept as a safety net in case an event is
ever missed (socket buffer overrun, suspend/resume).
"""

import glob
import os
import socket
import sys

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

ENC_CCW = 0x68    # F13
ENC_CW = 0x69     # F14
ENC_PRESS = 0x6A  # F15

# HID usage -> logical action
KNOB = {ENC_CCW: "ccw", ENC_CW: "cw", ENC_PRESS: "press"}

VENDOR_PRODUCT = "1189:8890"
VENDOR_HEX = "1189"
PRODUCT_HEX = "8890"

NETLINK_KOBJECT_UEVENT = 15
SAFETY_RESCAN_SECONDS = 30


def pad_nodes():
    """hidraw nodes belonging to the macro pad.

    Resolved from sysfs rather than by hardcoding hidrawN, because node
    numbers shift whenever the device is re-plugged or any other USB device
    is added or removed.
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


def interface_of(node):
    """USB interface number (e.g. 0, 2, 3) for a hidraw node, or None."""
    try:
        device_path = os.path.realpath(f"/sys/class/hidraw/{os.path.basename(node)}")
    except OSError:
        return None
    for part in device_path.split("/"):
        if ":1." in part:
            try:
                return int(part.rsplit(".", 1)[1])
            except ValueError:
                return None
    return None


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
        self._held = {}      # fd -> set of keycodes held as of the last report
        self._node_of = {}   # fd -> node path
        self._id_of = {}     # fd -> (st_dev, st_ino) of the node when opened
        self._fds = []
        self._uevent_socket = None
        self._safety_id = 0
        self.nodes = []
        self.problems = []

    # ---- lifecycle -----------------------------------------------------

    def start(self):
        self._watch_uevents()
        self._sync_nodes()
        self._schedule_safety_rescan()
        return self.nodes

    def _watch_uevents(self):
        if self._uevent_socket is not None:
            return
        try:
            sock = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM,
                                 NETLINK_KOBJECT_UEVENT)
            sock.bind((0, 1))  # group 1 = kernel uevents
            sock.setblocking(False)
        except OSError as error:
            print(f"pad: uevent monitor unavailable ({error}); "
                  f"falling back to periodic re-scan", file=sys.stderr)
            return
        self._uevent_socket = sock
        GLib.io_add_watch(sock.fileno(), GLib.IO_IN, self._on_uevent)

    def _schedule_safety_rescan(self):
        if not self._safety_id:
            self._safety_id = GLib.timeout_add_seconds(
                SAFETY_RESCAN_SECONDS, self._safety_rescan)

    def _safety_rescan(self):
        self._sync_nodes()
        return True  # stays armed

    # ---- descriptors ---------------------------------------------------

    def _sync_nodes(self):
        """Make the open descriptors match what is actually plugged in."""
        wanted = set(pad_nodes())

        for fd, node in list(self._node_of.items()):
            if node not in wanted:
                self._drop(fd, "removed")
            elif not self._still_same(node, fd):
                # Same path, different device: the node was reused by a new
                # enumeration. A descriptor on the old one never signals
                # anything, so comparing paths alone would miss this.
                self._drop(fd, "replaced by new enumeration")

        have = set(self._node_of.values())
        for node in sorted(wanted - have):
            self._open_node(node)

        if self._node_of:
            self.problems = []
        return self.nodes

    def _still_same(self, node, fd):
        try:
            stat = os.stat(node)
        except OSError:
            return False
        return self._id_of.get(fd) == (stat.st_dev, stat.st_ino)

    def _open_node(self, node):
        try:
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            self.problems.append(
                f"{node}: permission denied — the udev rule is missing or "
                f"was not reloaded; run: sudo ./setup-udev.sh")
            return
        except OSError as error:
            self.problems.append(f"{node}: {error}")
            return

        self._fds.append(fd)
        self._held[fd] = set()
        self._node_of[fd] = node
        try:
            stat = os.stat(node)
            self._id_of[fd] = (stat.st_dev, stat.st_ino)
        except OSError:
            self._id_of[fd] = None
        self.nodes.append(node)
        GLib.io_add_watch(fd, GLib.IO_IN, self._on_readable)
        print(f"pad: attached {node}", file=sys.stderr, flush=True)

    def _drop(self, fd, reason):
        node = self._node_of.pop(fd, None)
        try:
            os.close(fd)
        except OSError:
            pass
        if fd in self._fds:
            self._fds.remove(fd)
        self._held.pop(fd, None)
        self._id_of.pop(fd, None)
        if node in self.nodes:
            self.nodes.remove(node)
        if node:
            print(f"pad: detached {node} ({reason})", file=sys.stderr, flush=True)

    # ---- input ---------------------------------------------------------

    def _on_uevent(self, _fd, _condition):
        try:
            payload = self._uevent_socket.recv(4096)
        except (BlockingIOError, InterruptedError):
            return True
        except OSError:
            return True

        text = payload.decode("utf-8", "replace")
        if VENDOR_HEX in text and PRODUCT_HEX in text:
            self._sync_nodes()
        return True

    def _on_readable(self, fd, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR | GLib.IO_NVAL):
            self._drop(fd, "hangup")
            return False

        while True:
            try:
                report = os.read(fd, 64)
            except BlockingIOError:
                break
            except OSError as error:
                self._drop(fd, str(error))
                return False
            if not report:
                self._drop(fd, "end of stream")
                return False

            now = set(pressed_keys(report))
            # Only act on key-down edges, so a held key is reported once.
            for code in now - self._held[fd]:
                action = KNOB.get(code)
                if action:
                    self._on_event(action)
            self._held[fd] = now
        return True
