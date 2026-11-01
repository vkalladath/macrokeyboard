#!/usr/bin/env python3
"""Definitive test: does ONE key1 press toggle the mic exactly once?"""
import os, select, subprocess, sys, time

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0


def mute():
    out = subprocess.run(["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                         capture_output=True, text=True, timeout=2).stdout
    return "muted" if "yes" in out else "unmuted"


def set_mute(state):
    subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", state], check=True)


# Start from a known state.
set_mute("0")
print(f"reset: mic={mute()}", flush=True)

f = open("/dev/hidraw6", "rb", buffering=0)
os.set_blocking(f.fileno(), False)
start = time.time()
presses = 0

while time.time() - start < DUR and presses == 0:
    r, _, _ = select.select([f.fileno()], [], [], 0.25)
    for _ in r:
        try:
            data = f.read(64)
        except BlockingIOError:
            continue
        # count only presses, not releases
        if data and len(data) >= 4 and data[3] == 0x10:
            presses += 1
            print(f"t={time.time()-start:5.1f}  PRESS detected (mods={data[1]:02x}, key=m)", flush=True)

if presses == 0:
    print("no press seen within timeout", flush=True)
    sys.exit(0)

# Sample the mute state for 2s after the single press.
final = None
for i in range(10):
    time.sleep(0.2)
    final = mute()
    print(f"  +{(i+1)*0.2:.1f}s  mic={final}", flush=True)

print(flush=True)
if final == "muted":
    print("RESULT: single press -> exactly ONE toggle (correct)")
else:
    print("RESULT: single press -> net ZERO toggles (DOUBLE-FIRE problem)")
