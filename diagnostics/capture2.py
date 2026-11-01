#!/usr/bin/env python3
"""Capture + decode macropad HID reports from all three input interfaces."""
import os, select, sys, time

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
IDLE = 8.0

# hidraw6 = if00 boot keyboard, hidraw7 = if02 17KRO keyboard + consumer,
# hidraw8 = if03 boot mouse
LABEL = {"/dev/hidraw6": "kbd6K", "/dev/hidraw7": "kbd17K/media", "/dev/hidraw8": "mouse"}

MODS = {0x01: "LCtrl", 0x02: "LShift", 0x04: "LAlt", 0x08: "LMeta",
        0x10: "RCtrl", 0x20: "RShift", 0x40: "RAlt", 0x80: "RMeta"}

# USB HID keyboard usage -> name (subset that matters)
KEYS = {0x04:"a",0x05:"b",0x06:"c",0x07:"d",0x08:"e",0x09:"f",0x0a:"g",0x0b:"h",
        0x0c:"i",0x0d:"j",0x0e:"k",0x0f:"l",0x10:"m",0x11:"n",0x12:"o",0x13:"p",
        0x14:"q",0x15:"r",0x16:"s",0x17:"t",0x18:"u",0x19:"v",0x1a:"w",0x1b:"x",
        0x1c:"y",0x1d:"z",0x1e:"1",0x1f:"2",0x20:"3",0x21:"4",0x22:"5",0x23:"6",
        0x24:"7",0x25:"8",0x26:"9",0x27:"0",0x28:"Enter",0x29:"Esc",0x2a:"Bksp",
        0x2b:"Tab",0x2c:"Space",0x2d:"-",0x2e:"=",0x2f:"[",0x30:"]",0x31:"\\",
        0x33:";",0x34:"'",0x35:"`",0x36:",",0x37:".",0x38:"/",0x39:"Caps",
        0x4c:"Del",0x4f:"Right",0x50:"Left",0x51:"Down",0x52:"Up",
        0x68:"F13",0x69:"F14",0x6a:"F15",0x6b:"F16",0x6c:"F17",0x6d:"F18",
        0x6e:"F19",0x6f:"F20",0x70:"F21",0x71:"F22",0x72:"F23",0x73:"F24"}

CONSUMER = {0xcd:"PLAY/PAUSE",0xe2:"MUTE",0xe9:"VOL+",0xea:"VOL-",0xb5:"NEXT",
            0xb6:"PREV",0xb7:"STOP",0x6f:"BRIGHT+",0x70:"BRIGHT-",0x192:"CALC",
            0x19e:"LOCK",0x223:"WEB_HOME",0x224:"WEB_BACK",0x225:"WEB_FWD",
            0x182:"FAVORITES",0x2c1:"MIC_MUTE?"}


def hexs(b):
    return b.hex(" ")


def decode(which, data):
    """Return human readable interpretation of one report."""
    if not data:
        return "(empty)"
    rid, body = data[0], data[1:]

    if which == "mouse":
        if len(body) >= 3:
            btn, dx, dy = body[0], body[1], body[2]
            signed = lambda v: v - 256 if v > 127 else v
            return f"buttons=0x{btn:02x} dx={signed(dx)} dy={signed(dy)}"
        return "mouse report"

    if which == "kbd6K":
        # ID(1) + mods(1) + reserved(1) + keys(6)
        mods, keys = body[0], body[2:8]
        names = [KEYS.get(k, f"0x{k:02x}") for k in keys if k]
        return f"mods={mods:02x} {[MODS[b] for b in MODS if mods & b]} keys={names}"

    if which == "kbd17K/media":
        if rid == 1 and len(body) >= 11:
            mods, keys = body[0], body[2:11]
            names = [KEYS.get(k, f"0x{k:02x}") for k in keys if k]
            return f"[kbd rID1] mods={mods:02x} {[MODS[b] for b in MODS if mods & b]} keys={names}"
        if rid == 2 and len(body) >= 2:
            usage = body[0] | (body[1] << 8)
            return f"[MEDIA rID2] usage=0x{usage:04x} -> {CONSUMER.get(usage, 'unknown')}"
        return f"[rID{rid}] raw"

    return "?"


paths = [p for p in ("/dev/hidraw6", "/dev/hidraw7", "/dev/hidraw8") if os.path.exists(p)]
fds = {}
for p in paths:
    f = open(p, "rb", buffering=0)
    os.set_blocking(f.fileno(), False)
    fds[f.fileno()] = (p, f)

start = last = time.time()
events = 0
print(f"listening: {', '.join(f'{p} ({LABEL[p]})' for p in paths)}", flush=True)

while time.time() - start < DUR:
    r, _, _ = select.select(list(fds), [], [], 0.25)
    for fd in r:
        path, f = fds[fd]
        try:
            data = f.read(4096)
        except BlockingIOError:
            continue
        if not data:
            continue
        events += 1
        last = time.time()
        which = LABEL[path]
        print(f"{time.time()-start:7.3f}s {which:12s} | {hexs(data):<34s} | {decode(which, data)}", flush=True)
    if events and time.time() - last > IDLE:
        print(f"--- idle {IDLE:.0f}s, stopping ---", flush=True)
        break

print(f"=== {events} report(s) captured ===", flush=True)
