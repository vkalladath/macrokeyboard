"""Audio control via pactl (PipeWire / PulseAudio compatible)."""

import json
import subprocess

VOLUME_STEP = 5  # percent per encoder detent when the menu is closed


class AudioError(RuntimeError):
    pass


def _pactl(*args):
    result = subprocess.run(["pactl", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioError(result.stderr.strip() or f"pactl {' '.join(args)} failed")
    return result.stdout


def _json(kind):
    try:
        return json.loads(_pactl("-f", "json", "list", kind))
    except (AudioError, json.JSONDecodeError):
        return []


def _volume_percent(obj):
    for channel in (obj.get("volume") or {}).values():
        return channel.get("value_percent", "?")
    return "?"


def _devices(kind, skip_monitors=False):
    out = []
    for obj in _json(kind):
        name = obj.get("name", "")
        if skip_monitors and name.endswith(".monitor"):
            continue
        out.append({
            "name": name,
            "label": obj.get("description") or name,
            "mute": bool(obj.get("mute")),
            "volume": _volume_percent(obj),
        })
    return out


def sinks():
    return _devices("sinks")


def sources():
    return _devices("sources", skip_monitors=True)


def default_sink():
    return _pactl("get-default-sink").strip()


def default_source():
    return _pactl("get-default-source").strip()


def set_default_sink(name):
    _pactl("set-default-sink", name)
    # Move whatever is already playing, so the switch is immediate rather than
    # taking effect only for the next stream.
    for line in _pactl("list", "short", "sink-inputs").splitlines():
        parts = line.split("\t")
        if parts and parts[0]:
            try:
                _pactl("move-sink-input", parts[0], name)
            except AudioError:
                pass


def set_default_source(name):
    _pactl("set-default-source", name)
    for line in _pactl("list", "short", "source-outputs").splitlines():
        parts = line.split("\t")
        if parts and parts[0]:
            try:
                _pactl("move-source-output", parts[0], name)
            except AudioError:
                pass


def volume_step(direction):
    """direction: +1 louder, -1 quieter."""
    sign = "+" if direction > 0 else "-"
    _pactl("set-sink-volume", "@DEFAULT_SINK@", f"{sign}{VOLUME_STEP}%")


def toggle_output_mute():
    _pactl("set-sink-mute", "@DEFAULT_SINK@", "toggle")


def toggle_mic_mute():
    _pactl("set-source-mute", "@DEFAULT_SOURCE@", "toggle")


def status_line():
    """One-line summary of the current output device, for the overlay footer."""
    try:
        current = default_sink()
        for sink in sinks():
            if sink["name"] == current:
                muted = " · muted" if sink["mute"] else ""
                return f"{sink['label']} · {sink['volume']}{muted}"
    except AudioError:
        pass
    return ""
