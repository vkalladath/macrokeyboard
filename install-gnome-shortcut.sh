#!/usr/bin/env bash
# Register a GNOME custom shortcut so the pad's key 1 (which emits
# ctrl-alt-shift-m) runs mic-mute-toggle.sh.
#
# Safe to re-run: it appends one entry and leaves existing shortcuts alone.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="${DIR}/mic-mute-toggle.sh"
SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
KEY_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/macropad-micmute/"
BINDING="<Control><Alt><Shift>m"

[[ -x "${CMD}" ]] || { echo "missing or not executable: ${CMD}" >&2; exit 1; }

current="$(gsettings get "${SCHEMA}" custom-keybindings)"

if [[ "${current}" == *"macropad-micmute"* ]]; then
    echo "shortcut entry already registered; refreshing its values"
    updated="${current}"
elif [[ "${current}" == "@as []" || "${current}" == "[]" ]]; then
    updated="['${KEY_PATH}']"
else
    updated="${current%]}, '${KEY_PATH}']"
fi

gsettings set "${SCHEMA}" custom-keybindings "${updated}"

K="${SCHEMA}.custom-keybinding:${KEY_PATH}"
gsettings set "${K}" name "Toggle Microphone"
gsettings set "${K}" command "${CMD}"
gsettings set "${K}" binding "${BINDING}"

echo "registered: ${BINDING}  ->  ${CMD}"
echo
echo "custom-keybindings list:"
gsettings get "${SCHEMA}" custom-keybindings
