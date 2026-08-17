from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"Missing patch marker: {label}")
    return text.replace(old, new, 1)


# Fix a Dart int typing detail in the newly added parser.
service_path = Path("lib/services/rpcs3_library_service.dart")
service = service_path.read_text(encoding="utf-8")
service = service.replace(
    "final safeLimit = limit.clamp(start, bytes.length);",
    "final safeLimit = limit.clamp(start, bytes.length) as int;",
)
service_path.write_text(service, encoding="utf-8")

# main.dart: restore bookmark/cache at startup.
main_path = Path("lib/main.dart")
main = main_path.read_text(encoding="utf-8")
main = replace_once(
    main,
    "import 'package:neostation/services/melonx_library_service.dart';\n",
    "import 'package:neostation/services/melonx_library_service.dart';\n"
    "import 'package:neostation/services/rpcs3_library_service.dart';\n",
    "main RPCS3 import",
)
main = replace_once(
    main,
    "    await RetroArchLibraryService.loadCachedLibrary();\n"
    "    await Armsx2LibraryService.loadCachedLibrary();\n"
    "    await MelonxLibraryService.loadCachedLibrary();\n",
    "    await RetroArchLibraryService.loadCachedLibrary();\n"
    "    await Armsx2LibraryService.loadCachedLibrary();\n"
    "    await MelonxLibraryService.loadCachedLibrary();\n"
    "    await Rpcs3LibraryService.initialize();\n",
    "main RPCS3 initialization",
)
main_path.write_text(main, encoding="utf-8")

# Settings: add RPCS3 Data-folder card and sync actions.
settings_path = Path(
    "lib/screens/settings_screen/new_settings_options/directories_settings_content.dart"
)
settings = settings_path.read_text(encoding="utf-8")
settings = replace_once(
    settings,
    "import 'package:neostation/services/melonx_library_service.dart';\n",
    "import 'package:neostation/services/melonx_library_service.dart';\n"
    "import 'package:neostation/services/rpcs3_library_service.dart';\n",
    "settings RPCS3 import",
)
settings = replace_once(
    settings,
    "import 'package:neostation/l10n/app_locale.dart';\n",
    "import 'package:neostation/l10n/app_locale.dart';\n"
    "import 'package:neostation/l10n/rpcs3_library_locale.dart';\n",
    "settings RPCS3 locale import",
)

methods_marker = "  List<Widget> _iosEmulatorCards(ThemeData theme) {\n"
methods = """  Future<void> _linkRpcs3DataFolder() async {
    if (_linkingFolderKey != null) return;

    setState(() => _linkingFolderKey = Rpcs3LibraryService.bookmarkKey);
    try {
      final result = await Rpcs3LibraryService.linkAndSync();
      if (result == null || !mounted) return;

      setState(() {});
      AppNotification.showNotification(
        context,
        result.discoveredGames == 0
            ? Rpcs3LibraryLocale.noGames(context)
            : Rpcs3LibraryLocale.syncComplete(
                context,
                result.discoveredGames,
              ),
        type: result.discoveredGames == 0
            ? NotificationType.info
            : NotificationType.success,
      );
    } on FormatException {
      if (mounted) {
        AppNotification.showNotification(
          context,
          Rpcs3LibraryLocale.invalidFolder(context),
          type: NotificationType.error,
        );
      }
    } catch (e) {
      _log.e('RPCS3 folder link/sync failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          Rpcs3LibraryLocale.syncFailed(context, e),
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _linkingFolderKey = null);
      }
    }
  }

  Future<void> _syncWithRpcs3() async {
    try {
      final result = await Rpcs3LibraryService.syncLinkedLibrary();
      if (!mounted) return;
      setState(() {});
      AppNotification.showNotification(
        context,
        result.discoveredGames == 0
            ? Rpcs3LibraryLocale.noGames(context)
            : Rpcs3LibraryLocale.syncComplete(
                context,
                result.discoveredGames,
              ),
        type: result.discoveredGames == 0
            ? NotificationType.info
            : NotificationType.success,
      );
    } catch (e) {
      _log.e('RPCS3 library sync failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          Rpcs3LibraryLocale.syncFailed(context, e),
          type: NotificationType.error,
        );
      }
    }
  }

"""
if "Future<void> _linkRpcs3DataFolder()" not in settings:
    if methods_marker not in settings:
        raise SystemExit("Missing patch marker: settings methods")
    settings = settings.replace(methods_marker, methods + methods_marker, 1)

