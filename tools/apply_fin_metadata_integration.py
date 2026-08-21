from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel_path: str, old: str, new: str) -> None:
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Anchor not found in {rel_path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(rel_path: str, old: str, new: str, expected_min: int = 1) -> None:
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count < expected_min:
        raise RuntimeError(
            f"Expected at least {expected_min} occurrences in {rel_path}, found {count}: {old!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


# ---------------------------------------------------------------------------
# LibraryCatalogItem: preserve genuine trailer/video URLs returned by providers.
# ---------------------------------------------------------------------------
replace_once(
    "lib/services/library_catalog_service.dart",
    """    required this.pageUrls,\n    required this.raw,\n  });\n""",
    """    required this.pageUrls,\n    required this.raw,\n    this.videoUrls = const <String>[],\n  });\n""",
)
replace_once(
    "lib/services/library_catalog_service.dart",
    """  final List<String> pageUrls;\n  final Map<String, dynamic> raw;\n\n  bool get hasReadableContent =>\n""",
    """  final List<String> pageUrls;\n  final List<String> videoUrls;\n  final Map<String, dynamic> raw;\n\n  bool get hasReadableContent =>\n""",
)
replace_once(
    "lib/services/library_catalog_service.dart",
    """    final pageUrls = <String>[];\n    final rawPages = raw['pages'] ?? raw['images'];\n    if (rawPages is List) {\n      for (final page in rawPages) {\n        final resolved = resolveUrl(page);\n        if (resolved != null) pageUrls.add(resolved);\n      }\n    }\n\n    final inlineContent =\n""",
    """    final pageUrls = <String>[];\n    final rawPages = raw['pages'] ?? raw['images'];\n    if (rawPages is List) {\n      for (final page in rawPages) {\n        final resolved = resolveUrl(page);\n        if (resolved != null) pageUrls.add(resolved);\n      }\n    }\n\n    final videoUrls = <String>[];\n    void addVideo(dynamic value) {\n      if (value is List) {\n        for (final entry in value) {\n          addVideo(entry);\n        }\n        return;\n      }\n      if (value is Map) {\n        for (final key in const ['url', 'videoUrl', 'trailerUrl', 'youtubeUrl']) {\n          if (value.containsKey(key)) addVideo(value[key]);\n        }\n        return;\n      }\n      final resolved = resolveUrl(value);\n      if (resolved != null && !videoUrls.contains(resolved)) {\n        videoUrls.add(resolved);\n      }\n    }\n\n    addVideo(raw['videoUrl']);\n    addVideo(raw['trailerUrl']);\n    addVideo(raw['videos']);\n    addVideo(raw['trailers']);\n\n    final inlineContent =\n""",
)
replace_once(
    "lib/services/library_catalog_service.dart",
    """      pageUrls: List.unmodifiable(pageUrls),\n      raw: Map<String, dynamic>.unmodifiable(raw),\n""",
    """      pageUrls: List.unmodifiable(pageUrls),\n      videoUrls: List.unmodifiable(videoUrls),\n      raw: Map<String, dynamic>.unmodifiable(raw),\n""",
)

# ---------------------------------------------------------------------------
# Metadata provider adapters: fix endpoint joining and a few Dart type details.
# ---------------------------------------------------------------------------
replace_once(
    "lib/services/library_metadata_provider_service.dart",
    "final safeLimit = limit.clamp(1, 25);",
    "final safeLimit = limit.clamp(1, 25).toInt();",
)
replace_all(
    "lib/services/library_metadata_provider_service.dart",
    "Uri.parse(base).resolve(endpointPath)",
    "_joinEndpoint(base, endpointPath)",
    expected_min=5,
)
replace_once(
    "lib/services/library_metadata_provider_service.dart",
    """  static String? _extractArk(List<String> values) {\n""",
    """  static Uri _joinEndpoint(String base, String endpoint) {\n    final baseUri = Uri.parse(base);\n    final basePath = baseUri.path.endsWith('/')\n        ? baseUri.path.substring(0, baseUri.path.length - 1)\n        : baseUri.path;\n    final suffix = endpoint.startsWith('/') ? endpoint : '/$endpoint';\n    return baseUri.replace(path: '$basePath$suffix');\n  }\n\n  static String? _extractArk(List<String> values) {\n""",
)
replace_once(
    "lib/services/library_metadata_provider_service.dart",
    """  static void _validateResponse(Uri uri, http.Response response) {\n    if (response.statusCode < 200 || response.statusCode >= 300) {\n      throw StateError(\n        '${uri.host} returned HTTP ${response.statusCode}.',\n      );\n    }\n    if (response.bodyBytes.length > _maxBodyBytes) {\n      throw StateError('${uri.host} returned an unexpectedly large response.');\n    }\n  }\n}\n""",
    """  static void _validateResponse(Uri uri, http.Response response) {\n    if (response.statusCode < 200 || response.statusCode >= 300) {\n      throw StateError(\n        '${uri.host} returned HTTP ${response.statusCode}.',\n      );\n    }\n    if (response.bodyBytes.length > _maxBodyBytes) {\n      throw StateError('${uri.host} returned an unexpectedly large response.');\n    }\n  }\n}\n\nextension _FirstOrNull<T> on Iterable<T> {\n  T? get firstOrNull => isEmpty ? null : first;\n}\n""",
)

# ---------------------------------------------------------------------------
# Native Library: make all seven metadata providers searchable/filterable and
# show their metadata/video details instead of treating them as reading feeds.
# ---------------------------------------------------------------------------
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """import 'package:neostation/services/library_mangadex_service.dart';\nimport 'package:neostation/services/sfx_service.dart';\n""",
    """import 'package:neostation/services/library_mangadex_service.dart';\nimport 'package:neostation/services/library_metadata_provider_service.dart';\nimport 'package:neostation/services/sfx_service.dart';\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """import 'library_reader_screen.dart';\n""",
    """import 'library_reader_screen.dart';\nimport 'library_metadata_detail_dialog.dart';\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """  final LibraryMangaDexService _mangaDexService = LibraryMangaDexService.instance;\n\n  final ScrollController _libraryScrollController = ScrollController();\n""",
    """  final LibraryMangaDexService _mangaDexService = LibraryMangaDexService.instance;\n  final LibraryMetadataProviderService _metadataProviderService =\n      LibraryMetadataProviderService.instance;\n\n  final ScrollController _libraryScrollController = ScrollController();\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """    final options = <String, String>{\n      'all': 'all',\n      LibraryMangaDexService.providerId: 'MangaDex',\n    };\n""",
    """    final options = <String, String>{\n      'all': 'all',\n      LibraryMangaDexService.providerId: 'MangaDex',\n      ..._metadataProviderService.providerLabels,\n    };\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """      final label = entry.isMangaDex\n          ? 'MangaDex'\n          : (entry.source?.name.trim().isNotEmpty == true\n              ? entry.source!.name.trim()\n              : entry.providerId);\n""",
    """      final label = entry.isMangaDex\n          ? 'MangaDex'\n          : (_metadataProviderService.labelFor(entry.providerId) ??\n              (entry.source?.name.trim().isNotEmpty == true\n                  ? entry.source!.name.trim()\n                  : entry.providerId));\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """  Future<void> _loadAddons() async {\n    final addons = await _addonService.load();\n""",
    """  Future<void> _loadAddons() async {\n    try {\n      await _metadataProviderService.initialize();\n    } catch (_) {\n      // The native Library remains usable even if the bundled provider registry\n      // cannot be loaded for some reason.\n    }\n    final addons = await _addonService.load();\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """  Future<void> _runTitleSearch(String rawQuery) async {\n""",
    """  Future<List<_NativeLibraryEntry>> _searchMetadataProviders(\n    String query,\n  ) async {\n    try {\n      await _metadataProviderService.initialize();\n      Set<String>? providerIds;\n      if (_sourceFilter != 'all') {\n        if (!_metadataProviderService.isProviderId(_sourceFilter)) {\n          return const <_NativeLibraryEntry>[];\n        }\n        providerIds = <String>{_sourceFilter};\n      }\n\n      final groups = await _metadataProviderService.searchAll(\n        query,\n        providerIds: providerIds,\n      );\n      final entries = <_NativeLibraryEntry>[];\n      for (final group in groups.entries) {\n        for (final item in group.value) {\n          entries.add(\n            _NativeLibraryEntry(providerId: group.key, item: item),\n          );\n        }\n      }\n      return entries;\n    } catch (_) {\n      return const <_NativeLibraryEntry>[];\n    }\n  }\n\n  Future<void> _runTitleSearch(String rawQuery) async {\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """      }(),\n      for (final addon in _addons.where(\n""",
    """      }(),\n      _searchMetadataProviders(query),\n      for (final addon in _addons.where(\n""",
)
replace_once(
    "lib/screens/library_screen/library_screen.dart",
    """  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {\n    if (entry.source != null && _aidokuNativeService.supports(entry.source!)) {\n""",
    """  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {\n    if (_metadataProviderService.isProviderId(entry.providerId)) {\n      await showLibraryMetadataDetailDialog(\n        context,\n        item: entry.item,\n        providerName:\n            _metadataProviderService.labelFor(entry.providerId) ?? entry.providerId,\n      );\n      return;\n    }\n\n    if (entry.source != null && _aidokuNativeService.supports(entry.source!)) {\n""",
)

# ---------------------------------------------------------------------------
# iOS settings: Fin library card + separate Shortcut configuration card.
# ---------------------------------------------------------------------------
replace_once(
    "lib/screens/settings_screen/new_settings_options/directories_settings_content.dart",
    """import 'package:neostation/services/rpcs3_library_service.dart';\nimport 'package:neostation/services/ios_shortcut_jit_launch_service.dart';\n""",
    """import 'package:neostation/services/rpcs3_library_service.dart';\nimport 'package:neostation/services/fin_library_service.dart';\nimport 'package:neostation/services/ios_shortcut_jit_launch_service.dart';\n""",
)
replace_once(
    "lib/screens/settings_screen/new_settings_options/directories_settings_content.dart",
    """  Future<void> _linkRpcs3DataFolder() async {\n""",
    """  Future<void> _linkFinGamesFolder() async {\n    if (_linkingFolderKey != null) return;\n    final fr = Localizations.localeOf(context).languageCode == 'fr';\n    setState(() => _linkingFolderKey = FinLibraryService.bookmarkKey);\n    try {\n      final result = await FinLibraryService.linkAndSync();\n      if (result == null || !mounted) return;\n      setState(() {});\n      AppNotification.showNotification(\n        context,\n        fr\n            ? '${result.discoveredGames} jeu(x) Fin synchronisé(s) • '\n                  '${result.gameCubeGames} GameCube • ${result.wiiGames} Wii'\n            : '${result.discoveredGames} Fin game(s) synced • '\n                  '${result.gameCubeGames} GameCube • ${result.wiiGames} Wii',\n        type: NotificationType.success,\n      );\n    } on FormatException {\n      if (mounted) {\n        AppNotification.showNotification(\n          context,\n          fr\n              ? 'Sélectionne le dossier Fin/Games (ou le dossier Fin qui contient Games).'\n              : 'Select Fin/Games (or the Fin folder that contains Games).',\n          type: NotificationType.error,\n        );\n      }\n    } catch (e) {\n      _log.e('Fin folder link/sync failed: $e');\n      if (mounted) {\n        AppNotification.showNotification(\n          context,\n          fr ? 'Synchronisation Fin impossible : $e' : 'Fin sync failed: $e',\n          type: NotificationType.error,\n        );\n      }\n    } finally {\n      if (mounted) setState(() => _linkingFolderKey = null);\n    }\n  }\n\n  Future<void> _syncWithFin() async {\n    final fr = Localizations.localeOf(context).languageCode == 'fr';\n    try {\n      final result = await FinLibraryService.syncLinkedLibrary();\n      if (!mounted) return;\n      setState(() {});\n      AppNotification.showNotification(\n        context,\n        fr\n            ? '${result.discoveredGames} jeu(x) Fin synchronisé(s) • '\n                  '${result.gameCubeGames} GameCube • ${result.wiiGames} Wii'\n            : '${result.discoveredGames} Fin game(s) synced • '\n                  '${result.gameCubeGames} GameCube • ${result.wiiGames} Wii',\n        type: NotificationType.success,\n      );\n    } catch (e) {\n      _log.e('Fin library sync failed: $e');\n      if (mounted) {\n        AppNotification.showNotification(\n          context,\n          fr ? 'Synchronisation Fin impossible : $e' : 'Fin sync failed: $e',\n          type: NotificationType.error,\n        );\n      }\n    }\n  }\n\n  Future<void> _configureFinLaunch() async {\n    final opened = await IosShortcutJitLaunchService.openFinShortcutInstaller();\n    if (!mounted || opened) return;\n    AppNotification.showNotification(\n      context,\n      AppLocale.shortcutSetupOpenError.getString(context),\n      type: NotificationType.error,\n    );\n  }\n\n  Future<void> _testFinLaunch() async {\n    final fr = Localizations.localeOf(context).languageCode == 'fr';\n    final opened = await IosShortcutJitLaunchService.run(\n      shortcutName: IosShortcutJitLaunchService.finShortcutName,\n      input: '__NEOSTATION_TEST__',\n    );\n    if (!mounted) return;\n    AppNotification.showNotification(\n      context,\n      opened\n          ? (fr\n                ? 'Test envoyé au raccourci NeoStation+Fin.'\n                : 'Test sent to the NeoStation+Fin Shortcut.')\n          : (fr\n                ? 'Le raccourci NeoStation+Fin n’a pas pu être lancé.'\n                : 'NeoStation+Fin Shortcut could not be launched.'),\n      type: opened ? NotificationType.info : NotificationType.error,\n    );\n  }\n\n  Future<void> _linkRpcs3DataFolder() async {\n""",
)
replace_once(
    "lib/screens/settings_screen/new_settings_options/directories_settings_content.dart",
    """      _buildIOSArmsx2Section(theme),\n      _buildIOSMeloNXSection(theme),\n    ];\n""",
    """      _buildIOSArmsx2Section(theme),\n      _buildIOSMeloNXSection(theme),\n      _buildIOSFinLibrarySection(theme),\n      _buildIOSFinShortcutSection(theme),\n    ];\n""",
)
replace_once(
    "lib/screens/settings_screen/new_settings_options/directories_settings_content.dart",
    """  Widget _buildIOSEmulatorCard({\n""",
    """  Widget _buildIOSFinLibrarySection(ThemeData theme) {\n    final fr = Localizations.localeOf(context).languageCode == 'fr';\n    final isLinked = FinLibraryService.isLinked;\n    final hasSynced = FinLibraryService.hasSyncedLibrary;\n    final count = FinLibraryService.syncedGameCount;\n    final gcCount = FinLibraryService.gameCubeCount;\n    final wiiCount = FinLibraryService.wiiCount;\n    final skipped = FinLibraryService.skippedGameCount;\n\n    final String statusText;\n    if (!isLinked) {\n      statusText = fr\n          ? 'Sélectionne Fin/Games pour importer les jeux GameCube et Wii.'\n          : 'Select Fin/Games to import GameCube and Wii games.';\n    } else if (!hasSynced) {\n      statusText = fr\n          ? 'Dossier Fin lié • synchronisation requise.'\n          : 'Fin folder linked • sync required.';\n    } else {\n      statusText = '$count ${fr ? 'jeu(x)' : 'game(s)'} • '\n          '$gcCount GameCube • $wiiCount Wii'\n          '${skipped > 0 ? ' • $skipped ${fr ? 'non classé(s)' : 'unclassified'}' : ''}';\n    }\n\n    return _buildIOSEmulatorCard(\n      theme: theme,\n      name: 'Fin — GameCube & Wii',\n      icon: Symbols.sports_esports_rounded,\n      statusText: statusText,\n      isLinked: isLinked,\n      bookmarkKey: FinLibraryService.bookmarkKey,\n      successMessage: '',\n      onLinkPressed: _linkFinGamesFolder,\n      trailingAction: SizedBox(\n        height: 48.r,\n        child: FilledButton.icon(\n          onPressed: isLinked && _linkingFolderKey == null ? _syncWithFin : null,\n          icon: Icon(Symbols.sync_rounded, size: 20.r),\n          label: Text(\n            hasSynced\n                ? AppLocale.iosEmuResync.getString(context)\n                : AppLocale.iosEmuSync.getString(context),\n            style: TextStyle(fontSize: 14.r),\n          ),\n        ),\n      ),\n    );\n  }\n\n  Widget _buildIOSFinShortcutSection(ThemeData theme) {\n    final fr = Localizations.localeOf(context).languageCode == 'fr';\n    return _buildIOSEmulatorCard(\n      theme: theme,\n      name: 'Fin Shortcut',\n      icon: Symbols.rocket_launch_rounded,\n      statusText: fr\n          ? 'Raccourci attendu : NeoStation+Fin. NeoStation lui transmet le chemin relatif du jeu sous Fin/Games.'\n          : 'Expected Shortcut: NeoStation+Fin. NeoStation passes the game path relative to Fin/Games.',\n      isLinked: true,\n      bookmarkKey: 'fin-shortcut',\n      successMessage: '',\n      showLinkButton: false,\n      trailingAction: Row(\n        children: [\n          Expanded(\n            child: SizedBox(\n              height: 48.r,\n              child: FilledButton.icon(\n                onPressed: _configureFinLaunch,\n                icon: Icon(Symbols.add_rounded, size: 20.r),\n                label: Text(\n                  IosShortcutJitLaunchService.hasFinShortcutInstaller\n                      ? (fr ? 'Installer' : 'Install')\n                      : (fr ? 'Créer' : 'Create'),\n                  style: TextStyle(fontSize: 14.r),\n                ),\n              ),\n            ),\n          ),\n          SizedBox(width: 10.r),\n          Expanded(\n            child: SizedBox(\n              height: 48.r,\n              child: OutlinedButton.icon(\n                onPressed: _testFinLaunch,\n                icon: Icon(Symbols.play_arrow_rounded, size: 20.r),\n                label: Text(fr ? 'Tester' : 'Test'),\n              ),\n            ),\n          ),\n        ],\n      ),\n    );\n  }\n\n  Widget _buildIOSEmulatorCard({\n""",
)

# ---------------------------------------------------------------------------
# Game launch flow: Fin gets first chance for GameCube/Wii, then RetroArch.
# ---------------------------------------------------------------------------
replace_once(
    "lib/services/game/game_launch_service.dart",
    """import 'package:neostation/services/rpcs3_launch_service.dart';\nimport 'package:neostation/services/logger_service.dart';\n""",
    """import 'package:neostation/services/rpcs3_launch_service.dart';\nimport 'package:neostation/services/fin_library_service.dart';\nimport 'package:neostation/services/logger_service.dart';\n""",
)
replace_once(
    "lib/services/game/game_launch_service.dart",
    """      final isRpcs3VirtualRom =\n          Platform.isIOS &&\n          system.folderName.toLowerCase() == 'ps3' &&\n          game.romPath != null &&\n          Rpcs3LibraryService.isVirtualLibraryPath(game.romPath!);\n\n      bool romExists = false;\n""",
    """      final isRpcs3VirtualRom =\n          Platform.isIOS &&\n          system.folderName.toLowerCase() == 'ps3' &&\n          game.romPath != null &&\n          Rpcs3LibraryService.isVirtualLibraryPath(game.romPath!);\n      final isFinVirtualRom =\n          Platform.isIOS &&\n          (system.folderName.toLowerCase() == 'gc' ||\n              system.folderName.toLowerCase() == 'wii') &&\n          game.romPath != null &&\n          FinLibraryService.isVirtualLibraryPath(game.romPath!);\n\n      bool romExists = false;\n""",
)
replace_once(
    "lib/services/game/game_launch_service.dart",
    """        if (isArmsx2VirtualRom || isMeloNXVirtualRom || isRpcs3VirtualRom) {\n""",
    """        if (isArmsx2VirtualRom ||\n            isMeloNXVirtualRom ||\n            isRpcs3VirtualRom ||\n            isFinVirtualRom) {\n""",
)
replace_once(
    "lib/services/game/game_launch_service.dart",
    """        // Nintendo Switch: MeloNX exposes an alternate-frontend library export\n""",
    """        // Nintendo GameCube / Wii: Fin exposes its game folder through Files.\n        // When that library has been synced, NeoStation resolves the selected\n        // row to a relative path and hands it to the user-installed\n        // NeoStation+Fin Shortcut. Physical rows still fall through to\n        // RetroArch/Open In if Fin is not configured.\n        final systemFolder = system.folderName.toLowerCase();\n        if (systemFolder == 'gc' || systemFolder == 'wii') {\n          try {\n            final launched = await FinLibraryService.launchGameByRomPath(\n              game.romPath!,\n            );\n            if (launched) return GameLaunchResult.success();\n          } catch (e) {\n            // Physical GameCube/Wii rows can still fall through to RetroArch.\n          }\n\n          if (isFinVirtualRom) {\n            return GameLaunchResult.failure(\n              'Could not launch this ${systemFolder == 'gc' ? 'GameCube' : 'Wii'} game in Fin.',\n              game.romPath,\n            );\n          }\n        }\n\n        // Nintendo Switch: MeloNX exposes an alternate-frontend library export\n""",
)

# ---------------------------------------------------------------------------
# Startup: restore Fin bookmark/cache and virtual rows on cold launch.
# ---------------------------------------------------------------------------
replace_once(
    "lib/main.dart",
    """import 'package:neostation/services/rpcs3_library_service.dart';\nimport 'package:neostation/services/rpcs3_launch_service.dart';\n""",
    """import 'package:neostation/services/rpcs3_library_service.dart';\nimport 'package:neostation/services/rpcs3_launch_service.dart';\nimport 'package:neostation/services/fin_library_service.dart';\n""",
)
replace_once(
    "lib/main.dart",
    """    await MelonxLibraryService.loadCachedLibrary();\n    await Rpcs3LibraryService.initialize();\n    await Rpcs3LaunchService.initialize();\n""",
    """    await MelonxLibraryService.loadCachedLibrary();\n    await FinLibraryService.initialize();\n    await Rpcs3LibraryService.initialize();\n    await Rpcs3LaunchService.initialize();\n""",
)
replace_once(
    "lib/main.dart",
    """      await Rpcs3LibraryService.restoreAfterDatabaseReady(\n        configProvider: sqliteConfigProvider,\n        databaseProvider: sqliteDatabaseProvider,\n      );\n""",
    """      await Rpcs3LibraryService.restoreAfterDatabaseReady(\n        configProvider: sqliteConfigProvider,\n        databaseProvider: sqliteDatabaseProvider,\n      );\n      await FinLibraryService.restoreAfterDatabaseReady(\n        configProvider: sqliteConfigProvider,\n        databaseProvider: sqliteDatabaseProvider,\n      );\n""",
)

print("Fin + Library metadata integration patch applied successfully.")
