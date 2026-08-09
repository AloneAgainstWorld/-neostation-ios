# iOS Port — Status & How to Build

This documents the experimental iOS port. It is **phase 1**: get NeoStation
installable on an iPhone and browsing a local game library. Emulator
launching is explicitly out of scope for this phase (see "Known limitation"
below) — that's phase 2.

## What was changed

- **`packages/flutter_7zip/ios/`** — new podspec + `Classes/` forwarder,
  mirroring the existing macOS target. The Dart FFI loader
  (`lib/flutter_7zip.dart`) already had an `if (Platform.isIOS)` branch
  for finding the compiled framework, so only the native/CocoaPods side was
  missing.
- **`packages/flutter_7zip/pubspec.yaml`** — declared `ios: ffiPlugin: true`.
- **`packages/gamepads_darwin/ios/`** — new podspec + Swift plugin
  (`GamepadsIosPlugin.swift`), reusing the platform-agnostic
  `GamepadsListener.swift` from the macOS target as-is (it only touches
  `Foundation`/`GameController`, both shared between macOS and iOS).
- **`packages/gamepads_darwin/pubspec.yaml`** and **`packages/gamepads/pubspec.yaml`**
  — wired the new iOS plugin class into the federated plugin's platform map.
- **`pubspec.yaml`** — enabled `flutter_launcher_icons` for `ios`.
- **`lib/services/game/game_launch_service.dart`** — added an early,
  friendly failure for `Platform.isIOS` in `launchGame()` instead of letting
  the code fall through to the desktop `Process.start` path, which would
  throw an unhandled `UnsupportedError` on iOS. The app now degrades
  gracefully: browsing/library features work, launching returns a clear
  "not implemented yet" message rather than crashing.
- **`.github/workflows/ios-build.yml`** — new, separate CI workflow that
  builds the app on a macOS GitHub Actions runner (see below). It does not
  touch the existing release pipeline.
- **`main.dart`** — no changes needed. It already gated every desktop-only
  call (`window_manager`, `fullscreen_window`) behind
  `Platform.isWindows || Platform.isMacOS || Platform.isLinux`, and already
  had an `Platform.isAndroid || Platform.isIOS` branch for immersive
  fullscreen/orientation on mobile.

### What was **not** touched, and why it matters

- **`ios/` Xcode project itself.** It isn't committed — the CI workflow
  generates it fresh with `flutter create --platforms=ios .` on the macOS
  runner. Hand-writing a `project.pbxproj` reliably without a working Xcode
  install to validate it against is far riskier than letting the real
  tooling generate it. If you'd rather have `ios/` committed to the repo
  (e.g. to open it in Xcode locally), run that same `flutter create`
  command yourself on a Mac and commit the result — then delete the
  "Scaffold ios/ platform if missing" step from the workflow.
- **Local folder access / file picking on iOS.** iOS sandboxes app storage
  much more aggressively than desktop or even Android — there's no
  "point at any folder on disk" the way `file_picker` does on Windows/Linux.
  Folder selection will need to go through `UIDocumentPickerViewController`
  with security-scoped bookmarks persisted across launches. This is the
  "modifier les dossiers de jeux" work for the next step — happy to start
  on it once the base IPA is confirmed installable and running.

## Known limitation: emulator launching

NeoStation's launch flow is fundamentally different across platforms:

- **Windows/macOS/Linux**: spawns the emulator as a separate OS process
  (`dart:io Process.start`).
- **Android**: fires a native `Intent` through a `MethodChannel` to open the
  emulator app (e.g. RetroArch) with the ROM.
- **iOS**: neither mechanism exists. `Process` is unimplemented on iOS, and
  there is no equivalent of Android's "send an Intent with a file to any
  installed app" — iOS apps are sandboxed from each other.

The realistic path forward, matching what RetroArch's own iOS build and
apps like Delta do, is embedding libretro cores **directly inside
NeoStation** rather than shelling out to a separate app. That's a
significant, separate piece of engineering — intentionally deferred so this
phase can focus on getting the frontend itself running and browsing a local
library on-device.

## How to build the IPA

The build cannot run on Windows/Linux — it requires a macOS toolchain, which
is why this is done via GitHub Actions rather than locally in most cases.

1. Push this branch to GitHub as `ios-port` (or run the workflow manually
   from the Actions tab — it's set to `workflow_dispatch` too).
2. Go to **Actions → Build iOS (NeoStation)** and watch it run (~15-20 min,
   mostly CocoaPods + Xcode build).
3. Download the artifact:
   - **`NeoStation-ios-unsigned`** if you haven't set up signing secrets —
     this is a raw `.app` you'll need to sign yourself (open
     `ios/Runner.xcworkspace` in Xcode on a Mac, set your Apple ID as the
     team, plug in your iPhone, hit Run — Xcode handles free personal-team
     signing automatically), or sign with a tool like Sideloadly.
   - **`NeoStation-ios-signed`** if you configured the `IOS_CERTIFICATE_*`
     / `IOS_PROVISIONING_PROFILE_*` / `IOS_TEAM_ID` secrets described at the
     top of `ios-build.yml` — this one installs directly (AltStore,
     Sideloadly, Apple Configurator, or `ideviceinstaller`).

Either way, without a paid Apple Developer Program membership the
provisioning profile/certificate expires after 7 days (free account) and
you'll need to re-install periodically — that's an Apple platform policy,
not something specific to this build.

## First run on iOS — what to expect

- The app should launch, show the UI, and let you browse whatever the
  library screens show without a configured ROM folder yet.
- Selecting a game and hitting "launch" will show the "not implemented on
  iOS yet" message added above, instead of crashing.
- Gamepad support (MFi/Bluetooth controllers) should work if you have one
  paired — the `GameController` framework code is shared with the macOS
  build almost verbatim.
- The 7-Zip archive extraction (`flutter_7zip`) should work for opening
  compressed ROMs, same as on other platforms.
