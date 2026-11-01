"""Prepare an isolated Qt Android build toolchain inside build/android/."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "build/android/toolchain"
NDK_VERSION = "28.2.13676358"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path, expected: str) -> None:
    if target.is_file() and sha256(target) == expected:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        print(f"Downloading {target.name}", flush=True)
        with urlopen(url, timeout=30) as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        if sha256(temporary) != expected:
            raise ValueError(f"SHA-256 mismatch for {target.name}; refusing this download.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def android_wheels(arch: str) -> list[Path]:
    manifest = json.loads((ROOT / "platforms/android/wheels.json").read_text())
    wheels = []
    for name in ("pyside6", "shiboken6"):
        item = manifest[arch][name]
        target = TOOLS / "wheels" / item["filename"]
        download(manifest["source"] + name + "/" + item["filename"], target, item["sha256"])
        wheels.append(target)
    return wheels


def environment(
    *, sdk: Path | None = None, ndk: Path | None = None, python: Path | None = None
) -> dict[str, str]:
    # Buildozer prints its complete environment on failure. Only forward
    # toolchain/session essentials, never unrelated account credentials.
    allowed = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "JAVA_HOME",
        "CI",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    for key, folder in {
        "UV_CACHE_DIR": "uv-cache",
        "UV_PYTHON_INSTALL_DIR": "python",
        "ANDROID_USER_HOME": "android-user",
        "GRADLE_USER_HOME": "gradle",
        "XDG_CACHE_HOME": "cache",
    }.items():
        env[key] = str(TOOLS / folder)
    target_sdk = sdk or TOOLS / "sdk"
    target_ndk = ndk or target_sdk / "ndk" / NDK_VERSION
    env.update(
        {
            "ANDROID_HOME": str(target_sdk),
            "ANDROID_SDK_ROOT": str(target_sdk),
            "ANDROID_NDK_HOME": str(target_ndk),
            "ANDROID_NDK_ROOT": str(target_ndk),
            "PYTHONUNBUFFERED": "1",
        }
    )
    if python is not None:
        prefix = python.parent.parent
        if (prefix / "pyvenv.cfg").is_file():
            env["VIRTUAL_ENV"] = str(prefix)
        env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    # The user's default Java may be newer than the pinned Gradle supports.
    candidates = [Path(env["JAVA_HOME"])] if env.get("JAVA_HOME") else []
    candidates.extend(sorted((Path.home() / ".sdkman/candidates/java").glob("17*"), reverse=True))
    candidates.extend(sorted(Path("/usr/lib/jvm").glob("*17*")))
    for candidate in candidates:
        release = candidate / "release"
        if release.is_file() and 'JAVA_VERSION="17.' in release.read_text():
            env["JAVA_HOME"] = str(candidate)
            env["PATH"] = str(candidate / "bin") + os.pathsep + env.get("PATH", "")
            break
    return env


def ensure_pip(python: Path) -> None:
    # uv venv is intentionally unseeded. p4a/Buildozer invokes `python -m pip`
    # directly, so repair existing environments as well as newly created ones.
    env = environment(python=python)
    subprocess.run(
        [str(python), "-m", "ensurepip", "--upgrade", "--default-pip"], env=env, check=True
    )
    subprocess.run([str(python), "-m", "pip", "--version"], env=env, check=True)


def ensure_sdk_layout(sdk: Path) -> Path:
    """Expose modern command-line tools at Buildozer 1.6's legacy lookup path."""
    legacy = sdk / "tools"
    manager = legacy / "bin/sdkmanager"
    if manager.is_file() and os.access(manager, os.X_OK):
        return manager
    modern = next(
        (
            root
            for root in (sdk / "cmdline-tools/latest", sdk / "cmdline-tools")
            if (root / "bin/sdkmanager").is_file() and os.access(root / "bin/sdkmanager", os.X_OK)
        ),
        None,
    )
    if modern is None:
        raise RuntimeError(f"No executable sdkmanager found under {sdk / 'cmdline-tools'}.")
    if legacy.is_symlink() and not legacy.exists():
        legacy.unlink()
    if not legacy.exists():
        legacy.symlink_to(os.path.relpath(modern, sdk), target_is_directory=True)
    elif legacy.is_dir():
        # Preserve existing legacy tools. The SDK launcher resolves its own
        # symlink before locating modern lib/sdkmanager-classpath.jar.
        manager.parent.mkdir(parents=True, exist_ok=True)
        if manager.is_symlink() and not manager.exists():
            manager.unlink()
        if manager.exists():
            raise RuntimeError(f"Refusing to replace the existing non-executable {manager}.")
        manager.symlink_to(os.path.relpath(modern / "bin/sdkmanager", manager.parent))
    else:
        raise RuntimeError(f"Refusing to replace the existing {legacy}.")
    if not manager.is_file() or not os.access(manager, os.X_OK):
        raise RuntimeError(f"Buildozer cannot execute {manager}.")
    return manager


def prepare_sdk(source: Path, *, accept_licenses: bool, env: dict[str, str]) -> Path:
    target = TOOLS / "sdk"
    source_tools = source / "cmdline-tools/latest"
    destination = target / "cmdline-tools/latest"
    if not (destination / "bin/sdkmanager").is_file():
        if not (source_tools / "bin/sdkmanager").is_file():
            raise RuntimeError(
                "Android command-line tools are missing. Install Android Studio's "
                "Command-line Tools and provide --sdk /path/to/Android/Sdk."
            )
        shutil.copytree(source_tools, destination, dirs_exist_ok=True)
    ensure_sdk_layout(target)
    manager = str(destination / "bin/sdkmanager")
    if accept_licenses:
        # Explicit CLI flag authorizes Android SDK license acceptance for this SDK.
        subprocess.run(
            [manager, f"--sdk_root={target}", "--licenses"],
            input="y\n" * 100,
            text=True,
            env=env,
            check=True,
        )
    subprocess.run(
        [
            manager,
            f"--sdk_root={target}",
            "platform-tools",
            "platforms;android-35",
            "build-tools;35.0.0",
            f"ndk;{NDK_VERSION}",
        ],
        env=env,
        check=True,
    )
    return target


def prepare(arch: str, sdk: Path, *, accept_licenses: bool) -> tuple[Path, Path, list[Path]]:
    if sys.platform not in ("linux", "darwin"):
        raise RuntimeError("Build Android on Linux/macOS; on Windows use a Linux build host or CI.")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Install uv before preparing the Android build.")
    env = environment(python=Path(sys.executable))
    wheels = android_wheels(arch)
    host = TOOLS / "host"
    python = host / "bin/python"
    if not python.is_file():
        # Cython 0.29.33, pinned by Qt's deploy defaults, has CPython 3.11 wheels.
        # Build tools use this interpreter; the app/target interpreters stay separate.
        subprocess.run([uv, "python", "install", "3.11"], env=env, check=True)
        subprocess.run([uv, "venv", "--python", "3.11", str(host)], env=env, check=True)
    ensure_pip(python)
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "PySide6==6.12.0",
            "jinja2",
            "pkginfo",
            "tqdm",
            "packaging==24.1",
            "buildozer==1.6.0",
            "cython==0.29.33",
        ],
        env=env,
        check=True,
    )
    target_sdk = prepare_sdk(sdk, accept_licenses=accept_licenses, env=env)
    return python, target_sdk, wheels
