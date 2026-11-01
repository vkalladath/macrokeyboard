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
├── mapping.yaml              # the device mapping — source of truth
├── setup-udev.sh             # one-time sudo: grants write access
├── install-gnome-shortcut.sh # registers the mic-mute shortcut
├── mic-mute-toggle.sh        # toggles default mic source
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
| 1.0 | boot keyboard, 6KRO | `hidraw6` → `event18` | world-writable |
| 1.1 | **vendor config**, EP `0x02` OUT | **none** | no driver bound — needs usbfs access |
| 1.2 | 17-key rollover kbd + consumer control | `hidraw7` → `event19` | media keys land here |
| 1.3 | boot mouse | `hidraw8` → `event20`, `mouse4` | mouse emulation |

> `/dev/input/event*` is `root:input 0660` and this user is not in `input`, so
> `evtest` / `libinput` need `sudo`. Raw `hidraw` nodes are `0666`, which is why
> every diagnostic here reads hidraw instead.

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
      - ccw: "volumedown"
        press: null
        cw: "volumeup"
```

| Control | Sends | Notes |
|---|---|---|
| Key 1 (left) | `Ctrl+Alt+Shift+M` | bound in GNOME to mic-mute toggle |
| Key 2 (middle) | Consumer `0xCD` | play/pause |
| Key 3 (right) | Consumer `0xE2` | mute (output) |
| Knob ↻ | Consumer `0xE9` | volume up |
| Knob ↺ | Consumer `0xEA` | volume down |
| Knob press | — | unassigned, available |

Protocol bytes actually written to the device:

```
key 1:  03 01 11 01 01 07 10   macro, mods=0x07 (Ctrl+Shift+Alt), key=0x10 ('m')
key 2:  03 02 12 cd 00         media usage 0x00CD
key 3:  03 03 12 e2 00         media usage 0x00E2
knob ↺: 03 0d 12 ea 00         media usage 0x00EA
knob ↻: 03 0f 12 e9 00         media usage 0x00E9
```

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

Keys 2, 3 and the knob are plain kernel-level HID — they work in a TTY, at the
lock screen, and without any desktop software running.

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
programming needs either `sudo` or the udev rule that `setup-udev.sh` installs:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="1189", ATTR{idProduct}=="8890", TAG+="uaccess"
```

It grants the logged-in session user `rw` on the device node — confirm with
`getfacl /dev/bus/usb/001/013` showing `user:<you>:rw-`.

## Changing the mapping

Edit `mapping.yaml`, then:

```bash
ch57x-keyboard-tool validate < mapping.yaml
ch57x-keyboard-tool upload   mapping.yaml
```

Key names: `ch57x-keyboard-tool show-keys`
Action syntax (mouse, media, sequences, `delay()`):
<https://github.com/kriomant/ch57x-keyboard-tool/blob/master/doc/actions.md>

Example — assign the knob press:

```yaml
      - ccw: "volumedown"
        press: "play"
        cw: "volumeup"
```

Example — a multi-key sequence (note the 3x1 limitation below):

```yaml
      - ["ctrl-alt-shift-m", "play", "ctrl-a,ctrl-c"]
```

## Verification

All checks below were run against the live device.

| Check | Method | Result |
|---|---|---|
| All keys + knob distinct | raw `hidraw` capture | ✅ each emits its own usage |
| Key order left→right | capture vs. labelled presses | ✅ matches `mapping.yaml` |
| Key 1 chord bytes | `01 07 00 10` | ✅ LCtrl+LShift+LAlt + `m` |
| Knob direction | ↻ `0xE9`, ↺ `0xEA` | ✅ clockwise = louder |
| GNOME shortcut fires | `PAD` press → `MIC` state change | ✅ |
| No double-fire | one press ⇒ one toggle | ✅ |

Re-run any of these:

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

## Known limitations

- **No read-back.** The chip is write-only: the current mapping cannot be
  dumped, only overwritten. `mapping.yaml` is the only record — keep it in git.
- **No standard mic-mute usage** on this chip (see above).
- **3x1 + 1 knob**: modifiers are honoured only on the **first** key of a
  sequence. `ctrl-alt-del,1,2` works; `ctrl-alt-del,alt-1,2` cannot be done.
- **No layer switching** — this pad has no layer button, so only one of the
  three firmware layers is programmed.
- **Max 5 accords per key**, and `delay()` is unsupported on model `0x8890`.
