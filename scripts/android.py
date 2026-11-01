"""Experimental Qt Android build and adb helpers. No host wheels enter the APK."""

import argparse
import configparser
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

if __package__:
    from . import android_setup
else:
    import android_setup

ROOT = Path(__file__).resolve().parents[1]
QT_MODULES = frozenset(
    {"Core", "Gui", "Network", "OpenGL", "Qml", "Quick", "QuickControls2", "Svg"}
)
QT_PLUGINS = ("platforms/qtforandroid", "imageformats/qsvg", "iconengines/qsvgicon")
NATIVE_BUILD_TOOLS = (
    "make",
    "gcc",
    "g++",
    "autoconf",
    "automake",
    "libtoolize",
    "pkg-config",
    "patch",
    "git",
    "cmake",
    "ninja",
    "zip",
    "unzip",
    "perl",
    "cargo",
    "rustc",
    "rustup",
)
OPENSSL_PERL_MODULES = (
    "FindBin",
    "File::Compare",
    "File::Copy",
    "File::Path",
    "File::Spec",
    "IPC::Cmd",
    "Data::Dumper",
    "Getopt::Long",
    "Getopt::Std",
    "Pod::Usage",
    "Text::ParseWords",
    "Time::HiRes",
)


def android_profile() -> dict:
    """Android build inputs must not silently follow desktop dependency updates."""
    profile = tomllib.loads((ROOT / "platforms/android/runtime.toml").read_text())
    runtime = profile["runtime"]
    required = {
        "sqlalchemy",
        "defusedxml",
        "cryptography",
        "websockets",
        "zeroconf",
        "ifaddr",
        "cffi",
        "pycparser",
        "typing-extensions",
    }
    if set(runtime) != required or any(
        not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+)+", version)
        for version in runtime.values()
    ):
        raise ValueError("Android runtime must contain exact pins for the complete dependency set.")
    for name, version in {"ifaddr": "0.2.0", "zeroconf": "0.152.1", "sqlalchemy": "2.1.6"}.items():
        if runtime[name] != version:
            raise ValueError(f"Review the local {name} recipe before changing its Android version.")
    toolchain = profile["toolchain"]
    if toolchain["qt"] != "6.12.0" or toolchain["min_api"] != 28:
        raise ValueError("Review Android wheels and recipes before changing Qt or minimum API.")
    return profile


def prepare_qt_config(stage: Path) -> Path:
    """SVG icons need explicit Android image/icon plugins, not just QtSvg imports."""
    target = stage / "pysidedeploy.spec"
    config = configparser.ConfigParser(interpolation=None)
    if target.exists():
        config.read(target)
    else:
        import PySide6

        template = Path(PySide6.__file__).parent / "scripts/deploy_lib/default.spec"
        config.read(template)
    plugins = set(filter(None, config.get("android", "plugins", fallback="").split(",")))
    plugins.update(("platforms_qtforandroid", "imageformats_qsvg", "iconengines_qsvgicon"))
    if not config.has_section("android"):
        config.add_section("android")
    config["android"]["plugins"] = ",".join(sorted(plugins))
    with target.open("w") as output:
        config.write(output)
    return target


def qt_native_members(stage: Path, arch: str) -> dict[str, str]:
    """Map native filenames to entries in the Android PySide wheel."""
    abi = {"aarch64": "arm64-v8a", "x86_64": "x86_64"}[arch]
    config = configparser.ConfigParser(interpolation=None)
    config.read(stage / "pysidedeploy.spec")
    modules = QT_MODULES | set(filter(None, config.get("qt", "modules", fallback="").split(",")))
    if any(not re.fullmatch(r"[A-Za-z0-9]+", module) for module in modules):
        raise ValueError("Invalid Qt module name in deployment configuration.")
    members = {}
    for module in sorted(modules):
        members[f"Qt{module}.abi3.so"] = f"PySide6/Qt{module}.abi3.so"
        library = f"libQt6{module}_{abi}.so"
        members[library] = f"PySide6/Qt/lib/{library}"
    for plugin in QT_PLUGINS:
        directory, name = plugin.split("/")
        library = f"libplugins_{directory}_{name}_{abi}.so"
        members[library] = f"PySide6/Qt/plugins/{directory}/{library}"
    for library in ("libpyside6.abi3.so", "libpyside6qml.abi3.so"):
        members[library] = f"PySide6/{library}"
    return members


