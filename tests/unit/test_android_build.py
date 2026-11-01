import argparse
import configparser
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import android, android_setup


def mock_qt_wheel(stage: Path, wheel: Path, arch: str) -> None:
    with zipfile.ZipFile(wheel, "w") as archive:
        for member in android.qt_native_members(stage, arch).values():
            archive.writestr(member, f"Android wheel fixture: {member}")


@pytest.mark.parametrize("arch,abi", [("aarch64", "arm64-v8a"), ("x86_64", "x86_64")])
def test_refresh_qt_cache_updates_reused_distribution_without_removing_other_libraries(
    tmp_path: Path, arch: str, abi: str
) -> None:
    stage = tmp_path / arch
    stage.mkdir()
    (stage / "pysidedeploy.spec").write_text("[qt]\nmodules = Widgets\n")
    wheel = tmp_path / "qt.whl"
    mock_qt_wheel(stage, wheel, arch)
    # A fresh build must not create a partial cache or distribution.
    android.refresh_qt_native_cache(stage, wheel, arch)
    assert not (stage / ".buildozer").exists()
    base = stage / f".buildozer/android/platform/build-{abi}"
    for relative in (f"build/libs_collections/epubify/{abi}", f"dists/epubify/libs/{abi}"):
        destination = base / relative
        destination.mkdir(parents=True)
        (destination / "libssl.so").write_bytes(b"keep compiled OpenSSL")
        (destination / "QtCore.abi3.so").write_bytes(b"outdated Qt file")
    android.refresh_qt_native_cache(stage, wheel, arch)
    for relative in (f"build/libs_collections/epubify/{abi}", f"dists/epubify/libs/{abi}"):
        destination = base / relative
        for module in ("Svg", "QuickControls2", "Core", "Widgets"):
            assert (destination / f"Qt{module}.abi3.so").read_bytes().startswith(b"Android wheel")
        assert (destination / f"libplugins_imageformats_qsvg_{abi}.so").exists()
        assert (destination / f"libplugins_iconengines_qsvgicon_{abi}.so").exists()
        assert (destination / "libssl.so").read_bytes() == b"keep compiled OpenSSL"
        assert not list(destination.glob("*.part"))


def test_refresh_qt_cache_rejects_incomplete_wheel_before_writing(tmp_path: Path) -> None:
    wheel = tmp_path / "qt.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("PySide6/QtCore.abi3.so", b"incomplete fixture")
    with pytest.raises(ValueError, match="QtSvg.abi3.so"):
        android.refresh_qt_native_cache(tmp_path, wheel, "x86_64")
    assert not (tmp_path / ".buildozer").exists()


@pytest.mark.parametrize("arch,abi", [("aarch64", "arm64-v8a"), ("x86_64", "x86_64")])
def test_installer_reset_preserves_compiled_recipes_and_target_packages(
    tmp_path: Path, arch: str, abi: str
) -> None:
    stage = tmp_path / arch
    build = stage / f".buildozer/android/platform/build-{abi}/build"
    installer = build / "venv"
    installer.mkdir(parents=True)
    (installer / "pyvenv.cfg").write_text("version = 3.14.2\n")
    (installer / "mixed-pip-files").touch()
    for relative in (
        "other_builds/openssl/libssl.so",
        "python-installs/epubify/typing_extensions.py",
    ):
        marker = build / relative
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("retain expensive build outputs")
    android.reset_p4a_installer(stage, arch)
    assert not installer.exists()
    assert (
        build / "other_builds/openssl/libssl.so"
    ).read_text() == "retain expensive build outputs"
    assert (build / "python-installs/epubify/typing_extensions.py").exists()
    android.reset_p4a_installer(stage, arch)  # Fresh checkout/retry is a no-op.


