#!/usr/bin/env bash
# End-to-end check of the shipped scripts in a throwaway home: install.sh with a
# fake flatpak and two Steam accounts, a launch through the link Steam runs, and
# uninstall.sh. Needs only bash and python3.
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
WORK=$(mktemp -d)
HOME_DIR="$WORK/home"
STEAM="$HOME_DIR/.local/share/Steam"
PROGRAM="$HOME_DIR/.local/share/nonsteamapps"
failed=0
trap 'rm -rf "$WORK"' EXIT

run() {
    env -i HOME="$HOME_DIR" PATH="$WORK/bin:$PATH" USER=deck LANG=C.UTF-8 NO_COLOR=1 NONSTEAMAPPS_ALLOW_ROOT=1 \
        FAKE_FLATPAK_STATE="$WORK/flatpak.json" FAKE_FLATPAK_LOG="$WORK/flatpak.log" "$@"
}

check() {
    local message=$1
    shift
    if "$@"; then
        echo "    ok: $message"
    else
        echo "    FAIL $message"
        failed=1
    fi
}

shortcut_names() {
    python3 -I - "$ROOT/src/lib" "$STEAM/userdata/$1/config/shortcuts.vdf" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from nonsteamapps import vdf
path = Path(sys.argv[2])
entries = vdf.loads_binary(path.read_bytes()).get("shortcuts").values() if path.exists() else []
print(" ".join(sorted(entry.get("AppName") for entry in entries)))
EOF
}

mkdir -p "$WORK/bin" "$STEAM/userdata/111/config" "$STEAM/userdata/222/config" "$STEAM/config"
ln -s "$ROOT/tests/fakes/flatpak" "$WORK/bin/flatpak"
printf '%s\n' '"users"' '{' \
    '  "76561197960265839" { "AccountName" "alpha" "PersonaName" "Alpha" "MostRecent" "1" }' \
    '  "76561197960265950" { "AccountName" "beta" "PersonaName" "Beta" "MostRecent" "0" }' \
    '}' >"$STEAM/config/loginusers.vdf"

echo "==> install.sh"
run "$ROOT/install.sh" --yes --no-auto-update >"$WORK/install.log" 2>&1 || {
    cat "$WORK/install.log"
    exit 1
}
check "every app has a link to the launcher" test -L "$PROGRAM/apps/youtube" -a -L "$PROGRAM/apps/element" -a -L "$PROGRAM/apps/jellyfin" -a -L "$PROGRAM/apps/localsend"
check "both accounts list every app" test "$(shortcut_names 111)|$(shortcut_names 222)" == "Element Jellyfin LocalSend YouTube|Element Jellyfin LocalSend YouTube"
check "the artwork was copied" test "$(find "$STEAM/userdata/222/config/grid" -name '*_hero.jpg' | wc -l)" -eq 4

echo "==> launch through the link Steam runs"
: >"$WORK/flatpak.log"
run "$PROGRAM/apps/jellyfin" --steam-account 222 --verbose >/dev/null
run "$PROGRAM/apps/youtube" --steam-account 222
check "Jellyfin's profile for the account was created first" grep -qF '["run", "org.jellyfin.JellyfinDesktop", "--create-profile", "steam-222"]' "$WORK/flatpak.log"
check "Jellyfin started with that profile" grep -qF '"--tv", "--fullscreen", "--profile=steam-222"]' "$WORK/flatpak.log"
check "VacuumTube started with the account's folder" grep -qF "\"--portable=$HOME_DIR/.var/app/rocks.shy.VacuumTube/config/VacuumTube-steam-222\"]" "$WORK/flatpak.log"
check "the launch was logged" grep -q 'starting VacuumTube for Steam account 222' "$HOME_DIR/.local/state/nonsteamapps/youtube.log"

echo "==> uninstall.sh"
run "$ROOT/uninstall.sh" --yes >"$WORK/uninstall.log" 2>&1 || {
    cat "$WORK/uninstall.log"
    exit 1
}
check "the program folder is gone" test ! -e "$PROGRAM"
check "the shortcuts are gone" test -z "$(shortcut_names 111)$(shortcut_names 222)"
check "the apps it installed were uninstalled" grep -q '"apps": {}' "$WORK/flatpak.json"

if ((failed)); then
    echo "==> Sandbox test FAILED"
    exit 1
fi
echo "==> Sandbox test passed"