def refresh_qt_native_cache(stage: Path, wheel: Path, arch: str) -> None:
    """Refresh Qt runtime files even when p4a reuses an existing distribution.

    PythonRecipe.should_build only checks that PySide6 is installed. Changing
    Qt modules/plugins does not invalidate either that recipe or the distribution.
    Keep both native-library caches current without rebuilding unrelated recipes.
    """
    abi = {"aarch64": "arm64-v8a", "x86_64": "x86_64"}[arch]
    base = stage / f".buildozer/android/platform/build-{abi}"
    destinations = [
        base / f"build/libs_collections/epubify/{abi}",
        base / f"dists/epubify/libs/{abi}",
    ]
    members = qt_native_members(stage, arch)
    with zipfile.ZipFile(wheel) as archive:
        missing = set(members.values()) - set(archive.namelist())
        if missing:
            raise ValueError(
                f"Android Qt wheel is missing required native files: {sorted(missing)}"
            )
        for destination in destinations:
            if not destination.exists():
                continue  # A fresh build populates these via Qt's generated recipe.
            if not destination.resolve().is_relative_to(stage.resolve()):
                raise ValueError(f"Qt native cache escapes the staging directory: {destination}")
            for name, member in members.items():
                temporary = destination / f"{name}.part"
                with archive.open(member) as source, temporary.open("wb") as output:
                    shutil.copyfileobj(source, output)
                temporary.replace(destination / name)
            print(f"Refreshed {len(members)} Android Qt libraries in {destination}", flush=True)


def reset_p4a_installer(stage: Path, arch: str) -> None:
    """Discard only p4a's disposable pip environment before each build attempt.

    Qt-pinned p4a recreates this venv without --clear. Its patched ensurepip can
    overlay bundled pip 25.3 onto upgraded pip 26, leaving incompatible modules.
    Compiled recipes, target site-packages, downloads and the deploy host stay intact.
    """
    abi = {"aarch64": "arm64-v8a", "x86_64": "x86_64"}[arch]
    installer = stage / f".buildozer/android/platform/build-{abi}/build/venv"
    if not installer.exists() and not installer.is_symlink():
        return
    if (
        installer.is_symlink()
        or not installer.resolve().is_relative_to(stage.resolve())
        or not (installer / "pyvenv.cfg").is_file()
    ):
        raise RuntimeError(f"Refusing to remove unexpected p4a installer path: {installer}")
    shutil.rmtree(installer)
    print(
        "Reset disposable p4a pip environment; compiled Android dependencies retained.", flush=True
    )


def validate_wheels(wheels: list[Path], arch: str) -> None:
    """Qt wheels use android_aarch64; Gradle calls that ABI arm64-v8a."""
    if len(wheels) != 2:
        raise ValueError("Provide both the PySide6 and shiboken6 Android wheels.")
    parts = [wheel.name.removesuffix(".whl").split("-") for wheel in wheels]
    if any(len(part) not in (5, 6) for part in parts):
        raise ValueError("Invalid Android wheel filename.")
    if [part[0].lower() for part in parts] != ["pyside6", "shiboken6"]:
        raise ValueError("Provide the PySide6 wheel first and shiboken6 second.")
    if any(part[1] != "6.12.0" for part in parts) or parts[0][1:] != parts[1][1:]:
        raise ValueError("Qt wheel versions, build tags and Python ABI must match Qt 6.12.0.")
    if parts[0][-1] != f"android_{arch}":
        raise ValueError("The Android wheel architecture must match --arch.")


