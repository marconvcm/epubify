# Mobile deployment status

Debug Android APKs have been generated and launched in the x86_64 emulator, where
the file picker import and system bar colors were checked. The captured Android screen exposed desktop layout clipping;
the responsive layout and page-stack animation are now validated in desktop
phone-sized previews and still need a new APK/device check. No AAB or iOS app
has been verified. Document-provider import and real-device permission flows
remain release gates. Desktop functionality does not establish mobile compatibility.

## Android

### Iterate on the phone layout without rebuilding

The running Probe_35 emulator reports 1080×2400 pixels at density 420, approximately
411×914 logical pixels. Run the same desktop QML and native reader at that size:

```sh
uv run epub-reader --mobile-preview
```

Use `--data-dir build/mobile-preview/data` for a separate preview library, or omit
it to use your desktop library. Resize the window to check landscape/tablet layouts.
For a headless capture of an empty library:

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software uv run epub-reader \
  --mobile-preview --data-dir build/mobile-preview/data \
  --smoke-test --diagnostics-dir build/mobile-preview/captures
```

Below 720 logical pixels the library uses an overlay navigation drawer and a
compact grid. The reader uses an overlay contents panel, compact toolbar, larger
touch controls, swipe navigation and scrollable settings. Higher-numbered pages
sit on top of earlier pages: advancing slides the next sheet in from the right;
going backwards slides the top sheet out to the right, revealing the stationary
earlier page underneath.
QML drives the animation of two native page images; reduced motion skips it.
Font/theme changes do not trigger page-turn animations.

The Basic Qt Quick Controls style keeps custom palettes/backgrounds consistent
across platforms. Android deployment explicitly includes QtSvg and the SVG image
and icon plugins. Desktop preview cannot validate Android system bars, keyboard,
file providers or APK plugin loading; check those on the next device build.
Qt ApplicationWindow retains its automatic safe-area padding.

When Qt modules/plugins change, p4a may reuse an older distribution because its
PySide recipe only checks whether the Python package is already installed. This
previously produced a loader entry for `QtSvg.abi3.so` without that file in the
APK. Before every build, the script refreshes selected Qt bindings, Qt libraries
and SVG/platform plugins in both existing native-library caches directly from
the matching Android wheel. Other compiled dependencies are preserved. Fresh
builds use Qt's generated recipes. Publication rejects APKs missing these files,
including `QtQuickControls2.abi3.so`; signing alone cannot detect this failure.

Layout/gesture/transition checks: `uv run pytest tests/integration/test_mobile_layout.py -q`.
These include 320×640, 411×914, 480×800 and 914×411 viewports.

### Android system integration

The Qt/p4a bootstrap does not forward several activity callbacks to Qt, and `pyjnius`
cannot be imported at runtime in this bootstrap (`WebView_AndroidGetJNIEnv` is
unresolved). Android-only behavior therefore lives in Java and talks to Python
through small files in the app's private directory (`$ANDROID_PRIVATE`).

| Piece | Location | Role |
| --- | --- | --- |
| `MainActivity` | `platforms/android/java/org/epubify/MainActivity.java` | Launcher activity (extends p4a's `PythonActivity`). Applies system bar colors and records incoming documents. |
| `EpubifyBridge` | `platforms/android/java/org/qtproject/qt/android/EpubifyBridge.java` | Lives in Qt's package to reach package-private `QtNative.onActivityResult`. |
| `intent_filters.xml` | `platforms/android/intent_filters.xml` | Registers Epubify in the system "Open with" chooser for EPUB files. |
| `platforms/android.py` | `src/epub_reader/platforms/android.py` | Python side: reads the handoff files and copies `content://` documents. |

`scripts/android.py` copies the Java sources and intent filters into the stage
directory and sets `android.add_src`, `android.entrypoint`,
`android.activity_class_name` and `android.manifest.intent_filters` for Buildozer.

**File picker results.** `PythonActivity.onActivityResult` and `onNewIntent` return
without calling `QtActivity`, so Qt's `FileDialog` never received its result and
imports silently did nothing. `MainActivity` overrides both and forwards them to Qt
through `EpubifyBridge`.

