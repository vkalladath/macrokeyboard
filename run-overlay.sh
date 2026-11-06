#!/usr/bin/env bash
# Launch the macro pad overlay menu.
#
#   ./run-overlay.sh            normal: knob opens/navigates the menu
#   ./run-overlay.sh --preview  open the menu immediately (arrow keys work too)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec python3 -m overlay.app "$@"