def publish_apk(stage: Path, sdk: Path, arch: str) -> Path:
    candidates = list((stage / "bin").glob("*.apk"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one newly built debug APK in {stage / 'bin'}: {candidates}")
    apk = candidates[0]
    abi = "arm64-v8a" if arch == "aarch64" else "x86_64"
    with zipfile.ZipFile(apk) as package:
        names = package.namelist()
        if "AndroidManifest.xml" not in names or "classes.dex" not in names:
            raise ValueError("The output is not an Android application package.")
        native = [name for name in names if name.startswith("lib/") and name.endswith(".so")]
        if not native or any(not name.startswith(f"lib/{abi}/") for name in native):
            raise ValueError("The APK contains a missing or incorrect native ABI.")
        required = set(qt_native_members(stage, arch)) | {
            "libshiboken6.abi3.so",
            "libc++_shared.so",
        }
        missing = sorted(name for name in required if f"lib/{abi}/{name}" not in names)
        if missing:
            raise ValueError(f"APK is missing required Qt native libraries: {', '.join(missing)}")
    tools = sdk / "build-tools/35.0.0"
    badging = subprocess.run(
        [str(tools / "aapt"), "dump", "badging", str(apk)],
        capture_output=True,
        text=True,
        check=True,
        env=android_setup.environment(),
    ).stdout
    if "name='org.epubify.epubify'" not in badging or "launchable-activity:" not in badging:
        raise ValueError("The APK package ID or launcher is incorrect.")
    subprocess.run(
        [str(tools / "apksigner"), "verify", "--verbose", str(apk)],
        check=True,
        env=android_setup.environment(),
    )
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    folder = ROOT / "dist/android"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"Epubify-{version}-{abi}-debug.apk"
    temporary = target.with_suffix(".apk.part")
    shutil.copy2(apk, temporary)
    temporary.replace(target)
    report = {
        "status": "built",
        "runtime_verified": False,
        "artifact": str(target),
        "abi": abi,
        "sha256": android_setup.sha256(target),
        "size": target.stat().st_size,
        "built_at": datetime.now(UTC).isoformat(),
        "checks": [
            "APK structure",
            "native ABI",
            "Qt native libraries",
            "package ID",
            "launcher",
            "signature",
        ],
    }
    target.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"APK built and structurally verified: {target}", flush=True)
    print("Launching and reading on a device remains a separate validation step.", flush=True)
    return target


def redact_log_line(line: str) -> str:
    match = re.match(r"^(\s*#?\s*)([A-Z][A-Z0-9_]*)\s*=", line)
    if match and any(
        part in match[2]
        for part in (
            "TOKEN",
            "SECRET",
            "PASSWORD",
            "CREDENTIAL",
            "API_KEY",
            "ACCESS_KEY",
            "PRIVATE_KEY",
            "AUTHORIZATION",
            "COOKIE",
        )
    ):
        return f"{match[1]}{match[2]} = '[REDACTED]'\n"
    return line


def logged(command: list[str], target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        target.open("w") as log,
        subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=android_setup.environment(python=Path(command[0])),
            cwd=ROOT,
        ) as process,
    ):
        assert process.stdout is not None
        for line in process.stdout:
            line = redact_log_line(line)
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        result = process.wait()
    print(f"Log: {target}", flush=True)
    return result


def apk(args: argparse.Namespace) -> int:
    logs = ROOT / "build/android/logs"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "setup",
        "--arch",
        args.arch,
        "--sdk",
        str(args.sdk),
    ]
    if args.accept_licenses:
        command.append("--accept-licenses")
    result = logged(command, logs / f"{args.arch}-setup.log")
    if result:
        return result
    state = json.loads((android_setup.TOOLS / f"{args.arch}.json").read_text())
    return logged(
        [
            state["python"],
            str(Path(__file__).resolve()),
            "build",
            "--arch",
            args.arch,
            "--sdk",
            state["sdk"],
            "--ndk",
            state["ndk"],
            "--pyside-wheel",
            state["wheels"][0],
            "--shiboken-wheel",
            state["wheels"][1],
        ],
        logs / f"{args.arch}-build.log",
    )


def sdk_path() -> Path:
    return Path(
        os.environ.get("ANDROID_SDK_ROOT", os.environ.get("ANDROID_HOME", "~/Android/Sdk"))
    ).expanduser()


