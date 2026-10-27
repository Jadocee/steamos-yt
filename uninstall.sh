#!/usr/bin/env bash
# Remove SteamOS YT. Add --purge to also delete settings and YouTube sign-in data.
set -Eeuo pipefail

app_home="${STEAMOS_YT_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/steamos-yt}"
launcher="$app_home/bin/steamos-yt"
if [[ -x $launcher ]]; then
    exec "$launcher" uninstall "$@"
fi

purge=0 assume_yes=0
for argument in "$@"; do
    case $argument in
        --purge) purge=1 ;;
        -y | --yes) assume_yes=1 ;;
    esac
done

leftovers=()
for directory in "$app_home" "${XDG_CONFIG_HOME:-$HOME/.config}/steamos-yt" \
    "${XDG_STATE_HOME:-$HOME/.local/state}/steamos-yt" "${XDG_CACHE_HOME:-$HOME/.cache}/steamos-yt"; do
    [[ -d $directory && $directory == */steamos-yt ]] && leftovers+=("$directory")
done

if ((${#leftovers[@]} == 0)); then
    printf 'SteamOS YT is not installed.\n' >&2
    exit 0
fi
if ((purge == 0)); then
    printf 'SteamOS YT is already uninstalled. Run with --purge to delete the remaining settings and sign-in data:\n' >&2
    printf '  %s\n' "${leftovers[@]}" >&2
    exit 0
fi
if ((assume_yes == 0)); then
    printf 'Delete these folders, including your YouTube sign-in data?\n' >&2
    printf '  %s\n' "${leftovers[@]}" >&2
    read -r -p '[y/N] ' reply </dev/tty || reply=""
    [[ ${reply,,} == y || ${reply,,} == yes ]] || exit 1
fi
rm -rf "${leftovers[@]}"
printf 'Removed the remaining SteamOS YT data.\n' >&2