**`content://` documents.** The Android picker returns content URIs, which are not
local files. `ImportRequest` carries the URI; the import job copies it to a
temporary `.epub` with `QFile` (Qt resolves it through `ContentResolver`), imports
the copy and deletes it. Local `file://` URLs still import directly.

**Open with / share.** `MainActivity` handles `ACTION_VIEW` and `ACTION_SEND`
intents (`application/epub+zip`, or `application/octet-stream` named `*.epub`) at
launch and in `onNewIntent`. It writes the URI to `open-intent.txt`; a 700 ms
`QTimer` in `bootstrap.connect_android` consumes the file and starts an import.
Handoff files are written atomically (temp file plus rename).

**System bars.** After each theme change Python writes `system-bars.txt`
(`#RRGGBB light|dark`). `MainActivity` polls the file's timestamp every 400 ms on
the UI thread and sets the status/navigation bar colors, the window background
(visible behind transparent bars under Android 15 edge-to-edge enforcement) and
the light/dark icon appearance.

Manual checks after a build: pick a book with the "+" button, open an `.epub`
from a file manager via "Open with", switch themes and confirm both bars follow
the palette. `adb shell am start -a android.intent.action.VIEW -d file://...`
cannot substitute for a real `content://` grant and fails without storage
permission.

Known gaps: `platforms/network.py` still imports `jnius` for the Wi-Fi multicast
lock and will fail on devices until it uses the same Java bridge; imports requested
while another import is running are dropped; arm64 builds are compiled but have
only been run on an x86_64 emulator.

### Independent Android dependency profile

`platforms/android/runtime.toml` pins Android runtime dependencies and the Qt-pinned
p4a revision independently of the desktop `uv.lock`. Updating desktop packages
does not update the Android dependency set. The initial versions are retained;
they still require a completed cross-build and device acceptance. This manifest
does not lock every transitive build-backend dependency downloaded by p4a.

`platforms/android/recipes/` contains reviewed local overrides copied alongside
Qt's generated PySide6/shiboken6 recipes after each initialization:

- **ifaddr 0.2.0:** no legacy `getifaddrs.patch` or `libifaddrs` shim. Bionic
  [provides getifaddrs since API 24](https://android.googlesource.com/platform/bionic/+/master/libc/include/ifaddrs.h);
  the app requires API 28. The previous p4a recipe targets ifaddr 0.1.7 and its
  patch fails on 0.2.0. The source archive is checked with SHA-256.
- **zeroconf:** modern pyproject build with upstream's `SKIP_CYTHON=1` option.
- **SQLAlchemy:** pyproject build with `DISABLE_SQLALCHEMY_CEXT=1`. The application
  uses synchronous database access and does not need the asyncio greenlet extra.

The latter two switches disable optional accelerators; they preserve discovery
and persistence. Encryption still uses native cryptography/cffi. No sync feature
is removed. Keep local recipe versions and the Android manifest in agreement;
the build refuses unreviewed version changes for these recipes.

Run `uv run pytest tests/unit/test_android_build.py -q` before compiling. It checks
recipe staging without a desktop lockfile, cache preservation, pins and APK
publication failures. With the cached Android toolchain present, it also loads
the overrides through the real p4a recipe resolver. Each build saves its manifest
at `build/android/<arch>/android-runtime.toml` for diagnosis.

### Build the debug APK

From Linux/macOS with uv, JDK 17 and Android Studio command-line tools installed:

```sh
uv run python scripts/android.py apk --arch aarch64 --accept-licenses
```

For an x86_64 emulator, use `--arch x86_64`. This command downloads the pinned
Qt 6.12.0 Android wheels, verifies official SHA-256 hashes, creates a separate
CPython 3.11 deployment environment and installs API 35/Build Tools 35/NDK r28c
under `build/android/toolchain/`. It selects an installed JDK 17, including SDKMAN
installations, without changing the desktop environment. `--accept-licenses`
explicitly permits SDK license acceptance; omit it for the SDK installer's prompts.
The desktop app remains on Python 3.13 and p4a controls the target Python.

The setup bootstraps `pip` with `ensurepip` even when reusing an existing uv
environment: Buildozer/p4a invokes `python -m pip` directly. There is no need to
delete the toolchain to repair `No module named pip`. Build subprocesses receive
only toolchain/session environment variables, with SDK/NDK/virtualenv paths set
explicitly; unrelated account credentials are excluded. Credential assignments
in failure-log environment dumps are redacted. If a token appeared in an older
terminal log, revoke it before sharing that log.

There is a second, disposable Python environment inside p4a's
`build-<abi>/build/venv`, created by its compiled host Python 3.14. On repeated
builds, p4a's patched ensurepip can overlay bundled pip 25.3 on an upgraded pip
26 installation, leaving incompatible files (`BuildDependencyInstallError`
import failure). The script removes only this scratch venv before invoking
Buildozer so p4a creates it fresh. It preserves compiled recipes, target Python
packages, downloads, Gradle caches and the separate deployment host. Do not
delete `.buildozer` or reinstall Qt to recover from this error.

The SDK setup also exposes modern `cmdline-tools/latest` at the legacy
`tools/bin/sdkmanager` path hardcoded by Buildozer 1.6. It supports Qt's flat
`cmdline-tools/bin` layout, preserves existing legacy tools, and repairs stale
links. The build preflight repeats this check for already installed toolchains;
the doctor validates the actual executable path rather than only the SDK files.
Buildozer's automatic SDK update is disabled because setup already installs the
pinned API/build tools. Qt 6.12's initializer deletes `.buildozer` even with
`--init`, so the build script temporarily moves that cache outside Qt's project
and restores it in `finally`, including when initialization fails. Interrupted
initializations recover the saved cache on the next attempt; conflicting caches
are kept intact and reported rather than overwritten.

Native host tools are also required. On Ubuntu use `build-essential autoconf
automake libtool pkg-config patch git cmake ninja-build zip unzip perl libffi-dev libssl-dev
zlib1g-dev libncurses-dev`; on Fedora use `gcc gcc-c++ make autoconf automake
libtool pkgconf-pkg-config patch git cmake ninja-build zip unzip perl libffi-devel openssl-devel
zlib-devel ncurses-devel`. Install with the system package manager. The script
does not silently run sudo or change the system Java installation.
Rust's `cargo`, `rustc` and `rustup` must also be on PATH for cryptography; p4a
installs the Android Rust target as needed. OpenSSL needs Perl's core modules,
not just the interpreter. The doctor tests their imports, including `FindBin`
and `IPC::Cmd`. For an existing minimal Fedora installation missing only those
two modules, install `perl-FindBin perl-IPC-Cmd` with DNF before retrying.

If p4a reports `sh.CommandNotFound: patch`, install `patch` (`sudo dnf install -y
patch` on Fedora, or `sudo apt-get install -y patch` on Ubuntu) and rerun the same
APK command. Keep the build cache: this failure occurs while preparing sources,
before compilation. The doctor checks each native tool on the build environment's
PATH and reports the missing executable by name.

Successful ARM64 output is `dist/android/Epubify-0.1.0-arm64-v8a-debug.apk`, with
a JSON report recording its hash, ABI, required Qt libraries, package ID, launcher
and signature checks.
No output is published when those checks fail. These checks do not establish
that reading works on a device. Logs are `build/android/logs/<arch>-setup.log`
and `<arch>-build.log`; build caches survive retries. `setup` performs downloads
and toolchain installation separately, and `build` accepts explicit wheels as below.

The manually dispatched **Experimental Android APK** GitHub workflow installs
host dependencies and runs the same command on Ubuntu/JDK 17. APK/report upload
occurs only after a successful build; logs are retained on failure. The workflow
has not been executed or published from this workspace.

Local setup now includes SDK/NDK, Qt wheels and build prerequisites. The independent
profile has passed the previously failing ifaddr prebuild step in a real p4a run
and built libffi. That attempt stopped at OpenSSL configuration because Fedora's
Perl installation lacked `FindBin`; the log is
`build/android/logs/aarch64-profile-build.log`.
Subsequent user builds produced debug APKs with structure, ABI, launcher and
signature checks. The emulator launch is confirmed; this is not complete mobile
reading/synchronization acceptance.

Use an isolated deployment virtual environment: Qt's Android tool has build
prerequisites, including its own packaging version, separate from the app's
development environment. Follow the official [Qt Android deployment guide](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-android-deploy.html).
Obtain matching **Qt 6.12 Android** PySide6 and shiboken6 wheels for aarch64 or
x86_64. Desktop wheels cannot be substituted. The installed 6.12 deploy source
pins p4a and targets CPython **3.14.2**, while desktop development uses 3.13.
Match the actual wheel's Python/ABI and toolchain; do not force cp313 binaries
onto that target. NDK r28c is `28.2.13676358`, minimum API 28, initial target API 35.

```sh
uv run python scripts/android.py doctor
uv run python scripts/android.py emulator             # list existing AVDs
uv run python scripts/android.py emulator --avd Probe_35
uv run python scripts/android.py devices
uv run python scripts/android.py build --arch x86_64 \
  --pyside-wheel /path/to/PySide6-ANDROID.whl \
  --shiboken-wheel /path/to/shiboken6-ANDROID.whl
uv run python scripts/android.py install --serial emulator-5554 --apk /path/to/app.apk
```

`build` stages only application sources/resources, runs Qt's initializer to
generate ABI-specific recipes, then adds the Android runtime pins/local recipes and invokes
Buildozer directly. It adds JSON/QM/font/license assets and Internet/network/Wi-Fi/
multicast permissions. It includes pyjnius for the QtNative activity multicast
lease, held only during foreground sync. Native cryptography/cffi and optional
zeroconf extensions must cross-compile with compatible p4a recipes/Rust tooling;
the script does not copy Linux extension modules or claim these recipes succeed.
Inspect APK contents, Python ABI, 16 KiB page compatibility and licenses before
installing. If deployment fails, retained files are under `build/android/<arch>`.

For Android 17 targets (SDK 37+), add and request ACCESS_LOCAL_NETWORK before
starting sync. The adapter refuses network startup without that grant, but the
native runtime permission prompt is not implemented yet. The API-35 preparation
does not request it, following [Android's target-specific rules](https://developer.android.com/privacy-and-security/local-network-permission).
FileDialog's Android `content://` selections still need a bounded QFile snapshot
adapter; ordinary filesystem import does not imply Storage Access Framework
support. Emulator NAT commonly prevents multicast/peer discovery: use physical
devices on the same WLAN for acceptance. ADB is a host tool, not part of discovery.

The runner blocks ADB's local listener, so no emulator session or device
installation has been verified here. An installed SDKMAN JDK 17 is selected even
though the default system Java is newer. Network access may also block downloads
of uncached build dependencies; retained logs distinguish those failures from
compiler errors.

## iOS

Build on macOS with Xcode, matching iOS Qt/PySide/shiboken wheels and the matching
Python.xcframework using [pyside6-ios-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-ios-deploy.html).
Linux cannot produce a signed iOS build. Native cryptography/cffi/zeroconf must
also be built for the device/simulator target; host extensions cannot be reused.

Merge `platforms/ios/Info.sync.plist` into the generated app Info.plist. It declares
NSLocalNetworkUsageDescription and `_epubify._tcp` under NSBonjourServices. Never
replace the entire generated plist with this fragment. Raw zeroconf multicast
requires the entitlement in `Sync.entitlements` and Apple's approval/provisioning;
merely adding a file does not grant it. A future native Bonjour backend could
avoid raw multicast requirements. Follow [Apple local network privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy).

Request access through an explicit foreground sync action. Handle permission
denial without blocking reading; retry after the user changes system settings.
There is no continuous/background socket service on iOS, no invented background
mode and no cloud push dependency. Sign, provision and test on physical devices;
simulator tests do not validate local network prompts, signing or App Store rules.

## Acceptance gates

Install two target builds on a shared WLAN; deny/allow network access; pair using
a single-use invitation; transfer a generated EPUB and note; disconnect Wi-Fi;
edit both devices; reconnect and resolve the retained conflict; background/resume;
restart; revoke. Confirm no network service survives backgrounding and no data
leaves the paired LAN. Repeat IPv4/IPv6 and blocked-multicast cases. These checks
remain pending on both mobile platforms.