def doctor(sdk: Path, ndk: Path, wheels: list[Path], arch: str = "aarch64") -> bool:
    env = android_setup.environment()
    perl = shutil.which("perl", path=env["PATH"])
    perl_checks = {
        f"OpenSSL Perl module: {module}": perl is not None
        and subprocess.run(
            [perl, f"-M{module}", "-e", "1"],
            capture_output=True,
            text=True,
            env=env,
        ).returncode
        == 0
        for module in OPENSSL_PERL_MODULES
    }
    java = shutil.which("java", path=env["PATH"])
    java_version = (
        subprocess.run([java, "-version"], capture_output=True, text=True, env=env)
        if java
        else None
    )
    valid_wheels = False
    if all(wheel.is_file() for wheel in wheels):
        try:
            validate_wheels(wheels, arch)
            valid_wheels = True
        except ValueError:
            pass
    checks = {
        "Linux/macOS build host": sys.platform in ("linux", "darwin"),
        "JDK 17": java_version is not None
        and 'version "17.' in java_version.stderr + java_version.stdout,
        **{
            f"Native build tool: {name}": shutil.which(name, path=env["PATH"]) is not None
            for name in NATIVE_BUILD_TOOLS
        },
        **perl_checks,
        "adb": (sdk / "platform-tools/adb").is_file(),
        "Buildozer sdkmanager (tools/bin/sdkmanager)": (sdk / "tools/bin/sdkmanager").is_file()
        and os.access(sdk / "tools/bin/sdkmanager", os.X_OK),
        "Android API 35 / Build Tools 35.0.0": (sdk / "platforms/android-35/android.jar").is_file()
        and (sdk / "build-tools/35.0.0/aapt").is_file(),
        "Android NDK r28c": (ndk / "source.properties").is_file()
        and "28.2.13676358" in (ndk / "source.properties").read_text(),
        "PySide6 deploy prerequisites": all(
            importlib.util.find_spec(name)
            for name in ("pip", "jinja2", "pkginfo", "tqdm", "buildozer")
        ),
        "Android Qt 6.12.0 wheels": valid_wheels,
    }
    for label, passed in checks.items():
        print(f"{'OK' if passed else 'MISSING'}  {label}")
    print(
        "Target Python/ABI must match both Qt wheels; desktop CPython 3.13 wheels cannot be reused."
    )
    return all(checks.values())


