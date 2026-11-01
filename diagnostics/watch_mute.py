#!/usr/bin/env python3
"""Watch hidraw6 (keyboard) and the default-source mute state on one timeline."""
import os, select, subprocess, sys, time

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0

f = open("/dev/hidraw6", "rb", buffering=0)
os.set_blocking(f.fileno(), False)

MODS = {0x01: "LCtrl", 0x02: "LShift", 0x04: "LAlt", 0x08: "LMeta"}
KEYS = {0x10: "m"}


def mute_state():
    try:
        out = subprocess.run(["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                             capture_output=True, text=True, timeout=2).stdout
        return "muted" if "yes" in out else "unmuted"
    except Exception as e:
        return f"error({e})"


start = time.time()
prev_mute = mute_state()
print(f"t=0.0  mic={prev_mute}   (watching {DUR:.0f}s)", flush=True)

while time.time() - start < DUR:
    r, _, _ = select.select([f.fileno()], [], [], 0.25)
    for _ in r:
        try:
            data = f.read(64)
        except BlockingIOError:
            continue
        if not data or len(data) < 3:
            continue
        mods, keys = data[1], data[3:9]
        names = [KEYS.get(k, f"0x{k:02x}") for k in keys if k]
        m = [MODS[b] for b in MODS if mods & b]
        print(f"t={time.time()-start:5.1f}  PAD  mods={mods:02x} {m} keys={names}", flush=True)
        time.sleep(0.35)
        new_mute = mute_state()
        if new_mute != prev_mute:
            print(f"t={time.time()-start:5.1f}  MIC  {prev_mute} -> {new_mute}", flush=True)
            prev_mute = new_mute
        else:
            print(f"t={time.time()-start:5.1f}  MIC  unchanged ({new_mute})", flush=True)

print(f"done. final mic={mute_state()}", flush=True)