settings = replace_once(
    settings,
    "    return [\n"
    "      _buildIOSRetroArchSection(theme),\n"
    "      _buildIOSArmsx2Section(theme),\n"
    "      _buildIOSMeloNXSection(theme),\n"
    "    ];\n",
    "    return [\n"
    "      _buildIOSRetroArchSection(theme),\n"
    "      _buildIOSRpcs3Section(theme),\n"
    "      _buildIOSArmsx2Section(theme),\n"
    "      _buildIOSMeloNXSection(theme),\n"
    "    ];\n",
    "settings RPCS3 card list",
)

rpcs3_card_marker = (
    "  /// ARMSX2 is sync-only, like MeloNX. Its exported library is authoritative\n"
)
rpcs3_card = """  Widget _buildIOSRpcs3Section(ThemeData theme) {
    final isLinked = Rpcs3LibraryService.isLinked;
    final hasSynced = Rpcs3LibraryService.hasSyncedLibrary;
    final count = Rpcs3LibraryService.syncedGameCount;

    final String statusText;
    if (!isLinked) {
      statusText = Rpcs3LibraryLocale.statusNeedsLink(context);
    } else if (!hasSynced) {
      statusText = Rpcs3LibraryLocale.statusNeedsSync(context);
    } else {
      statusText = Rpcs3LibraryLocale.statusSynced(context, count);
    }

    return _buildIOSEmulatorCard(
      theme: theme,
      name: 'RPCS3',
      icon: Symbols.sports_esports_rounded,
      statusText: statusText,
      isLinked: isLinked,
      bookmarkKey: Rpcs3LibraryService.bookmarkKey,
      successMessage: '',
      onLinkPressed: _linkRpcs3DataFolder,
      trailingAction: SizedBox(
        height: 48.r,
        child: FilledButton.icon(
          onPressed: !isLinked ? null : _syncWithRpcs3,
          icon: Icon(Symbols.sync_rounded, size: 20.r),
          label: Text(
            hasSynced
                ? AppLocale.iosEmuResync.getString(context)
                : AppLocale.iosEmuSync.getString(context),
            style: TextStyle(fontSize: 14.r),
          ),
        ),
      ),
    );
  }

"""
if "Widget _buildIOSRpcs3Section" not in settings:
    if rpcs3_card_marker not in settings:
        raise SystemExit("Missing patch marker: settings RPCS3 card")
    settings = settings.replace(rpcs3_card_marker, rpcs3_card + rpcs3_card_marker, 1)

settings = replace_once(
    settings,
    "    bool showLinkButton = true,\n"
    "    Widget? trailingAction,\n"
    "  }) {\n",
    "    bool showLinkButton = true,\n"
    "    Future<void> Function()? onLinkPressed,\n"
    "    Widget? trailingAction,\n"
    "  }) {\n",
    "settings custom link callback signature",
)
settings = replace_once(
    settings,
    "        onPressed: isAnyLinkInFlight\n"
    "            ? null\n"
    "            : () => _linkExternalFolder(\n"
    "                bookmarkKey: bookmarkKey,\n"
    "                successMessage: successMessage,\n"
    "              ),\n",
    "        onPressed: isAnyLinkInFlight\n"
    "            ? null\n"
    "            : () async {\n"
    "                if (onLinkPressed != null) {\n"
    "                  await onLinkPressed();\n"
    "                } else {\n"
    "                  await _linkExternalFolder(\n"
    "                    bookmarkKey: bookmarkKey,\n"
    "                    successMessage: successMessage,\n"
    "                  );\n"
    "                }\n"
    "              },\n",
    "settings custom link callback",
)
settings_path.write_text(settings, encoding="utf-8")

