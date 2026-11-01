#!/usr/bin/env bash
# One-time setup: grant the active session user write access to the macro
# pad's vendor configuration interface (1189:8890, interface 1.1, EP 0x02).
#
# Without this, ch57x-keyboard-tool fails with
# "Access denied (insufficient permissions)" because the config interface has
# no hidraw node and /dev/bus/usb/... is root-only.
#
# Run once with sudo:   sudo ./setup-udev.sh
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "must run as root:  sudo $0" >&2
    exit 1
fi

RULE=/etc/udev/rules.d/50-usb-macrokeyboard.rules

cat > "${RULE}" <<'EOF'
# CH57x macro pad (Trisat 1189:8890)
# Grants the logged-in session user access to the vendor config interface so
# ch57x-keyboard-tool can program key mappings without running as root.
SUBSYSTEM=="usb", ATTR{idVendor}=="1189", ATTR{idProduct}=="8890", TAG+="uaccess"
EOF

udevadm control --reload
udevadm trigger --subsystem-match=usb --action=add

echo "installed: ${RULE}"
echo
echo "Verify with (as your normal user):"
echo "  getfacl /dev/bus/usb/\$(lsusb | awk '/1189:8890/{print \"00\"\$4}' | tr -d ':') 2>/dev/null"
echo "  # or simply re-run: ./upload.sh"
