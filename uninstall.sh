#!/usr/bin/env bash
# Remove NonSteamApps, its Steam shortcuts and the apps it installed. Add --purge
# to also delete every app's sign-in data and your settings.
set -Eeuo pipefail

app_home="${NONSTEAMAPPS_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/nonsteamapps}"
launcher="$app_home/bin/nonsteamapps"
if [[ -x $launcher ]]; then
    exec "$launcher" uninstall "$@"
fi

settings="${XDG_CONFIG_HOME:-$HOME/.config}/nonsteamapps"
purge=0 assume_yes=0
for argument in "$@"; do
    case $argument in
        --purge) purge=1 ;;
        -y | --yes) assume_yes=1 ;;
    esac
done

if [[ ! -d $settings ]]; then
    printf 'NonSteamApps is not installed.\n' >&2
    exit 0
fi
if ((purge == 0)); then
    printf 'NonSteamApps is already uninstalled. Run with --purge to delete its settings in %s\n' "$settings" >&2
    exit 0
fi
if ((assume_yes == 0)); then
    read -r -p "Delete $settings? [y/N] " reply </dev/tty || reply=""
    [[ ${reply,,} == y || ${reply,,} == yes ]] || exit 1
fi
rm -rf "$settings"
printf 'Removed the remaining NonSteamApps settings.\n' >&2
