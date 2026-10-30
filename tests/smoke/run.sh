#!/usr/bin/env bash
# End-to-end smoke test: installs into a throwaway HOME, launches the kiosk
# against a local HTTPS stand-in for www.youtube.com/tv, and checks the
# companion extension, the device identity, every exit path, the separate
# profile for each Steam account and the site lock.
#
#   tests/smoke/run.sh [helium-<version>-x86_64_linux.tar.xz]
#
# Without an archive the latest Helium release is downloaded. Needs python3,
# openssl and either a running display or Xvfb.
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
PORT=${SMOKE_PORT:-18443}
ARCHIVE=${1:-}
WORK=$(mktemp -d)
HOME_DIR="$WORK/home"
OUTPUT="$WORK/output"
LAUNCHER="$HOME_DIR/.local/share/steamos-yt/bin/steamos-yt"
PIDS=()

cleanup() {
    local pid
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    if [[ ${KEEP_WORK:-0} == 1 ]]; then
        echo "kept $WORK"
    else
        rm -rf "$WORK"
    fi
}
trap cleanup EXIT

run_clean() {
    env -i HOME="$HOME_DIR" PATH="$PATH" USER="${USER:-tester}" LANG=C.UTF-8 \
        DISPLAY="${DISPLAY:-}" STEAMOS_YT_ALLOW_ROOT=1 NO_COLOR=1 "$@"
}

mkdir -p "$HOME_DIR" "$OUTPUT"
echo "==> Installing into $HOME_DIR"
install_args=(--no-steam --no-desktop-entry --no-auto-update --yes)
[[ -n $ARCHIVE ]] && install_args+=(--helium-archive "$(readlink -f -- "$ARCHIVE")")
run_clean "$ROOT/install.sh" "${install_args[@]}"

if [[ -z ${DISPLAY:-} ]]; then
    for display in {90..99}; do
        [[ -e /tmp/.X11-unix/X$display ]] && continue
        Xvfb ":$display" -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
        PIDS+=($!)
        export DISPLAY=":$display"
        break
    done
    sleep 1
fi

HOSTS=(www.youtube.com sponsor.ajay.app dearrow-thumb.ajay.app returnyoutubedislikeapi.com blocked.example)
san=$(printf 'DNS:%s,' "${HOSTS[@]}")
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=www.youtube.com" \
    -addext "subjectAltName=${san%,}" -keyout "$WORK/key.pem" -out "$WORK/cert.pem" >/dev/null 2>&1
python3 "$ROOT/tests/smoke/server.py" --port "$PORT" --cert "$WORK/cert.pem" --key "$WORK/key.pem" --output "$OUTPUT" >"$WORK/server.log" 2>&1 &
PIDS+=($!)
for _ in {1..50}; do
    grep -q ready "$WORK/server.log" && break
    sleep 0.1
done

rules=$(printf 'MAP %s 127.0.0.1:'"$PORT"', ' "${HOSTS[@]}")
browser_flags=(--no-proxy-server --ignore-certificate-errors "--host-resolver-rules=${rules%, }")
[[ $(id -u) == 0 ]] && browser_flags+=(--no-sandbox)

stop_kiosk() {
    local pid=$1 pattern="[-]-user-data-dir=$HOME_DIR/"
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    pkill -f "$pattern" 2>/dev/null || true
    wait_for 10 bash -c "! pgrep -f '$pattern' >/dev/null" || true
}

wait_for() {
    local seconds=$1
    shift
    local deadline=$((SECONDS + seconds))
    until "$@"; do
        ((SECONDS < deadline)) || return 1
        sleep 0.25
    done
}

CONFIG="$HOME_DIR/.config/steamos-yt/steamos-yt.conf"
APP="$HOME_DIR/.local/share/steamos-yt"
cp "$CONFIG" "$WORK/steamos-yt.conf"
failed=0

run_scenario() {
    local scenario=$1 mode=$2 cookie=$3 pid report=report.json
    local query="exit=$mode&probe=$scenario" flags=("${browser_flags[@]}")
    shift 3
    echo "==> Scenario: $scenario (exit via $mode${1:+; $*})"
    rm -f "$OUTPUT"/*
    cp "$WORK/steamos-yt.conf" "$CONFIG"
    case $scenario in
        titles-only) echo "YT_DEARROW_THUMBNAILS=0" >>"$CONFIG" ;;
        combo) echo "YT_WINDOW=app" >>"$CONFIG" ;;
        close) echo "YT_BLOCK_ADS=0" >>"$CONFIG" ;;
        site-lock)
            report=lock.json
            query+="&lock=1"
            flags+=(--disable-popup-blocking)
            ;;
    esac
    run_clean "$LAUNCHER" launch "$@" "https://www.youtube.com/tv?$query" -- "${flags[@]}" &
    pid=$!
    PIDS+=("$pid")
    if ! wait_for 40 test -s "$OUTPUT/$report"; then
        echo "    FAIL no report from the page; launch log:"
        tail -n 30 "$HOME_DIR/.local/state/steamos-yt/launch.log" || true
        failed=1
        stop_kiosk "$pid"
        return 0
    fi
    if wait_for 20 bash -c "! kill -0 $pid 2>/dev/null"; then
        echo "    ok: kiosk closed itself"
    else
        echo "    FAIL kiosk did not close after the $mode exit request"
        failed=1
    fi
    stop_kiosk "$pid"
    if python3 "$ROOT/tests/smoke/check.py" "$OUTPUT" "$scenario" "$mode" "$cookie"; then
        echo "    ok: page checks passed"
    else
        failed=1
    fi
}

add_steam_accounts() {
    local steam="$HOME_DIR/.local/share/Steam"
    mkdir -p "$steam/userdata/111/config" "$steam/userdata/222/config" "$steam/config"
    printf '%s\n' '"users"' '{' \
        '  "76561197960265839" { "AccountName" "alpha" "PersonaName" "Alpha" "MostRecent" "1" }' \
        '  "76561197960265950" { "AccountName" "beta" "PersonaName" "Beta" "MostRecent" "0" }' \
        '}' >"$steam/config/loginusers.vdf"
}

expect_profile() {
    if [[ $1 == present && -d $APP/$2 ]] || [[ $1 == absent && ! -e $APP/$2 ]]; then
        echo "    ok: $2 $1"
    else
        echo "    FAIL $2 should be $1"
        failed=1
    fi
}

for scenario in leanback combo close titles-only:leanback; do
    run_scenario "${scenario%%:*}" "${scenario#*:}" "*"
done

echo "==> Steam accounts: the first launch inherits the shared profile, then each account keeps its own"
add_steam_accounts
run_scenario account-a leanback titles-only
run_scenario account-b leanback - --steam-account 222
run_scenario account-a-again leanback account-a --steam-account 111
expect_profile absent profile
expect_profile present profiles/111
expect_profile present profiles/222

run_scenario site-lock leanback "*"

if ((failed)); then
    echo "==> Smoke test FAILED"
    exit 1
fi
echo "==> Smoke test passed"
