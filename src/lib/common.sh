# shellcheck shell=bash disable=SC2034
# Shared helpers for steamos-yt. Sourced by bin/steamos-yt and install.sh.

STEAMOS_YT_VERSION="1.1.0"
STEAMOS_YT_REPO="${STEAMOS_YT_REPO:-jadocee/steamos-yt}"
HELIUM_REPO="imputnet/helium-linux"
HELIUM_KEY_FINGERPRINT="BE677C1989D35EAB2C5F26C9351601AD01D6378E"
HELIUM_KEEP_VERSIONS=2

APP_HOME="${APP_HOME:-${STEAMOS_YT_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/steamos-yt}}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/steamos-yt"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/steamos-yt"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/steamos-yt"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
PROFILE_DIR="$APP_HOME/profile"
HELIUM_DIR="$APP_HOME/helium"
LAUNCHER="$APP_HOME/bin/steamos-yt"
DESKTOP_FILE="$APPLICATIONS_DIR/steamos-yt.desktop"
UPDATE_UNIT="steamos-yt-update"

if [[ -t 2 && -z ${NO_COLOR:-} ]]; then
    C_BOLD=$'\e[1m' C_RED=$'\e[31m' C_GREEN=$'\e[32m' C_YELLOW=$'\e[33m' C_BLUE=$'\e[34m' C_RESET=$'\e[0m'
else
    C_BOLD="" C_RED="" C_GREEN="" C_YELLOW="" C_BLUE="" C_RESET=""
fi

QUIET="${QUIET:-0}"
ASSUME_YES="${ASSUME_YES:-0}"

