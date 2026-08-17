<div align="center">

# NeoStation iOS

<h4>iOS 18+ port of the NeoStation Flutter emulation frontend</h4>

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE.md)
[![Stars](https://img.shields.io/github/stars/TarbleFR/neostation-ios?logo=github)](https://github.com/TarbleFR/neostation-ios/stargazers)
[![Issues](https://img.shields.io/github/issues/TarbleFR/neostation-ios)](https://github.com/TarbleFR/neostation-ios/issues)
[![Platform](https://img.shields.io/badge/Platform-iOS%2018%2B-blue)](https://github.com/TarbleFR/neostation-ios)

<img src="https://raw.githubusercontent.com/TarbleFR/neostation-ios/main/assets/readme/neostation-ios-preview.png" alt="NeoStation iOS menu preview" width="100%" />

</div>

NeoStation iOS is an **iOS 18+ port** of the upstream [NeoStation](https://github.com/misobadev/neostation-frontend) project. It keeps the original Flutter frontend while adding iOS-specific file handling, emulator integration, library synchronization, sideloading and JIT workflows.

> **Modified version notice — August 2026**  
> This repository contains a modified version of NeoStation. The upstream project and its contributors retain credit for the original work. The iOS-specific port and adaptations in this repository are developed and maintained by [@TarbleFR](https://github.com/TarbleFR). This does not imply endorsement by the upstream NeoStation maintainers. The covered modified work is distributed under the GNU General Public License v3.0.

## iOS features

- **iOS 18+** target.
- **RetroArch** library synchronization and direct game launching through deeplinks.
- **MeloNX** library synchronization, media association, direct launching and JIT workflows.
- **ARMSX2** library synchronization, direct launching and JIT workflows.
- Installed-emulator detection in NeoStation settings.
- iOS-specific document, media and file handling.
- Custom main-menu backgrounds using static images, GIFs or videos.
- SideStore and compatible sideloading workflows.
- ScreenScraper metadata and media scraping.
- RetroAchievements support.
- NeoSync account and cloud-save features inherited from NeoStation.

The upstream NeoStation project also supports other platforms. This repository is maintained primarily as the **iOS port**; refer to the upstream repository for the canonical non-iOS project documentation and releases.

## Requirements

- iOS 18 or newer.
- An IPA signing/sideloading method such as SideStore or another compatible installer, or Apple Developer signing.
- RetroArch, MeloNX or ARMSX2 where the related integration is used.
- Flutter SDK ≥ 3.9.2 and macOS/Xcode only when building iOS locally.

## Build from source

Clone **this iOS port**:

```bash
git clone https://github.com/TarbleFR/neostation-ios.git
cd neostation-ios
flutter pub get
```

For a local unsigned iOS build on macOS:

```bash
flutter build ios --release --no-codesign \
  --dart-define=SCREENSCRAPER_DEV_ID=your_id \
  --dart-define=SCREENSCRAPER_DEV_PASSWORD=your_password
```

## ScreenScraper configuration

ScreenScraper requires developer credentials before NeoStation can communicate with the API. These developer credentials are separate from each user's ScreenScraper account credentials.

For local development, create `.env` from `.env.example` and fill both values:

```powershell
Copy-Item .env.example .env
```

```text
SCREENSCRAPER_DEV_ID=your_developer_id
SCREENSCRAPER_DEV_PASSWORD=your_developer_password
```

`.env` is intentionally excluded from Git and **must never be committed**.

The current ScreenScraper user-credential path uses the project's established SQLite/Base64 persistence.

## Project structure

```text
lib/
├── data/          SQLite access and migrations
├── l10n/          localization
├── models/        data models
├── providers/     application state
├── repositories/  data access layer
├── screens/       UI screens
├── services/      business logic and integrations
├── sync/          cloud synchronization
├── themes/        themes
├── utils/         helpers
└── widgets/       reusable UI
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for additional implementation details.

## Upstream project and attribution

NeoStation iOS is based on the upstream **NeoStation** project:

- Upstream repository: https://github.com/misobadev/neostation-frontend
- Lead: **[@misobadev](https://github.com/misobadev)**
- Official co-maintainer: **[@androosio](https://github.com/androosio)**
- Official collaborator: **[@ItsRetroPup](https://github.com/ItsRetroPup)**

All upstream authors and contributors retain attribution for their contributions. The upstream repository history and contributor list remain the authoritative record for the original project.

### iOS port

- iOS port developer / maintainer: **[@TarbleFR](https://github.com/TarbleFR)**
- Patreon: **[TarbleFR](https://www.patreon.com/cw/TarbleFR)**
- Reddit: **[u/Mysterious_Air2053](https://www.reddit.com/user/Mysterious_Air2053/)**
- Modified iOS version maintained since **August 2026**.

The iOS port includes sideloading adaptations, emulator detection and launch flows, library synchronization, JIT-related workflows, iOS UI/file-handling adaptations and other iOS-specific integration work.

## GPL-3.0 and corresponding source

NeoStation and this modified iOS port are distributed under the **GNU General Public License v3.0 (GPL-3.0)**. See [`LICENSE.md`](LICENSE.md) for the complete license text and [`NOTICE.md`](NOTICE.md) for copyright, modification and third-party notices.

The **corresponding source** for an IPA built from this repository is the exact source commit or tag used to produce that binary.

When redistributing an IPA elsewhere, keep the GPL and applicable notices available to recipients and provide a clear reference or link to the corresponding source commit. Do not distribute only an older upstream source or only a patch against another version.

Third-party components, packages, artwork, trademarks and emulator projects can have their own licenses or terms. Their notices must be preserved where applicable; see [`NOTICE.md`](NOTICE.md) and the license files shipped with vendored packages.

## Contributing

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a bug report, feature request or pull request.

## Security

Please follow [`SECURITY.md`](SECURITY.md) for responsible vulnerability reporting.

## License

GNU General Public License v3.0. Nothing in this README restricts or replaces the rights granted by the GPL-3.0.
