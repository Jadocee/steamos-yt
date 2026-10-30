"""NonSteamApps' own copy of Helium, the browser its web apps run in.

Helium publishes no Flatpak, so NonSteamApps installs its signed release archive:
it checks the signature against Helium's bundled public key, unpacks each version
beside the others, points ``current`` at the active one and keeps two versions.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from . import ui

REPO = "imputnet/helium-linux"
FINGERPRINT = "BE677C1989D35EAB2C5F26C9351601AD01D6378E"
KEEP = 2
TIMEOUT = 30
WRAPPER = "helium-wrapper"
_VERSION = re.compile(r"\d+(?:\.\d+){1,4}\Z")
_ARCHIVE = re.compile(r"helium-(\d+(?:\.\d+){1,4})-")


class HeliumError(RuntimeError):
    """Helium could not be downloaded, checked or installed."""


def valid_version(text: str) -> bool:
    return bool(_VERSION.match(text or ""))


def version_key(version: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def architecture() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    raise HeliumError(f"Helium has no build for this processor ({machine})")


def asset_name(version: str, arch: str) -> str:
    return f"helium-{version}-{arch}_linux.tar.xz"


def _request(url: str, accept: str = "") -> urllib.request.Request:
    headers = {"User-Agent": "nonsteamapps"}
    if accept:
        headers["Accept"] = accept
    return urllib.request.Request(url, headers=headers)


def _fetch_text(url: str, accept: str = "") -> str:
    with urllib.request.urlopen(_request(url, accept), timeout=TIMEOUT) as response:
        return response.read().decode("utf-8")


def _final_url(url: str) -> str:
    with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as response:
        return response.geturl()


def _download(url: str, target: Path) -> None:
    partial = target.with_name(target.name + ".part")
    try:
        with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as response, open(partial, "wb") as output:
            shutil.copyfileobj(response, output, 1 << 20)
        os.replace(partial, target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


class Runtime:
    """Helium versions installed under ``root``, checked against the public key in ``key``."""

    def __init__(self, root: Path, key: Path, fingerprint: str = FINGERPRINT, repo: str = REPO) -> None:
        self.root = Path(root)
        self.key = Path(key)
        self.fingerprint = fingerprint
        self.repo = repo

    @property
    def downloads(self) -> Path:
        return self.root / ".downloads"

    @property
    def widevine(self) -> Path:
        """Widevine, which Helium downloads on first use, shared by every profile."""
        return self.root / "WidevineCdm"

    @property
    def executable(self) -> Path:
        return self.root / "current" / WRAPPER

    def _complete(self, version: str) -> bool:
        return os.access(self.root / version / WRAPPER, os.X_OK)

    def current(self) -> Optional[str]:
        try:
            target = os.readlink(self.root / "current")
        except OSError:
            return None
        return target if valid_version(target) and self._complete(target) else None

    def versions(self) -> List[str]:
        """Installed versions, newest first."""
        if not self.root.is_dir():
            return []
        found = [path.name for path in self.root.iterdir() if valid_version(path.name) and self._complete(path.name)]
        return sorted(found, key=version_key, reverse=True)

    def latest(self) -> str:
        """The newest release, from GitHub's API or, failing that, its latest-release redirect."""
        try:
            tag = str(json.loads(_fetch_text(f"https://api.github.com/repos/{self.repo}/releases/latest",
                                             "application/vnd.github+json")).get("tag_name", ""))
            if valid_version(tag):
                return tag
        except (OSError, ValueError, AttributeError):
            pass
        try:
            tag = _final_url(f"https://github.com/{self.repo}/releases/latest").rstrip("/").rsplit("/", 1)[-1]
            if valid_version(tag):
                return tag
        except OSError:
            pass
        raise HeliumError("could not find Helium's latest release on GitHub")

    def download(self, version: str) -> Path:
        name = asset_name(version, architecture())
        base = f"https://github.com/{self.repo}/releases/download/{version}"
        archive = self.downloads / name
        self.downloads.mkdir(parents=True, exist_ok=True)
        ui.info(f"Downloading {name}")
        _download(f"{base}/{name}.asc", archive.with_name(name + ".asc"))
        _download(f"{base}/{name}", archive)
        return archive

    def verify(self, archive: Path) -> bool:
        """Whether ``archive`` carries a valid signature by Helium's key."""
        signature = Path(f"{archive}.asc")
        if not signature.is_file() or not (shutil.which("gpg") and shutil.which("gpgv")):
            return False
        with tempfile.TemporaryDirectory() as home:
            keyring = Path(home) / "helium.gpg"
            dearmored = subprocess.run(
                ["gpg", "--batch", "--quiet", "--homedir", home, "--dearmor", "--output", str(keyring), str(self.key)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
            )
            if dearmored.returncode != 0:
                return False
            status = subprocess.run(
                ["gpgv", "--homedir", home, "--status-fd", "1", "--keyring", str(keyring), str(signature), str(archive)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            ).stdout
        return any(
            line.startswith("[GNUPG:] VALIDSIG ") and self.fingerprint in line.split()[2:]
            for line in status.splitlines()
        )

    def unpack(self, archive: Path, version: str) -> None:
        if self._complete(version):
            return
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".unpack.", dir=str(self.root)))
        try:
            result = subprocess.run(
                ["tar", "-xJf", str(archive), "-C", str(staging), "--no-same-owner"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise HeliumError(f"could not unpack {Path(archive).name}: {result.stderr.strip()}")
            inner = next((path for path in staging.iterdir() if path.is_dir() and path.name.startswith("helium-")), None)
            if inner is None or not all(os.access(inner / name, os.X_OK) for name in ("helium", WRAPPER)):
                raise HeliumError(f"unexpected Helium archive layout in {Path(archive).name}")
            target = self.root / version
            if target.exists():
                shutil.rmtree(target)
            inner.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def activate(self, version: str) -> None:
        link = self.root / ".current.new"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(version)
        os.replace(link, self.root / "current")

    def in_use(self, version: str) -> bool:
        folder = str(self.root / version) + os.sep
        for exe in Path("/proc").glob("[0-9]*/exe"):
            try:
                if os.readlink(exe).startswith(folder):
                    return True
            except OSError:
                continue
        return False

    def prune(self) -> List[str]:
        """Delete all but the active version and the newest other one, unless still running."""
        current = self.current()
        keep = [current] if current else []
        for version in self.versions():
            if len(keep) >= KEEP:
                break
            if version not in keep:
                keep.append(version)
        removed = []
        for version in self.versions():
            if version not in keep and not self.in_use(version):
                shutil.rmtree(self.root / version)
                removed.append(version)
        return removed

    def install(self, archive: Optional[Path] = None, verify: bool = True) -> str:
        """Install the newest release, or ``archive`` (with its ``.asc`` signature beside it)."""
        if archive is not None:
            archive = Path(archive).resolve()
            match = _ARCHIVE.match(archive.name)
            if not match:
                raise HeliumError(f"{archive.name} is not named like a Helium release archive")
            version = match.group(1)
        else:
            version = self.latest()
            if self._complete(version):
                self.activate(version)
                return version
            archive = self.download(version)
        if self.verify(archive):
            ui.ok(f"Checked Helium {version}'s signature (key {self.fingerprint[:4]} … {self.fingerprint[-4:]})")
        elif verify:
            raise HeliumError(
                f"Helium {version} failed its signature check, so it was not installed "
                "(gpg and gpgv are needed; --skip-verify overrides this, which is not recommended)"
            )
        else:
            ui.warn(f"installing Helium {version} without checking its signature (--skip-verify)")
        self.unpack(archive, version)
        self.activate(version)
        self.prune()
        shutil.rmtree(self.downloads, ignore_errors=True)
        return version

    def update(self) -> Optional[str]:
        """Install a newer release if there is one; return its version."""
        latest = self.latest()
        current = self.current()
        if current and version_key(latest) <= version_key(current):
            return None
        return self.install()

    def rollback(self) -> str:
        current = self.current()
        others = [version for version in self.versions() if version != current]
        if not others:
            raise HeliumError("no other Helium version is installed to switch back to")
        self.activate(others[0])
        return others[0]

    def remove(self) -> None:
        if self.root.is_dir():
            shutil.rmtree(self.root)