log() { [[ $QUIET == 1 ]] || printf '%s==>%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_BOLD" "$*" "$C_RESET" >&2; }
info() { [[ $QUIET == 1 ]] || printf '    %s\n' "$*" >&2; }
ok() { [[ $QUIET == 1 ]] || printf '%s ✓%s  %s\n' "$C_GREEN" "$C_RESET" "$*" >&2; }
warn() { printf '%swarning:%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die() {
    printf '%serror:%s %s\n' "$C_RED" "$C_RESET" "$*" >&2
    exit 1
}
have() { command -v "$1" >/dev/null 2>&1; }

confirm() {
    local prompt=$1 default=${2:-n} reply hint="[y/N]"
    [[ $default == y ]] && hint="[Y/n]"
    [[ $ASSUME_YES == 1 ]] && return 0
    if ! { : </dev/tty; } 2>/dev/null; then
        [[ $default == y ]]
        return
    fi
    printf '%s?%s %s %s ' "$C_YELLOW" "$C_RESET" "$prompt" "$hint" >/dev/tty
    IFS= read -r reply </dev/tty || reply=""
    reply=${reply:-$default}
    [[ ${reply,,} == y || ${reply,,} == yes ]]
}

helper() {
    python3 -B -E -s "$APP_HOME/lib/steamos-yt-helper" "$@"
}

require_commands() {
    local missing=() command
    for command in "$@"; do
        have "$command" || missing+=("$command")
    done
    ((${#missing[@]} == 0)) || die "missing required command(s): ${missing[*]}"
}

refuse_root() {
    if [[ $(id -u) == 0 && ${STEAMOS_YT_ALLOW_ROOT:-0} != 1 ]]; then
        die "run steamos-yt as your normal user (for example 'deck'), not as root"
    fi
}

in_game_mode() {
    [[ ${XDG_CURRENT_DESKTOP:-} == gamescope || -n ${GAMESCOPE_WAYLAND_DISPLAY:-} ]]
}

is_steamos() {
    [[ -r /etc/os-release ]] && grep -qiE '^ID(_LIKE)?=.*steamos' /etc/os-release
}

helium_arch() {
    case "$(uname -m)" in
        x86_64 | amd64) echo x86_64 ;;
        aarch64 | arm64) echo arm64 ;;
        *) return 1 ;;
    esac
}

valid_version() {
    [[ $1 =~ ^[0-9]+(\.[0-9]+){1,4}$ ]]
}

download() {
    local url=$1 destination=$2 progress=(-sS)
    [[ -t 2 && $QUIET != 1 ]] && progress=(--progress-bar)
    mkdir -p "$(dirname "$destination")"
    if curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 "${progress[@]}" -o "$destination.part" "$url"; then
        mv -f "$destination.part" "$destination"
    else
        rm -f "$destination.part"
        return 1
    fi
}

helium_latest_version() {
    local tag="" url
    tag=$(curl -fsSL --retry 2 --connect-timeout 20 -H 'Accept: application/vnd.github+json' \
        "https://api.github.com/repos/$HELIUM_REPO/releases/latest" 2>/dev/null |
        python3 -c 'import json, sys; print(json.load(sys.stdin).get("tag_name", ""))' 2>/dev/null) || tag=""
    if ! valid_version "$tag"; then
        url=$(curl -fsSIL --retry 2 --connect-timeout 20 -o /dev/null -w '%{url_effective}' \
            "https://github.com/$HELIUM_REPO/releases/latest" 2>/dev/null) || url=""
        tag=${url##*/}
    fi
    valid_version "$tag" || return 1
    printf '%s\n' "$tag"
}

helium_current_version() {
    local target
    target=$(readlink "$HELIUM_DIR/current" 2>/dev/null) || return 1
    [[ -x $HELIUM_DIR/$target/helium ]] || return 1
    printf '%s\n' "$target"
}

helium_verify() {
    local archive=$1 signature=$1.asc keyhome status
    [[ -f $signature ]] || {
        warn "no signature found for $(basename "$archive")"
        return 1
    }
    if ! have gpg || ! have gpgv; then
        warn "gpg/gpgv are not available, so the Helium signature cannot be checked"
        return 1
    fi
    keyhome=$(mktemp -d)
    if ! GNUPGHOME=$keyhome gpg --batch --quiet --dearmor <"$APP_HOME/keys/helium.asc" >"$keyhome/helium.gpg" 2>/dev/null; then
        rm -rf "$keyhome"
        warn "could not read the bundled Helium signing key"
        return 1
    fi
    status=$(gpgv --homedir "$keyhome" --status-fd 1 --keyring "$keyhome/helium.gpg" "$signature" "$archive" 2>/dev/null) || status=""
    rm -rf "$keyhome"
    grep -q "^\[GNUPG:\] VALIDSIG .*$HELIUM_KEY_FINGERPRINT" <<<"$status"
}

helium_fetch() {
    local version=$1 arch asset base archive
    arch=$(helium_arch) || die "unsupported CPU architecture: $(uname -m)"
    asset="helium-$version-${arch}_linux.tar.xz"
    base="https://github.com/$HELIUM_REPO/releases/download/$version"
    archive="$CACHE_DIR/$asset"
    if [[ -f $archive && -f $archive.asc ]] && helium_verify "$archive" 2>/dev/null; then
        info "Using cached $asset"
    else
        info "Downloading $asset"
        download "$base/$asset.asc" "$archive.asc" || die "could not download the Helium $version signature"
        download "$base/$asset" "$archive" || die "could not download Helium $version"
    fi
    printf '%s\n' "$archive"
}

helium_unpack() {
    local archive=$1 version=$2 skip_verify=${3:-0} staging inner
    if [[ -x $HELIUM_DIR/$version/helium ]]; then
        info "Helium $version is already unpacked"
        return 0
    fi
    if helium_verify "$archive"; then
        ok "Signature verified (Helium signing key ${HELIUM_KEY_FINGERPRINT:0:4} … ${HELIUM_KEY_FINGERPRINT: -4})"
    elif [[ $skip_verify == 1 ]]; then
        warn "continuing without signature verification (--skip-verify)"
    else
        die "Helium $version failed signature verification; refusing to install it (use --skip-verify to override)"
    fi
    mkdir -p "$HELIUM_DIR"
    staging=$(mktemp -d "$HELIUM_DIR/.unpack.XXXXXX")
    info "Unpacking Helium $version"
    if ! tar -xJf "$archive" -C "$staging" --no-same-owner; then
        rm -rf "$staging"
        die "could not unpack $archive"
    fi
    inner=$(find "$staging" -mindepth 1 -maxdepth 1 -type d -name 'helium-*' -print -quit)
    if [[ -z $inner || ! -x $inner/helium || ! -x $inner/helium-wrapper ]]; then
        rm -rf "$staging"
        die "unexpected Helium archive layout in $archive"
    fi
    mv -T "$inner" "$HELIUM_DIR/$version"
    rm -rf "$staging"
}

helium_clean_cache() {
    rm -f "$CACHE_DIR"/helium-*_linux.tar.xz "$CACHE_DIR"/helium-*_linux.tar.xz.asc "$CACHE_DIR"/*.part
}

helium_activate() {
    local version=$1
    ln -sfn "$version" "$HELIUM_DIR/.current.new"
    mv -Tf "$HELIUM_DIR/.current.new" "$HELIUM_DIR/current"
}

helium_in_use() {
    local directory=$1 exe target
    for exe in /proc/[0-9]*/exe; do
        target=$(readlink "$exe" 2>/dev/null) || continue
        [[ $target == "$directory"/* ]] && return 0
    done
    return 1
}

helium_prune() {
    local current kept=0 directory name
    current=$(helium_current_version) || return 0
    while IFS= read -r directory; do
        name=$(basename "$directory")
        valid_version "$name" || continue
        if [[ $name == "$current" ]] || ((kept < HELIUM_KEEP_VERSIONS - 1)); then
            [[ $name == "$current" ]] || kept=$((kept + 1))
            continue
        fi
        if helium_in_use "$directory"; then
            info "Keeping Helium $name (still running)"
            continue
        fi
        rm -rf "$directory"
        info "Removed old Helium $name"
    done < <(find "$HELIUM_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2-)
}

steam_running() {
    pgrep -u "$(id -u)" -x steam >/dev/null 2>&1
}

steam_command() {
    if have steam; then
        echo steam
    elif [[ -x $HOME/.local/share/Steam/steam.sh ]]; then
        echo "$HOME/.local/share/Steam/steam.sh"
    else
        return 1
    fi
}

steam_stop() {
    local command waited=0
    steam_running || return 0
    if in_game_mode; then
        die "Steam is running in Game Mode and cannot be closed from here. Switch to Desktop Mode and run: $LAUNCHER steam add"
    fi
    confirm "Steam must be closed to update its library. Close Steam now?" y ||
        die "Steam was left running; close it and run: $LAUNCHER steam add"
    log "Closing Steam"
    if command=$(steam_command); then
        "$command" -shutdown >/dev/null 2>&1 </dev/null &
    elif have xdg-open; then
        xdg-open steam://exit >/dev/null 2>&1 &
    fi
    while steam_running; do
        ((waited >= 90)) && die "Steam did not close within 45 seconds; close it manually and run: $LAUNCHER steam add"
        sleep 0.5
        waited=$((waited + 1))
    done
    sleep 1
    STEAM_WAS_STOPPED=1
}

steam_restart() {
    local command
    [[ ${STEAM_WAS_STOPPED:-0} == 1 ]] || return 0
    command=$(steam_command) || {
        warn "could not find the steam command; start Steam manually"
        return 0
    }
    log "Starting Steam again"
    if have setsid; then
        setsid -f "$command" -silent >/dev/null 2>&1 </dev/null
    else
        nohup "$command" -silent >/dev/null 2>&1 </dev/null &
    fi
}
