# Macro keyboard — 3 keys + 1 knob

A cheap CH57x-family macro pad, programmed on Linux with
[`ch57x-keyboard-tool`](https://github.com/kriomant/ch57x-keyboard-tool).

```bash
cargo install ch57x-keyboard-tool     # installs to ~/.cargo/bin
```

## Layout

```
.
├── README.md
├── LICENSE                   # MIT
├── mapping.yaml              # the device mapping — source of truth
├── setup-udev.sh             # one-time sudo: grants write access
├── install-gnome-shortcut.sh # registers the mic-mute shortcut
├── mic-mute-toggle.sh        # toggles default mic source
├── run-overlay.sh            # launches the scroll menu overlay
├── overlay/                  # the overlay menu (see below)
│   ├── app.py                # GTK4 UI + menu state machine
│   ├── menus.py              # menu tree — add items here
│   ├── audio.py              # pactl helpers
│   ├── volume.py             # volume keys via uinput (gives the OSD back)
│   ├── pad.py                # hidraw reader -> knob events
│   └── style.css             # transparency / colours
├── systemd/
│   └── macropad-menu.service # run the overlay at login
└── diagnostics/
    ├── capture2.py           # decode live HID reports from all interfaces
    ├── watch_mute.py         # correlate keypresses with mic state
    └── single_press_test.py  # assert one press == one toggle
```

This folder is self-contained and portable. Nothing depends on `/tmp`.

## Device

| Property | Value |
|---|---|
| USB ID | `1189:8890` (Trisat Industrial / "Acer Communications & Multimedia") |
| Speed / power | Full Speed 12 Mbps, bus-powered 100 mA |
| Product/manufacturer/serial strings | none — all descriptors empty |
| Tool model name | `ch57x-2` |
| Layout | 3 buttons, 1 knob, 3 firmware layers (1 used) |

### Interfaces

| # | Class | Node | Notes |
|---|---|---|---|
| 1.0 | boot keyboard, 6KRO | `hidraw6` → `event18` | readable via udev ACL |
| 1.1 | **vendor config**, EP `0x02` OUT | **none** | no driver bound — needs usbfs access |
| 1.2 | 17-key rollover kbd + consumer control | `hidraw7` → `event19` | media keys land here |
| 1.3 | boot mouse | `hidraw8` → `event20`, `mouse4` | mouse emulation |

> `/dev/input/event*` is `root:input 0660` and this user is not in `input`, so
> `evtest` / `libinput` need `sudo`. `hidraw` nodes ship `0600 root:root` on
> current Fedora, so `setup-udev.sh` grants the session user access to this
> device's nodes — which is why everything here reads hidraw rather than evdev.
>
> The `hidrawN` numbers in this table are from one particular boot. **They
> change on every replug** (`hidraw6/7/8` → `hidraw9/10/11` → …), so never
> hardcode them; resolve from sysfs as `overlay/pad.py:pad_nodes()` does.

## Original problem

Out of the box the config EEPROM was unprogrammed: **every key and every
encoder detent emitted the identical report** `01 00 00 06 00 ...` (keycode
`0x06` = `c`).

This could **not** be fixed from the OS side. Because the reports were
byte-identical, `keyd`, `evdev`, `udev` or `xmodmap` cannot distinguish three
inputs that produce the same HID report. The mapping had to be written into the
device over interface `1.1`.

## Current mapping

```yaml
model: ch57x-2
orientation: normal
rows: 1
columns: 3
knobs: 1
layers:
  - buttons:
      - ["ctrl-alt-shift-m", "play", "mute"]
    knobs:
      - ccw: "f13"
        press: "f15"
        cw: "f14"
```

| Control | Sends | Notes |
|---|---|---|
| Key 1 (left) | `Ctrl+Alt+Shift+M` | bound in GNOME to mic-mute toggle |
| Key 2 (middle) | Consumer `0xCD` | play/pause |
| Key 3 (right) | Consumer `0xE2` | mute (output) |
| Knob ↻ | `F14` | overlay: next item · closed: volume up |
| Knob ↺ | `F13` | overlay: previous item · closed: volume down |
| Knob press | `F15` | opens the overlay menu |

Protocol bytes actually written to the device:

```
key 1:  03 01 11 01 01 07 10   macro, mods=0x07 (Ctrl+Shift+Alt), key=0x10 ('m')
key 2:  03 02 12 cd 00         media usage 0x00CD
key 3:  03 03 12 e2 00         media usage 0x00E2
knob ↺: 03 0d 11 01 01 00 68   macro, no modifiers, key=0x68 (F13)
knob ⏺: 03 0e 11 01 01 00 6a   macro, no modifiers, key=0x6A (F15)
knob ↻: 03 0f 11 01 01 00 69   macro, no modifiers, key=0x69 (F14)
```

## Scroll menu overlay

Clicking the knob opens a translucent overlay; scrolling moves the selection,
clicking activates it. It dismisses after **5 s** with no input, and also
dismisses as soon as it loses focus.

```
Macro pad
  ▸ Audio controls
      ├─ Switch audio source   →  ● current output
      │                            ○ each other output
      ├─ Volume up / down
      ├─ Mute output
      └─ Back
  ▸ Microphone
      ├─ Switch microphone
      ├─ Mute microphone
      └─ Back
  ▸ System
      ├─ Lock screen
      ├─ Suspend
      └─ Back
  Close menu
```

```bash
./run-overlay.sh            # normal
./run-overlay.sh --preview  # open immediately; arrow keys + Enter also work
```

Run it at login:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/macropad-menu.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now macropad-menu.service
```

### Why the knob sends F13/F14/F15

It used to send volume keys. Reusing those for menu navigation would change the
system volume — with the OSD flashing — on every detent while scrolling. So the
knob emits unused F-keys, and `overlay/app.py` interprets them:

- **overlay open** → move the selection / activate
- **overlay closed** → volume step

Volume is applied by emitting real `KEY_VOLUMEUP`/`KEY_VOLUMEDOWN` events from a
uinput virtual keyboard (`overlay/volume.py`), **not** by calling `pactl`. That
matters: because the desktop sees genuine key events it shows its usual volume
OSD and applies its own policies. If uinput is unavailable the module falls back
to `pactl`, and the OSD is lost in that case only.

The cost is that **knob volume needs the overlay running** — the device itself
no longer sends volume keys. Everything else on the pad is unaffected, and keys
2 and 3 keep working with no software running.

The virtual device appears in the system as an extra keyboard named
"Macro pad volume". It has only the two volume keys and exists only while the
overlay runs.

### Adding menu items

Edit `overlay/menus.py` only. An item is:

```python
Item("Label", action=some_callable, keep_open=True)  # or submenu="name"
```

`keep_open` leaves the overlay up so an action can be repeated (volume steps) or
so dynamic content can refresh (the `●` marker moving after a source switch).
Register any new submenu in `TITLES` and return its items from `items_for`.

### Notes on the implementation

- Reads `/dev/hidraw*` directly, so it needs no root, no `input` group and no
  Wayland global-shortcut portal. It still works when the overlay is not focused.
- Node names are resolved from sysfs by matching `1189:8890`, **not** hardcoded
  as `hidraw6` — node numbers shift on every replug and on any other USB change.
- **Reconnects on its own.** A held `hidraw` descriptor goes permanently silent
  when the device is removed — no error, no hangup, so waiting for one never
  fires. The reader therefore listens on the kernel uevent netlink socket and
  re-syncs descriptors on add/remove events, plus a 30 s re-scan as a safety net.
- **Idle cost:** one wakeup every 30 s for that safety net, zero otherwise; CPU
  was immeasurable (0 ticks over 120 s) and the uevent socket is poll-based.
  The 30 s figure is the price of surviving replugs — see `pad.py`.
- GNOME/Wayland has no `wlr-layer-shell`, so the window cannot be positioned or
  pinned above other windows; the compositor centres it. It does not steal input
  focus from the app underneath for typing, but it is a normal toplevel, so it
  appears in Alt-Tab.
- Arrow keys and Enter are accepted as a fallback, which is how you can test the
  menu with the pad unplugged.

## Why mic mute is a chord, not a media key

The CH57x consumer page used by this tool exposes **no** microphone-mute usage.
Supported: brightness, play/next/prev/stop, mute, volume up/down, calculator,
screen lock, browser keys, favourites.

So key 1 emits a rare chord that nothing else uses, and GNOME runs
`mic-mute-toggle.sh` on it. Trade-offs:

- works only while the GNOME session is unlocked;
- the chord still reaches the focused application, so an app binding
  `Ctrl+Alt+Shift+M` would also trigger. A `keyd` layer that swallows the chord
  fixes that if it ever matters.

Keys 2 and 3 are plain kernel-level HID — they work in a TTY, at the lock
screen, and without any desktop software running. The knob is different: its
volume function now lives in `overlay/app.py`, so it needs the overlay running.

## Setup (already done on this machine)

```bash
# 1. one-time: allow programming without root
sudo ./setup-udev.sh

# 2. one-time: register the mic-mute shortcut
./install-gnome-shortcut.sh

# 3. write the mapping into the device
ch57x-keyboard-tool validate < mapping.yaml
ch57x-keyboard-tool upload   mapping.yaml
```

The vendor interface has no hidraw node and `/dev/bus/usb/...` is root-only, so
programming needs either `sudo` or the udev rules that `setup-udev.sh` installs:

```
# programming (vendor config interface)
SUBSYSTEM=="usb", ATTR{idVendor}=="1189", ATTR{idProduct}=="8890", TAG+="uaccess"

# reading knob events (hidraw nodes ship 0600 root:root)
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1189", ATTRS{idProduct}=="8890", TAG+="uaccess"
```

Both grant the logged-in session user access — confirm with
`getfacl /dev/bus/usb/001/013` and `getfacl /dev/hidraw6` showing
`user:<you>:rw-`. The hidraw rule is **not** optional: without it the overlay
starts but reports `permission denied`, and the knob appears dead.

## Changing the mapping

Edit `mapping.yaml`, then:

```bash
ch57x-keyboard-tool validate < mapping.yaml
ch57x-keyboard-tool upload   mapping.yaml
```

Key names: `ch57x-keyboard-tool show-keys`
Action syntax (mouse, media, sequences, `delay()`):
<https://github.com/kriomant/ch57x-keyboard-tool/blob/master/doc/actions.md>

Example — change what the knob press opens (the overlay listens for `F15`):

```yaml
      - ccw: "f13"
        press: "f15"
        cw: "f14"
```

Don't put `volumeup`/`volumedown` back on the knob while the overlay is in use:
scrolling a menu would change the system volume on every detent.

Example — a multi-key sequence (note the 3x1 limitation below):

```yaml
      - ["ctrl-alt-shift-m", "play", "ctrl-a,ctrl-c"]
```

## Verification

Status of each piece, honestly:

| Check | Method | Result |
|---|---|---|
| All keys + knob distinct | raw `hidraw` capture | ✅ |
| Key order left→right | capture vs. labelled presses | ✅ |
| Key 1 chord bytes | `01 07 00 10` | ✅ LCtrl+LShift+LAlt + `m` |
| GNOME shortcut fires | `PAD` press → `MIC` state change | ✅ |
| No double-fire | one press ⇒ one toggle | ✅ |
| Audio layer (`pactl`) | sink list, no-op switch, volume ±5% | ✅ |
| Volume via uinput | synthetic keys moved the sink 97→100→94 | ✅ OSD path works |
| Menu trees build | `items_for()` on every menu | ✅ |
| Overlay launches | 3 s GTK4 run, no warnings | ✅ |
| **Knob → F13/F14/F15** | — | ⏳ **not yet flashed** (pad was unplugged) |
| **Overlay look & feel** | — | ⏳ needs your eyes |

The knob remap is written to `mapping.yaml` but has **not** been uploaded to the
device. Until it is, the knob still emits `VOL+`/`VOL-` and pressing it does
nothing, so the overlay will not respond to the knob. Re-upload with the pad
plugged in:

```bash
ch57x-keyboard-tool validate < mapping.yaml
ch57x-keyboard-tool upload   mapping.yaml
```

Re-run the device checks:

```bash
./diagnostics/capture2.py 60          # press keys, watch decoded reports
./diagnostics/watch_mute.py 120       # keypress vs mic state on one timeline
./diagnostics/single_press_test.py 90 # assert one press == one toggle
```

## Troubleshooting

**Keys work but the mic key does nothing** — the GNOME shortcut, not the pad.
`gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings`
should list the `macropad-micmute` entry; re-run `install-gnome-shortcut.sh`.

**Upload fails with "Access denied (insufficient permissions)"** — udev rule
missing or udev not reloaded. Run `sudo ./setup-udev.sh`, then confirm the
`getfacl` output above.

**Wrong bus/device number** — device numbers change on replug. Re-read `lsusb`;
never reuse a number from this document.

**Keys stopped working after using the vendor Windows software** — it
overwrites the same config area. Re-upload `mapping.yaml`.

**Nothing works at all, every key types `c`** — the config was wiped/reset.
This is the original factory state; re-upload `mapping.yaml`.

**Knob stopped working after replugging the pad** — the pad re-enumerates with
new `hidraw` numbers and a stale descriptor goes silent without any error. The
overlay re-syncs on udev events, so it should recover on its own within a
second; if it does not, check `journalctl --user -f` / its stderr for
`pad: attached`. Restarting the overlay is the fallback.

**Knob dead and every key dead, but `lsusb` shows the device** — the firmware
has stalled (observed once on this unit). It stops sending HID reports while
staying healthy at the USB level: authorized, powered, answering control
transfers, with `hid-generic` bound and input devices registered. No software
fix exists; **unplug and replug**. If it recurs often, suspect the cable, the
port, or USB power.

## LED modes (empirical)

`ch57x-keyboard-tool led <mode>` sends a single mode byte (`03 b0 18 <mode>`).
The OEM's published table does **not** match this unit. Measured here:

| Mode | Behaviour |
|---|---|
| 0 | off |
| **1** | reactive colour: a pressed key lights and breathes, the others go dark; fades out when idle |
| **2** | multi-colour sweep, continuous, never times out |
| 3 | all off |
| 4 | nothing — OEM claims "a single key lights when pressed"; not implemented here |
| 5 | nothing — OEM claims "white, all keys" |

Only modes 1 and 2 do anything, and neither is addressable per key.

Mode 2 is the most expensive: it animates indefinitely, drawing from the USB
port continuously, so it costs more power than the overlay daemon does. Mode 1
fades when idle; mode 0 draws nothing. For everyday use prefer **1** or **0**.

## Known limitations

- **No read-back.** The chip is write-only: the current mapping cannot be
  dumped, only overwritten. `mapping.yaml` is the only record — keep it in git.
- **No standard mic-mute usage** on this chip (see above).
- **3x1 + 1 knob**: modifiers are honoured only on the **first** key of a
  sequence. `ctrl-alt-del,1,2` works; `ctrl-alt-del,alt-1,2` cannot be done.
- **No layer switching** — this pad has no layer button, so only one of the
  three firmware layers is programmed.
- **Max 5 accords per key**, and `delay()` is unsupported on model `0x8890`.
- **Knob volume depends on the overlay.** The knob emits `F13`/`F14`, so volume
  stepping only happens while `overlay/app.py` is running. If it dies, the knob
  is inert for volume (keys 2 and 3 still work).
- **The overlay window cannot be positioned** on GNOME/Wayland (no
  `wlr-layer-shell`); the compositor decides where it appears.
- **No host-controllable per-key LEDs on this model.** The `0x8890` firmware
  accepts only a single global LED mode byte. Per-key RGB protocols exist and
  are confirmed for `0x8840`/`0x8842` and `0x514c:0x8850`, but not for this
  model — three independent projects agree (`rOzzy1987/MacroPad`'s author,
  `MacroPadStudio`'s device table, `jvspier/macropad-rebind`). Modes 0–5 give
  canned effects only; mode 1 is a reactive breathing effect that fades out
  when idle. Lighting an LED to mean "mic muted" would require custom firmware.

## License

[MIT](LICENSE) — use it, fork it, ship it, sell it. No attribution required
beyond keeping the copyright notice.

### Credits

The device protocol was learned by observing this unit and reading
[`ch57x-keyboard-tool`](https://github.com/kriomant/ch57x-keyboard-tool)
(MIT OR Apache-2.0, by kriomant), which does the actual programming. No code
from that project is included here — this repository only invokes it, and
reimplements the small amount of framing needed for LED modes and hand-verify
captures.

Prior art consulted for the LED question:
[`rOzzy1987/MacroPad`](https://github.com/rOzzy1987/MacroPad),
[`fabiodalez-dev/MacroPadStudio`](https://github.com/fabiodalez-dev/MacroPadStudio),
[`jvspier/macropad-rebind`](https://github.com/jvspier/macropad-rebind),
[`nonatofabio/macrokey-driver`](https://github.com/nonatofabio/macrokey-driver).
