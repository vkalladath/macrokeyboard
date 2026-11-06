"""Menu tree — everything user-visible is defined here.

To add an item: append an `Item` to the relevant list below. If it opens a
submenu, also register a title in `TITLES` and handle the new name in
`items_for`.
"""

import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from . import audio


@dataclass
class Item:
    label: str
    action: Optional[Callable[[], None]] = None
    submenu: Optional[str] = None
    keep_open: bool = False   # stay open after the action (e.g. volume steps)
    back: bool = False        # pop to the parent menu
    close: bool = False       # dismiss the overlay


TITLES = {
    "main": "Macro pad",
    "audio": "Audio controls",
    "sinks": "Switch audio source",
    "mic": "Microphone",
    "sources": "Switch microphone",
    "system": "System",
}


def title_for(menu):
    return TITLES.get(menu, menu)


def lock_screen():
    subprocess.run(["loginctl", "lock-session"], check=False)


def suspend():
    subprocess.run(["systemctl", "suspend"], check=False)


def _device_items(devices, current, apply):
    """Bullet list of devices, with the active one marked."""
    items = []
    for device in devices:
        marker = "●" if device["name"] == current else "○"
        items.append(Item(
            f"{marker}  {device['label']}",
            action=(lambda name=device["name"]: apply(name)),
            keep_open=True,  # so the ● marker visibly moves
        ))
    if not items:
        items.append(Item("(none found)"))
    items.append(Item("‹  Back", back=True))
    return items


def items_for(menu):
    if menu == "main":
        return [
            Item("Audio controls", submenu="audio"),
            Item("Microphone", submenu="mic"),
            Item("System", submenu="system"),
            Item("Close menu", close=True),
        ]

    if menu == "audio":
        return [
            Item("Switch audio source", submenu="sinks"),
            Item("Volume up", action=lambda: audio.volume_step(+1), keep_open=True),
            Item("Volume down", action=lambda: audio.volume_step(-1), keep_open=True),
            Item("Mute output", action=audio.toggle_output_mute, keep_open=True),
            Item("‹  Back", back=True),
        ]

    if menu == "sinks":
        return _device_items(audio.sinks(), audio.default_sink(), audio.set_default_sink)

    if menu == "mic":
        return [
            Item("Switch microphone", submenu="sources"),
            Item("Mute microphone", action=audio.toggle_mic_mute, keep_open=True),
            Item("‹  Back", back=True),
        ]

    if menu == "sources":
        return _device_items(audio.sources(), audio.default_source(), audio.set_default_source)

    if menu == "system":
        return [
            Item("Lock screen", action=lock_screen),
            Item("Suspend", action=suspend),
            Item("‹  Back", back=True),
        ]

    return [Item("‹  Back", back=True)]