def test_installer_reset_refuses_symlinks_and_non_venv_directories(tmp_path: Path) -> None:
    installer = tmp_path / "stage/.buildozer/android/platform/build-x86_64/build/venv"
    installer.parent.mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    (other / "pyvenv.cfg").touch()
    installer.symlink_to(other, target_is_directory=True)
    with pytest.raises(RuntimeError, match="Refusing"):
        android.reset_p4a_installer(tmp_path / "stage", "x86_64")
    assert (other / "pyvenv.cfg").exists()
    installer.unlink()
    installer.mkdir()
    with pytest.raises(RuntimeError, match="Refusing"):
        android.reset_p4a_installer(tmp_path / "stage", "x86_64")
    assert installer.is_dir()


def test_android_svg_plugins_are_added_without_dropping_existing_settings(tmp_path: Path) -> None:
    target = tmp_path / "pysidedeploy.spec"
    target.write_text(
        "[android]\nplugins = platforms_qtforandroid,imageformats_qjpeg\n[app]\ntitle = Epubify\n"
    )
    android.prepare_qt_config(tmp_path)
    config = configparser.ConfigParser()
    config.read(target)
    assert set(config["android"]["plugins"].split(",")) == {
        "platforms_qtforandroid",
        "imageformats_qjpeg",
        "imageformats_qsvg",
        "iconengines_qsvgicon",
    }
    assert config["app"]["title"] == "Epubify"


@pytest.mark.parametrize(
    "before,after,message",
    [
        ('ifaddr = "0.2.0"', 'ifaddr = "0.3.0"', "local ifaddr recipe"),
        ('cryptography = "50.0.2"', 'cryptography = ">=50"', "exact pins"),
        ("min_api = 28", "min_api = 23", "minimum API"),
    ],
)
def test_android_profile_rejects_unreviewed_recipe_changes(
    monkeypatch, tmp_path: Path, before: str, after: str, message: str
) -> None:
    original = (android.ROOT / "platforms/android/runtime.toml").read_text()
    manifest = tmp_path / "platforms/android/runtime.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(original.replace(before, after))
    monkeypatch.setattr(android, "ROOT", tmp_path)
    with pytest.raises(ValueError, match=message):
        android.android_profile()