# Game launch: virtual RPCS3 rows are display-only for this stage.
launch_path = Path("lib/services/game/game_launch_service.dart")
launch = launch_path.read_text(encoding="utf-8")
launch = replace_once(
    launch,
    "import 'package:neostation/services/melonx_library_service.dart';\n",
    "import 'package:neostation/services/melonx_library_service.dart';\n"
    "import 'package:neostation/services/rpcs3_library_service.dart';\n",
    "game launch RPCS3 import",
)
launch = replace_once(
    launch,
    "import 'package:neostation/l10n/app_locale.dart';\n",
    "import 'package:neostation/l10n/app_locale.dart';\n"
    "import 'package:neostation/l10n/rpcs3_library_locale.dart';\n",
    "game launch RPCS3 locale import",
)

virtual_marker = """      final isMeloNXVirtualRom =
          Platform.isIOS &&
          system.folderName.toLowerCase() == 'switch' &&
          game.romPath != null &&
          MelonxLibraryService.isVirtualLibraryPath(game.romPath!);

"""
virtual_addition = virtual_marker + """      final isRpcs3VirtualRom =
          Platform.isIOS &&
          system.folderName.toLowerCase() == 'ps3' &&
          game.romPath != null &&
          Rpcs3LibraryService.isVirtualLibraryPath(game.romPath!);

"""
if "final isRpcs3VirtualRom" not in launch:
    if virtual_marker not in launch:
        raise SystemExit("Missing patch marker: RPCS3 virtual ROM")
    launch = launch.replace(virtual_marker, virtual_addition, 1)

launch = replace_once(
    launch,
    "        if (isArmsx2VirtualRom || isMeloNXVirtualRom) {\n",
    "        if (isArmsx2VirtualRom ||\n"
    "            isMeloNXVirtualRom ||\n"
    "            isRpcs3VirtualRom) {\n",
    "game launch virtual existence",
)
launch = replace_once(
    launch,
    "      if (Platform.isIOS) {\n"
    "        GameSessionManager.registerGameLaunch(system, game, 'ios_direct_launch');\n",
    "      if (Platform.isIOS) {\n"
    "        if (isRpcs3VirtualRom) {\n"
    "          return GameLaunchResult.failure(\n"
    "            Rpcs3LibraryLocale.launchUnavailable(context),\n"
    "            game.romPath,\n"
    "          );\n"
    "        }\n\n"
    "        GameSessionManager.registerGameLaunch(system, game, 'ios_direct_launch');\n",
    "game launch display-only guard",
)
launch_path.write_text(launch, encoding="utf-8")

# Build number and public documentation.
pubspec_path = Path("pubspec.yaml")
pubspec = pubspec_path.read_text(encoding="utf-8")
if "version: 0.9.9+130" not in pubspec:
    if "version: 0.9.9+129" not in pubspec:
        raise SystemExit("Unexpected build version")
    pubspec = pubspec.replace("version: 0.9.9+129", "version: 0.9.9+130", 1)
pubspec_path.write_text(pubspec, encoding="utf-8")

readme_path = Path("README.md")
readme = readme_path.read_text(encoding="utf-8")
bullet = (
    "- **RPCS3 iOS** Data-folder library import for displaying installed PS3 "
    "games and artwork (direct game launch remains pending).\n"
)
marker = (
    "- **ARMSX2** library synchronization, direct launching and JIT-oriented "
    "launch flows.\n"
)
if bullet not in readme:
    if marker not in readme:
        raise SystemExit("Missing README RPCS3 insertion marker")
    readme = readme.replace(marker, marker + bullet, 1)
readme_path.write_text(readme, encoding="utf-8")
