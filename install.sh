#!/usr/bin/env bash
# Install NonSteamApps: apps from Flathub (YouTube through VacuumTube, Element,
# Jellyfin), added to the Steam library with artwork and separate sign-ins for
# each Steam account.
#
#   ./install.sh [APP...] [options]
#   curl -fsSL https://raw.githubusercontent.com/jadocee/steamos-yt/main/install.sh | bash -s -- [APP...]
#
# When piped, the rest of the project is fetched from GitHub (NONSTEAMAPPS_REPO,
# NONSTEAMAPPS_REF) or from the archive URL in NONSTEAMAPPS_SOURCE_URL.
#
# Run './install.sh --help' for the available options.
set -Eeuo pipefail

REF="${NONSTEAMAPPS_REF:-main}"
REPO="${NONSTEAMAPPS_REPO:-jadocee/steamos-yt}"
APP_HOME="${NONSTEAMAPPS_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/nonsteamapps}"
PAYLOAD=(src/bin:bin src/lib:lib src/share:share assets/artwork:artwork)

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

local_source() {
    local script=${BASH_SOURCE[0]:-} directory
    [[ -n $script && -f $script ]] || return 1
    directory=$(cd -- "$(dirname -- "$script")" && pwd -P)
    [[ -f $directory/src/lib/nonsteamapps/__init__.py ]] || return 1
    printf '%s\n' "$directory"
}

download_source() {
    local destination url
    if ! command -v curl >/dev/null || ! command -v tar >/dev/null; then
        die "curl and tar are needed to download NonSteamApps"
    fi
    url=${NONSTEAMAPPS_SOURCE_URL:-https://github.com/$REPO/archive/$REF.tar.gz}
    destination=$(mktemp -d)
    printf '==> Downloading NonSteamApps from %s\n' "$url" >&2
    if ! curl -fsSL --retry 3 --connect-timeout 20 "$url" | tar -xz -C "$destination" --strip-components=1; then
        rm -rf "$destination"
        die "could not download NonSteamApps from $url"
    fi
    printf '%s\n' "$destination"
}

install_payload() {
    local source_dir=$1 entry from to
    mkdir -p "$APP_HOME"
    for entry in "${PAYLOAD[@]}"; do
        from=$source_dir/${entry%%:*}
        to=${entry##*:}
        [[ -d $from ]] || die "incomplete source tree: missing ${entry%%:*}"
        rm -rf "$APP_HOME/.$to.new" "$APP_HOME/.$to.old"
        cp -R "$from" "$APP_HOME/.$to.new"
        if [[ -e $APP_HOME/$to ]]; then
            mv -T "$APP_HOME/$to" "$APP_HOME/.$to.old"
        fi
        mv -T "$APP_HOME/.$to.new" "$APP_HOME/$to"
        rm -rf "$APP_HOME/.$to.old"
    done
    find "$APP_HOME/lib" -name '__pycache__' -type d -prune -exec rm -rf {} +
    chmod 0755 "$APP_HOME/bin/nonsteamapps" "$APP_HOME/lib/nonsteamapps-cli"
}

main() {
    local source_dir cleanup="" argument version
    if ! source_dir=$(local_source); then
        source_dir=$(download_source)
        cleanup=$source_dir
    fi
    for argument in "$@"; do
        if [[ $argument == -h || $argument == --help ]]; then
            "$source_dir/src/bin/nonsteamapps" install --help
            [[ -z $cleanup ]] || rm -rf "$cleanup"
            return 0
        fi
    done
    if [[ $(id -u) == 0 && ${NONSTEAMAPPS_ALLOW_ROOT:-0} != 1 ]]; then
        die "run the installer as your normal user (for example 'deck'), not as root"
    fi
    command -v python3 >/dev/null || die "python3 is required"
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || die "Python 3.8 or newer is required"
    version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$source_dir/src/lib/nonsteamapps/__init__.py")
    printf '==> Copying NonSteamApps %s to %s\n' "$version" "$APP_HOME" >&2
    install_payload "$source_dir"
    [[ -z $cleanup ]] || rm -rf "$cleanup"
    exec "$APP_HOME/bin/nonsteamapps" install "$@"
}

main "$@"