def test_installed_p4a_selects_local_recipes_without_legacy_ifaddr_patch() -> None:
    """Optional toolchain integration; never downloads or compiles dependencies."""
    host = android.ROOT / "build/android/toolchain/host/bin/python"
    p4a = android.ROOT / "build/android/aarch64/.buildozer/android/platform/python-for-android"
    if not host.is_file() or not (p4a / "pythonforandroid/recipe.py").is_file():
        pytest.skip("Requires the prepared Android host and cached Qt-pinned p4a checkout")
    probe = """
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from pythonforandroid.recipe import Recipe, PyProjectRecipe
ctx = SimpleNamespace(
    local_recipes=sys.argv[2], root_dir=sys.argv[1] + '/pythonforandroid',
    storage_dir=sys.argv[1],
)
result = {}
for name in ('ifaddr', 'zeroconf', 'sqlalchemy'):
    recipe = Recipe.get_recipe(name, ctx)
    assert Path(recipe.get_recipe_dir()).parent == Path(sys.argv[2])
    if name == 'ifaddr':
        assert not recipe.patches and 'ifaddrs' not in recipe.depends
        assert recipe.min_ndk_api_support == 24
        recipe.apply_patches(SimpleNamespace(arch='arm64-v8a'))
    else:
        assert isinstance(recipe, PyProjectRecipe)
    result[name] = recipe.version
print(json.dumps(result))
"""
    result = subprocess.run(
        [str(host), "-c", probe, str(p4a), str(android.ROOT / "platforms/android/recipes")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    versions = json.loads(result.stdout)
    assert versions == {name: android.android_profile()["runtime"][name] for name in versions}


def test_doctor_rejects_missing_patch_in_build_path(monkeypatch, tmp_path: Path, capsys) -> None:
    sdk = tmp_path / "sdk"
    ndk = sdk / "ndk" / android_setup.NDK_VERSION
    for relative in (
        "platform-tools/adb",
        "tools/bin/sdkmanager",
        "platforms/android-35/android.jar",
        "build-tools/35.0.0/aapt",
    ):
        target = sdk / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        target.chmod(0o755)
    ndk.mkdir(parents=True)
    (ndk / "source.properties").write_text(f"Pkg.Revision = {android_setup.NDK_VERSION}\n")
    wheels = [
        tmp_path / f"{name}-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl"
        for name in ("pyside6", "shiboken6")
    ]
    for wheel in wheels:
        wheel.touch()
    monkeypatch.setattr(android_setup, "environment", lambda: {"PATH": "/isolated/bin"})
    monkeypatch.setattr(android.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        android.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            stdout="",
            stderr='openjdk version "17.0.20"',
            returncode=0,
        ),
    )
    missing = {"patch"}

    def which(name, *, path):
        assert path == "/isolated/bin"
        return None if name in missing else f"{path}/{name}"

    monkeypatch.setattr(android.shutil, "which", which)
    assert not android.doctor(sdk, ndk, wheels)
    failures = [line for line in capsys.readouterr().out.splitlines() if line.startswith("MISSING")]
    assert failures == ["MISSING  Native build tool: patch"]
    missing.clear()
    assert android.doctor(sdk, ndk, wheels)
    assert "MISSING" not in capsys.readouterr().out
    monkeypatch.setattr(
        android.subprocess,
        "run",
        lambda command, **kw: SimpleNamespace(
            stdout="",
            stderr='openjdk version "17.0.20"',
            returncode=1 if "-MFindBin" in command else 0,
        ),
    )
    assert not android.doctor(sdk, ndk, wheels)
    failures = [line for line in capsys.readouterr().out.splitlines() if line.startswith("MISSING")]
    assert failures == ["MISSING  OpenSSL Perl module: FindBin"]


@pytest.mark.parametrize("arch", ["aarch64", "x86_64"])
def test_official_qt_android_wheel_names_are_accepted(arch: str) -> None:
    manifest = json.loads((android.ROOT / "platforms/android/wheels.json").read_text())
    wheels = [Path(manifest[arch][name]["filename"]) for name in ("pyside6", "shiboken6")]
    android.validate_wheels(wheels, arch)
    other = "x86_64" if arch == "aarch64" else "aarch64"
    with pytest.raises(ValueError, match="architecture"):
        android.validate_wheels(wheels, other)
    with pytest.raises(ValueError, match="first"):
        android.validate_wheels(list(reversed(wheels)), arch)


def test_mismatched_python_and_qt_versions_are_rejected() -> None:
    wheels = [
        Path("pyside6-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl"),
        Path("shiboken6-6.12.0-6.12.0-cp311-cp311-android_aarch64.whl"),
    ]
    with pytest.raises(ValueError, match="ABI"):
        android.validate_wheels(wheels, "aarch64")


def test_download_rejects_corruption_and_removes_partial_file(monkeypatch, tmp_path: Path) -> None:
    from io import BytesIO

    target = tmp_path / "wheel.whl"
    monkeypatch.setattr(android_setup, "urlopen", lambda *a, **kw: BytesIO(b"bad download"))
    with pytest.raises(ValueError, match="SHA-256"):
        android_setup.download("https://download.qt.io/wheel.whl", target, "0" * 64)
    assert not target.exists()
    assert not target.with_suffix(".whl.part").exists()
    target.write_bytes(b"cached wheel")
    android_setup.download(
        "https://download.qt.io/wheel.whl", target, hashlib.sha256(target.read_bytes()).hexdigest()
    )
    assert target.read_bytes() == b"cached wheel"


def mock_apk(root: Path, abi: str, *, omit: str = "") -> Path:
    folder = root / "bin"
    folder.mkdir(parents=True)
    apk = folder / "app-debug.apk"
    arch = "aarch64" if abi == "arm64-v8a" else "x86_64"
    native = set(android.qt_native_members(root, arch)) | {
        "libshiboken6.abi3.so",
        "libc++_shared.so",
    }
    with zipfile.ZipFile(apk, "w") as output:
        for name in (
            "AndroidManifest.xml",
            "classes.dex",
            *(f"lib/{abi}/{n}" for n in native if n != omit),
        ):
            output.writestr(name, "unit fixture, not an executable")
    return apk


@pytest.mark.parametrize(
    "missing",
    ["QtSvg.abi3.so", "QtQuickControls2.abi3.so", "libplugins_imageformats_qsvg_x86_64.so"],
)
def test_missing_qt_library_never_replaces_published_apk(
    monkeypatch, tmp_path: Path, missing: str
) -> None:
    monkeypatch.setattr(android, "ROOT", tmp_path)
    target = tmp_path / "dist/android/Epubify-0.1.0-x86_64-debug.apk"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous APK")
    mock_apk(tmp_path / "stage", "x86_64", omit=missing)
    with pytest.raises(ValueError, match="missing required Qt native libraries"):
        android.publish_apk(tmp_path / "stage", tmp_path / "sdk", "x86_64")
    assert target.read_bytes() == b"previous APK"


def test_wrong_abi_and_failed_signature_never_publish_an_apk(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(android, "ROOT", tmp_path)
    mock_apk(tmp_path / "stage", "x86_64")
    with pytest.raises(ValueError, match="ABI"):
        android.publish_apk(tmp_path / "stage", tmp_path / "sdk", "aarch64")
    assert not (tmp_path / "dist").exists()

    def external_tool(command, **kwargs):
        if "apksigner" in command[0]:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout="package: name='org.epubify.epubify'\nlaunchable-activity:")

    monkeypatch.setattr(android.subprocess, "run", external_tool)
    with pytest.raises(subprocess.CalledProcessError):
        android.publish_apk(tmp_path / "stage", tmp_path / "sdk", "x86_64")
    assert not (tmp_path / "dist").exists()


def test_verified_artifact_report_does_not_claim_runtime_validation(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(android, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    original = mock_apk(tmp_path / "stage", "arm64-v8a")
    monkeypatch.setattr(
        android.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            stdout="package: name='org.epubify.epubify'\nlaunchable-activity:"
        ),
    )
    target = android.publish_apk(tmp_path / "stage", tmp_path / "sdk", "aarch64")
    assert target.read_bytes() == original.read_bytes()
    report = json.loads(target.with_suffix(".json").read_text())
    assert report["runtime_verified"] is False
    assert report["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()


@pytest.mark.parametrize("initializer_fails", [False, True])
def test_build_keeps_native_requirements_and_preserves_cache_after_failure(
    monkeypatch, tmp_path: Path, initializer_fails: bool
) -> None:
    project = android.ROOT
    monkeypatch.setattr(android, "ROOT", tmp_path)
    source = tmp_path / "src/epub_reader"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("")
    for name in ("pyproject.toml", "THIRD_PARTY_NOTICES.md"):
        (tmp_path / name).write_bytes((project / name).read_bytes())
    shutil.copytree(project / "platforms/android", tmp_path / "platforms/android")
    stage = tmp_path / "build/android/aarch64"
    cache = stage / ".buildozer/cache-marker"
    cache.parent.mkdir(parents=True)
    cache.write_text("Preserve expensive cross-compiled dependencies")
    installer = stage / ".buildozer/android/platform/build-arm64-v8a/build/venv"
    installer.mkdir(parents=True)
    (installer / "pyvenv.cfg").write_text("version = 3.14.2\n")
    monkeypatch.setattr(android, "doctor", lambda *a, **kw: True)
    commands = []

    def initialize(command, *, cwd, **kwargs):
        commands.append(command)
        assert "--no-install" in command
        assert not (cwd / ".buildozer").exists()  # Qt --init deletes this directory.
        if initializer_fails:
            raise subprocess.CalledProcessError(1, command)
        (cwd / "buildozer.spec").write_text("[app]\n[buildozer]\n")
        qt_recipe = cwd / "deployment/recipes/PySide6/__init__.py"
        qt_recipe.parent.mkdir(parents=True)
        qt_recipe.write_text("# Generated by Qt; must survive overlay installation\n")

    monkeypatch.setattr(android.subprocess, "run", initialize)
    native_cache = stage / (
        ".buildozer/android/platform/build-arm64-v8a/build/libs_collections/epubify/arm64-v8a"
    )
    native_cache.mkdir(parents=True)

    def compile_android(*args, **kwargs):
        # Refresh must happen before Buildozer can reuse the cached recipe.
        assert (native_cache / "QtSvg.abi3.so").is_file()
        assert (native_cache / "QtQuickControls2.abi3.so").is_file()
        return 1

    monkeypatch.setattr(android.subprocess, "call", compile_android)
    args = argparse.Namespace(
        pyside_wheel=tmp_path / "pyside6-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl",
        shiboken_wheel=tmp_path / "shiboken6-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl",
        arch="aarch64",
        sdk=tmp_path / "sdk",
        ndk=tmp_path / "ndk",
    )
    mock_qt_wheel(stage, args.pyside_wheel, args.arch)
    manager = args.sdk / "cmdline-tools/latest/bin/sdkmanager"
    manager.parent.mkdir(parents=True)
    manager.write_text("#!/bin/sh\nexit 0\n")
    manager.chmod(0o755)
    if initializer_fails:
        with pytest.raises(subprocess.CalledProcessError):
            android.build(args)
        assert cache.exists()
        assert installer.exists()
        assert not (stage.parent / ".aarch64-buildozer-cache").exists()
        return
    assert android.build(args) == 1
    config = configparser.ConfigParser()
    config.read(stage / "buildozer.spec")
    requirements = config["app"]["requirements"]
    for dependency in (
        "PySide6",
        "shiboken6",
        "pyjnius",
        "cryptography==",
        "sqlalchemy==",
        "typing-extensions==",
    ):
        assert dependency in requirements
    assert config["app"]["android.archs"] == "arm64-v8a"
    assert config["app"]["android.api"] == "35"
    assert config["app"]["android.skip_update"] == "True"
    recipe_dir = Path(config["app"]["p4a.local_recipes"])
    assert (recipe_dir / "PySide6/__init__.py").read_text().startswith("# Generated by Qt")
    assert (recipe_dir / "ifaddr/__init__.py").read_bytes() == (
        project / "platforms/android/recipes/ifaddr/__init__.py"
    ).read_bytes()
    assert config["app"]["p4a.commit"] == android.android_profile()["toolchain"]["p4a_commit"]
    assert (stage / "android-runtime.toml").is_file()
    assert config["buildozer"]["bin_dir"] == str(stage / "bin")
    assert "ttf" in config["app"]["source.include_exts"]
    assert cache.exists()
    assert not installer.exists()
    assert (args.sdk / "tools/bin/sdkmanager").is_file()
    assert not (tmp_path / "dist").exists()
    assert commands


def test_existing_host_bootstraps_pip_before_installing_build_dependencies(
    monkeypatch, tmp_path: Path
) -> None:
    tools = tmp_path / "toolchain"
    python = tools / "host/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    (tools / "host/pyvenv.cfg").write_text("include-system-site-packages = false\n")
    marker = tools / "host/cache-marker"
    marker.write_text("keep existing environment")
    monkeypatch.setattr(android_setup, "TOOLS", tools)
    monkeypatch.setattr(android_setup, "android_wheels", lambda arch: [])
    monkeypatch.setattr(android_setup.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(android_setup, "prepare_sdk", lambda *a, **kw: tools / "sdk")
    commands = []
    monkeypatch.setattr(
        android_setup.subprocess, "run", lambda command, **kw: commands.append(command)
    )
    result = android_setup.prepare("aarch64", tmp_path / "sdk", accept_licenses=False)
    assert result[0] == python
    assert commands[0] == [str(python), "-m", "ensurepip", "--upgrade", "--default-pip"]
    assert commands[1] == [str(python), "-m", "pip", "--version"]
    assert commands[2][1:4] == ["pip", "install", "--python"]
    assert not any("venv" in command for command in commands)
    assert marker.exists()


def test_build_environment_excludes_credentials_and_uses_selected_toolchain(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("JIRA_API_TOKEN", "synthetic-do-not-forward")
    monkeypatch.setenv("UNRELATED_PASSWORD", "synthetic-password")
    monkeypatch.setenv("ANDROID_NDK_ROOT", "/old/ndk/30")
    monkeypatch.setenv("ANDROID_HOME", "/old/sdk")
    monkeypatch.setenv("VIRTUAL_ENV", "/desktop/venv")
    python = tmp_path / "host/bin/python"
    python.parent.mkdir(parents=True)
    (tmp_path / "host/pyvenv.cfg").touch()
    env = android_setup.environment(sdk=tmp_path / "sdk", ndk=tmp_path / "ndk", python=python)
    assert "JIRA_API_TOKEN" not in env and "UNRELATED_PASSWORD" not in env
    assert env["ANDROID_HOME"] == env["ANDROID_SDK_ROOT"] == str(tmp_path / "sdk")
    assert env["ANDROID_NDK_HOME"] == env["ANDROID_NDK_ROOT"] == str(tmp_path / "ndk")
    assert env["VIRTUAL_ENV"] == str(tmp_path / "host")
    assert str(python.parent) in env["PATH"]
    assert "HOME" in env


def test_environment_dump_redacts_credential_assignments() -> None:
    text = "#     JIRA_API_TOKEN = 'synthetic-private-value'\n"
    assert android.redact_log_line(text) == "#     JIRA_API_TOKEN = '[REDACTED]'\n"
    ordinary = "#     ANDROID_HOME = '/a/sdk'\n"
    assert android.redact_log_line(ordinary) == ordinary


@pytest.mark.parametrize("layout", ["cmdline-tools/latest", "cmdline-tools"])
def test_sdk_legacy_lookup_executes_modern_manager_idempotently(
    tmp_path: Path, layout: str
) -> None:
    modern = tmp_path / layout / "bin/sdkmanager"
    modern.parent.mkdir(parents=True)
    modern.write_text('#!/bin/sh\nprintf "sdk-fixture %s\\n" "$1"\n')
    modern.chmod(0o755)
    manager = android_setup.ensure_sdk_layout(tmp_path)
    assert manager == tmp_path / "tools/bin/sdkmanager"
    assert manager.resolve() == modern.resolve()
    result = subprocess.run([str(manager), "--version"], capture_output=True, text=True, check=True)
    assert result.stdout == "sdk-fixture --version\n"
    assert android_setup.ensure_sdk_layout(tmp_path) == manager


def test_sdk_legacy_tools_are_preserved_and_broken_alias_is_repaired(tmp_path: Path) -> None:
    sdk = tmp_path / "sdk"
    modern = sdk / "cmdline-tools/latest/bin/sdkmanager"
    modern.parent.mkdir(parents=True)
    modern.write_text("#!/bin/sh\nexit 0\n")
    modern.chmod(0o755)
    legacy = sdk / "tools"
    legacy.symlink_to("missing-old-tools", target_is_directory=True)
    assert android_setup.ensure_sdk_layout(sdk).resolve() == modern.resolve()
    legacy.unlink()
    legacy.mkdir()
    marker = legacy / "keep-existing-tools.txt"
    marker.write_text("preserve")
    assert android_setup.ensure_sdk_layout(sdk).resolve() == modern.resolve()
    assert marker.read_text() == "preserve"


def test_sdk_missing_manager_and_conflicting_legacy_file_fail_without_overwriting(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="No executable sdkmanager"):
        android_setup.ensure_sdk_layout(tmp_path)
    modern = tmp_path / "cmdline-tools/latest/bin/sdkmanager"
    modern.parent.mkdir(parents=True)
    modern.write_text("#!/bin/sh\nexit 0\n")
    modern.chmod(0o755)
    conflict = tmp_path / "tools"
    conflict.write_text("preserve")
    with pytest.raises(RuntimeError, match="Refusing to replace"):
        android_setup.ensure_sdk_layout(tmp_path)
    assert conflict.read_text() == "preserve"