def build(args: argparse.Namespace) -> int:
    profile = android_profile()
    android_setup.ensure_sdk_layout(args.sdk)
    wheels = [wheel.resolve() for wheel in (args.pyside_wheel, args.shiboken_wheel) if wheel]
    if not doctor(args.sdk, args.ndk, wheels, args.arch):
        return 1
    validate_wheels(wheels, args.arch)
    stage = ROOT / "build/android" / args.arch
    stage.mkdir(parents=True, exist_ok=True)
    if (stage / "epub_reader").exists():
        shutil.rmtree(stage / "epub_reader")
    shutil.copytree(
        ROOT / "src/epub_reader",
        stage / "epub_reader",
        ignore=shutil.ignore_patterns("__pycache__"),
        dirs_exist_ok=True,
    )
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", stage / "THIRD_PARTY_NOTICES.md")
    (stage / "main.py").write_text(
        "from epub_reader.bootstrap import main\nraise SystemExit(main())\n"
    )
    deploy = Path(sys.executable).parent / "pyside6-android-deploy"
    qt_config = prepare_qt_config(stage)
    # Qt generates its own ABI-specific PySide/shiboken recipes and pins p4a.
    cache = stage / ".buildozer"
    saved_cache = stage.parent / f".{args.arch}-buildozer-cache"
    if saved_cache.exists():
        if cache.exists():
            raise RuntimeError(f"Both {cache} and {saved_cache} exist; preserve both for recovery.")
        saved_cache.rename(cache)
    if cache.exists():
        cache.rename(saved_cache)
    try:
        subprocess.run(
            [
                str(deploy),
                "--config-file",
                str(qt_config),
                "--extra-modules",
                "Svg,QuickControls2",
                "--init",
                "--name",
                "Epubify",
                "--wheel-pyside",
                str(wheels[0]),
                "--wheel-shiboken",
                str(wheels[1]),
                "--sdk-path",
                str(args.sdk),
                "--ndk-path",
                str(args.ndk),
                "--keep-deployment-files",
                "--force",
                "--no-install",
            ],
            cwd=stage,
            check=True,
            env=android_setup.environment(sdk=args.sdk, ndk=args.ndk, python=Path(sys.executable)),
        )
    finally:
        # Qt 6.12 cleans .buildozer even for --init. Keep the cache outside
        # its project while it regenerates recipes, including on failure.
        if saved_cache.exists():
            if cache.exists():
                raise RuntimeError(
                    f"New cache appeared at {cache}; saved cache is at {saved_cache}."
                )
            saved_cache.rename(cache)
    spec = stage / "buildozer.spec"
    config = configparser.ConfigParser(interpolation=None)
    config.read(spec)
    recipes = stage / "deployment/recipes"
    shutil.copytree(
        ROOT / "platforms/android/recipes",
        recipes,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy2(ROOT / "platforms/android/runtime.toml", stage / "android-runtime.toml")
    # Registers Epubify as a handler for .epub files in the system "Open with" chooser.
    shutil.copy2(ROOT / "platforms/android/intent_filters.xml", stage / "intent_filters.xml")
    shutil.copytree(ROOT / "platforms/android/java", stage / "java", dirs_exist_ok=True)
    requirements = [f"{name}=={version}" for name, version in profile["runtime"].items()]
    config["app"].update(
        {
            "package.name": "epubify",
            "package.domain": "org.epubify",
            "version": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
            "requirements": ",".join(["python3", "shiboken6", "PySide6", "pyjnius", *requirements]),
            "p4a.local_recipes": str(recipes),
            "p4a.commit": profile["toolchain"]["p4a_commit"],
            "source.include_exts": "py,qml,qm,json,png,svg,ttf,txt,md",
            "source.include_patterns": "epub_reader/resources/licenses/*/*,THIRD_PARTY_NOTICES.md",
            "android.permissions": (
                "INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE"
            ),
            "android.archs": "arm64-v8a" if args.arch == "aarch64" else "x86_64",
            "android.manifest.intent_filters": "intent_filters.xml",
            "android.add_src": "java",
            "android.activity_class_name": "org.epubify.MainActivity",
            "android.entrypoint": "org.epubify.MainActivity",
            "android.api": str(profile["toolchain"]["target_api"]),
            "android.minapi": str(profile["toolchain"]["min_api"]),
            "android.ndk_api": str(profile["toolchain"]["min_api"]),
            "android.skip_update": "True",
            "icon.filename": "epub_reader/resources/icons/app_icon.png",
            "source.exclude_dirs": ".git,.venv,__pycache__",
        }
    )
    # Qt's initializer can select the project root as bin_dir. Make the
    # artifact location explicit so validation always reads this build's APK.
    config["buildozer"]["bin_dir"] = str(stage / "bin")
    with spec.open("w") as output:
        config.write(output)
    # Invoke buildozer directly: running the Qt initializer again would reset
    # requirements/permissions. Native dependencies must cross-compile via p4a.
    refresh_qt_native_cache(stage, wheels[0], args.arch)
    reset_p4a_installer(stage, args.arch)
    for previous in (stage / "bin").glob("*.apk"):
        previous.unlink()
    result = subprocess.call(
        [sys.executable, "-m", "buildozer", "android", "debug"],
        cwd=stage,
        env=android_setup.environment(sdk=args.sdk, ndk=args.ndk, python=Path(sys.executable)),
    )
    if result == 0:
        publish_apk(stage, args.sdk, args.arch)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("doctor", "setup", "apk", "build", "devices", "emulator", "install")
    )
    parser.add_argument("--sdk", type=Path, default=sdk_path())
    parser.add_argument("--ndk", type=Path)
    parser.add_argument("--arch", choices=("aarch64", "x86_64"), default="aarch64")
    parser.add_argument(
        "--accept-licenses", action="store_true", help="Accept Android SDK licenses during setup"
    )
    parser.add_argument("--pyside-wheel", type=Path)
    parser.add_argument("--shiboken-wheel", type=Path)
    parser.add_argument("--avd", help="Existing Android Studio virtual device name")
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--serial", help="adb device serial; required for install")
    args = parser.parse_args()
    if args.action == "apk":
        return apk(args)
    if args.action == "setup":
        python, sdk, wheels = android_setup.prepare(
            args.arch,
            args.sdk,
            accept_licenses=args.accept_licenses,
        )
        state = {
            "python": str(python),
            "sdk": str(sdk),
            "ndk": str(sdk / "ndk" / android_setup.NDK_VERSION),
            "wheels": [str(wheel) for wheel in wheels],
        }
        (android_setup.TOOLS / f"{args.arch}.json").write_text(json.dumps(state, indent=2) + "\n")
        return 0
    args.ndk = args.ndk or args.sdk / "ndk/28.2.13676358"
    adb = str(args.sdk / "platform-tools/adb")
    if args.action == "doctor":
        return (
            0
            if doctor(
                args.sdk,
                args.ndk,
                [p for p in (args.pyside_wheel, args.shiboken_wheel) if p],
                args.arch,
            )
            else 1
        )
    if args.action == "devices":
        return subprocess.call([adb, "devices", "-l"])
    if args.action == "emulator":
        emulator = str(args.sdk / "emulator/emulator")
        if not args.avd:
            return subprocess.call([emulator, "-list-avds"])
        return subprocess.call([emulator, "-avd", args.avd, "-no-snapshot-save"])
    if args.action == "install":
        if not args.apk or not args.serial:
            parser.error("install requires --apk and --serial")
        return subprocess.call([adb, "-s", args.serial, "install", "-r", str(args.apk)])
    return build(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Android build failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
