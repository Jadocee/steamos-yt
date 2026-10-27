#!/usr/bin/env bash
# Install YouTube on TV for SteamOS: Helium in kiosk mode with a console-style
# interface, added to the Steam library with artwork.
#
#   ./install.sh [options]
#   curl -fsSL https://raw.githubusercontent.com/jadocee/steamos-yt/main/install.sh | bash
#
# Run './install.sh --help' for the available options.
set -Eeuo pipefail

STEAMOS_YT_REF="${STEAMOS_YT_REF:-main}"
PAYLOAD=(src/bin:bin src/lib:lib src/extension:extension src/share:share assets/artwork:artwork keys:keys)

local_source() {
    local script=${BASH_SOURCE[0]:-} directory
    [[ -n $script && -f $script ]] || return 1
    directory=$(cd -- "$(dirname -- "$script")" && pwd -P)
    [[ -f $directory/src/lib/common.sh ]] || return 1
    printf '%s\n' "$directory"
}

download_source() {
    local repo=${STEAMOS_YT_REPO:-jadocee/steamos-yt} destination
    destination=$(mktemp -d)
    printf '==> Downloading steamos-yt (%s@%s)\n' "$repo" "$STEAMOS_YT_REF" >&2
    if ! curl -fsSL --retry 3 --connect-timeout 20 "https://github.com/$repo/archive/$STEAMOS_YT_REF.tar.gz" |
        tar -xz -C "$destination" --strip-components=1; then
        rm -rf "$destination"
        printf 'error: could not download steamos-yt from github.com/%s\n' "$repo" >&2
        exit 1
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
    chmod 0755 "$APP_HOME/bin/steamos-yt" "$APP_HOME/lib/steamos-yt-helper"
    printf '%s\n' "$STEAMOS_YT_VERSION" >"$APP_HOME/VERSION"
}

main() {
    local source_dir cleanup="" argument
    if ! source_dir=$(local_source); then
        source_dir=$(download_source)
        cleanup=$source_dir
    fi
    # shellcheck source=src/lib/common.sh
    source "$source_dir/src/lib/common.sh"

    for argument in "$@"; do
        if [[ $argument == -h || $argument == --help ]]; then
            "$source_dir/src/bin/steamos-yt" install --help
            [[ -z $cleanup ]] || rm -rf "$cleanup"
            return 0
        fi
    done

    refuse_root
    require_commands curl tar xz python3
    log "Copying SteamOS YT $STEAMOS_YT_VERSION to $APP_HOME"
    install_payload "$source_dir"
    [[ -z $cleanup ]] || rm -rf "$cleanup"
    exec "$APP_HOME/bin/steamos-yt" install "$@"
}

main "$@"
