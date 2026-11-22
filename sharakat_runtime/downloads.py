"""Pinned, checksum-verified downloads of the native binaries the runtime manages.

Every artefact is pinned to an exact upstream URL and SHA-256. A mismatch is a
hard failure: nothing unverified is ever extracted or executed. To upgrade a
component, change the version, URL and hash together (and record why in the
architecture document).
"""
from __future__ import annotations

import hashlib
import shutil
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Artifact:
    name: str
    version: str
    url: str
    sha256: str
    # Archive members to keep (prefixes, POSIX style). Empty keeps everything.
    keep: tuple[str, ...] = ()
    # Directory inside the archive that becomes the install root.
    strip: str = ""


POSTGRES_VERSION = "16.16-1"
_EDB = "https://get.enterprisedb.com/postgresql"
_PG_KEEP = ("pgsql/bin/", "pgsql/lib/", "pgsql/share/")

GARNET_VERSION = "2.2.13"
_GARNET = f"https://github.com/microsoft/garnet/releases/download/v{GARNET_VERSION}"

# (component, os_key, arch) -> artifact
PINNED: dict[tuple[str, str, str], Artifact] = {
    ("postgres", "windows", "x64"): Artifact(
        "postgres", POSTGRES_VERSION, f"{_EDB}/postgresql-{POSTGRES_VERSION}-windows-x64-binaries.zip",
        "5c0d06f3d26a929ecb36dd931409f1e51a4181355794a259b90aae8bffc57a9f", _PG_KEEP, "pgsql"),
    # EDB macOS binaries are universal (x86_64 + arm64).
    ("postgres", "macos", "x64"): Artifact(
        "postgres", POSTGRES_VERSION, f"{_EDB}/postgresql-{POSTGRES_VERSION}-osx-binaries.zip",
        "48d4f9870a929d2ac3488620f18271ab5c6e8221574a3d48f58fa66ca569c137", _PG_KEEP, "pgsql"),
    ("postgres", "macos", "arm64"): Artifact(
        "postgres", POSTGRES_VERSION, f"{_EDB}/postgresql-{POSTGRES_VERSION}-osx-binaries.zip",
        "48d4f9870a929d2ac3488620f18271ab5c6e8221574a3d48f58fa66ca569c137", _PG_KEEP, "pgsql"),
    ("garnet", "windows", "x64"): Artifact(
        "garnet", GARNET_VERSION, f"{_GARNET}/win-x64-based-readytorun.zip",
        "cc8212d7c7a671c490e5c87967fc43025a22215922bdbdad5eccff00915c7b82", (), "net10.0"),
    ("garnet", "windows", "arm64"): Artifact(
        "garnet", GARNET_VERSION, f"{_GARNET}/win-arm64-based-readytorun.zip",
        "b82adae8be12bb0c68e0bae6b959590897771157e3aaf5ad8be843d26eb54ff2", (), "net10.0"),
    ("garnet", "linux", "x64"): Artifact(
        "garnet", GARNET_VERSION, f"{_GARNET}/linux-x64-based.tar.xz",
        "23a4f19d5ffd1c533f1db7cc9ef4c00a5f811aa2914544cc819fd23215fa557c", (), "net10.0"),
    ("garnet", "linux", "arm64"): Artifact(
        "garnet", GARNET_VERSION, f"{_GARNET}/linux-arm64-based.tar.xz",
        "103026aa9934ba8cbaefc3c843d91a38a75e75a78ec185ff23446db87322c969", (), "net10.0"),
    ("garnet", "macos", "x64"): Artifact(
        "garnet", GARNET_VERSION, f"{_GARNET}/osx-x64-based.tar.xz",
        "6609dff0a48c3f2bd327111b03ab2a7cc7769ebfabbd7cb3de58a8ac30748227", (), "net10.0"),
    ("garnet", "macos", "arm64"): Artifact(
        "garnet", GARNET_VERSION, f"{_GARNET}/osx-arm64-based.tar.xz",
        "be12fae4a7aef7fff91ccd19e664259e411b96434e972596d294603afc17dbd8", (), "net10.0"),
}

# Garnet's release builds are framework-dependent on .NET 10. The official
# Microsoft install scripts put a private runtime under the runtime directory
# (no administrator rights, nothing installed system-wide).
DOTNET_CHANNEL = "10.0"
DOTNET_INSTALL_PS1 = "https://dot.net/v1/dotnet-install.ps1"
DOTNET_INSTALL_SH = "https://dot.net/v1/dotnet-install.sh"


class DownloadError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(artifact: Artifact, downloads_dir: Path, log=print) -> Path:
    """Download (or reuse a cached copy of) an artifact and verify its hash."""
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target = downloads_dir / PurePosixPath(artifact.url).name
    if target.is_file() and sha256_file(target) == artifact.sha256:
        return target
    partial = target.with_suffix(target.suffix + ".partial")
    log(f"Downloading {artifact.name} {artifact.version} from {artifact.url}")
    request = urllib.request.Request(artifact.url, headers={"User-Agent": "sharakat-runtime"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out, length=1024 * 1024)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"Could not download {artifact.url}: {exc}") from exc
    actual = sha256_file(partial)
    if actual != artifact.sha256:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"Checksum mismatch for {artifact.url}: expected {artifact.sha256}, got {actual}")
    partial.replace(target)
    return target


def _member_target(name: str, artifact: Artifact, destination: Path) -> Path | None:
    posix = name.replace("\\", "/")
    if artifact.keep and not posix.startswith(artifact.keep):
        return None
    relative = PurePosixPath(posix)
    if artifact.strip:
        try:
            relative = relative.relative_to(artifact.strip)
        except ValueError:
            return None
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return None
    resolved = (destination / Path(*relative.parts)).resolve()
    if not resolved.is_relative_to(destination.resolve()):
        return None   # path traversal guard
    return resolved


def extract(archive: Path, artifact: Artifact, destination: Path) -> Path:
    """Extract the kept members of a verified archive into destination."""
    staging = destination.with_name(destination.name + ".extracting")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                target = _member_target(info.filename, artifact, staging)
                if target is None or info.is_dir():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
                mode = (info.external_attr >> 16) & 0o777
                if mode:
                    target.chmod(mode)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                target = _member_target(member.name, artifact, staging)
                if target is None or not (member.isfile() or member.issym()):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                if member.issym():
                    link = (target.parent / member.linkname).resolve()
                    if link.is_relative_to(staging.resolve()):
                        target.symlink_to(member.linkname)
                    continue
                with bundle.extractfile(member) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
                target.chmod(member.mode & 0o777 or 0o644)
    if destination.exists():
        shutil.rmtree(destination)
    staging.replace(destination)
    return destination


def install_artifact(artifact: Artifact, downloads_dir: Path, destination: Path, log=print) -> Path:
    marker = destination / ".sharakat-artifact"
    expected = f"{artifact.name} {artifact.version} {artifact.sha256}"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == expected:
        return destination
    archive = fetch(artifact, downloads_dir, log)
    log(f"Extracting {archive.name}")
    extract(archive, artifact, destination)
    marker.write_text(expected + "\n", encoding="utf-8")
    return destination
