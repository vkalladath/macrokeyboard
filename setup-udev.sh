#!/usr/bin/env bash
# One-time setup: grant the active session user access to this macro pad.
#
# Two different device nodes are involved:
#
#   /dev/bus/usb/...   the vendor configuration interface (1.1, EP 0x02 OUT).
#                      Needed to write mappings; has no hidraw node and no
#                      driver, so ch57x-keyboard-tool needs usbfs access.
#
#   /dev/hidraw*       the keyboard/media interfaces the overlay reads to see
#                      knob events. Shipped 0600 root:root on current Fedora,
#                      so the overlay cannot read them as a normal user.
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

# 1. Vendor config interface: lets ch57x-keyboard-tool program the mapping
#    without running as root.
SUBSYSTEM=="usb", ATTR{idVendor}=="1189", ATTR{idProduct}=="8890", TAG+="uaccess"

# 2. hidraw nodes: lets the overlay read knob events. Without this the nodes
#    are 0600 root:root and the daemon reports "permission denied".
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1189", ATTRS{idProduct}=="8890", TAG+="uaccess"
EOF

udevadm control --reload
udevadm trigger --subsystem-match=usb --action=add
udevadm trigger --subsystem-match=hidraw --action=add

echo "installed: ${RULE}"
echo
echo "Check, as your normal user:"
echo "  ls -l /dev/hidraw* | grep '1189'   # or any hidraw with a '+' ACL"
echo "  getfacl /dev/hidraw6 | grep \$USER"
