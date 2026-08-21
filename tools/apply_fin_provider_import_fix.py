from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found for {label}: {old[:160]!r}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Keep iOS security-scoped access alive after a folder is selected.
# ---------------------------------------------------------------------------
swift_path = "packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift"
swift = read(swift_path)

if "activeSecurityScopedURLs" not in swift:
    swift = replace_once(
        swift,
        "    private var audioSessionKnownActive = false\n",
        "    private var audioSessionKnownActive = false\n"
        "\n"
        "    /// Security-scoped URLs that must remain active while NeoStation is\n"
        "    /// running. The document picker callback used to stop access as soon\n"
        "    /// as it returned the path to Dart, which meant a service could see\n"
        "    /// the selected directory but fail as soon as it tried to enumerate\n"
        "    /// or open its files. Keep one balanced access grant per bookmark key.\n"
        "    private var activeSecurityScopedURLs: [String: URL] = [:]\n",
        "active security scope dictionary",
    )

old_pick = """        // Bookmark creation itself needs the resource to be accessible;\n        // wrap it in a matched start/stop pair even though the picker's\n        // returned URL is already scoped for this immediate callback.\n        let didStart = url.startAccessingSecurityScopedResource()\n        defer {\n            if didStart { url.stopAccessingSecurityScopedResource() }\n        }\n\n        do {\n            let bookmarkData = try url.bookmarkData(\n                options: [],\n                includingResourceValuesForKeys: nil,\n                relativeTo: nil\n            )\n            UserDefaults.standard.set(\n                bookmarkData,\n                forKey: Self.bookmarkDefaultsKey(for: pendingBookmarkKey)\n            )\n            pendingResult?(url.path)\n        } catch {\n            pendingResult?(\n                FlutterError(\n                    code: \"BOOKMARK_FAILED\",\n                    message: error.localizedDescription,\n                    details: nil\n                )\n            )\n        }\n        pendingResult = nil\n"""
new_pick = """        // Keep the selected folder's security scope alive for the remainder\n        // of this app session. Dart starts enumerating the folder only after this\n        // callback returns, so stopping the scope here makes external app folders\n        // (such as Fin/Games) appear selected but unreadable.\n        let key = pendingBookmarkKey\n        let didStart = url.startAccessingSecurityScopedResource()\n\n        do {\n            let bookmarkData = try url.bookmarkData(\n                options: [],\n                includingResourceValuesForKeys: nil,\n                relativeTo: nil\n            )\n            UserDefaults.standard.set(\n                bookmarkData,\n                forKey: Self.bookmarkDefaultsKey(for: key)\n            )\n\n            if let previous = activeSecurityScopedURLs.removeValue(forKey: key),\n                previous != url\n            {\n                previous.stopAccessingSecurityScopedResource()\n            }\n            if didStart {\n                activeSecurityScopedURLs[key] = url\n            }\n            pendingResult?(url.path)\n        } catch {\n            if didStart { url.stopAccessingSecurityScopedResource() }\n            pendingResult?(\n                FlutterError(\n                    code: \"BOOKMARK_FAILED\",\n                    message: error.localizedDescription,\n                    details: nil\n                )\n            )\n        }\n        pendingResult = nil\n"""
if old_pick in swift:
    swift = swift.replace(old_pick, new_pick, 1)

old_resolve_guard = """    private func resolveBookmarkedFolder(key: String, result: @escaping FlutterResult) {\n        guard\n            let bookmarkData = UserDefaults.standard.data(\n"""
new_resolve_guard = """    private func resolveBookmarkedFolder(key: String, result: @escaping FlutterResult) {\n        if let active = activeSecurityScopedURLs[key] {\n            result(active.path)\n            return\n        }\n\n        guard\n            let bookmarkData = UserDefaults.standard.data(\n"""
if old_resolve_guard in swift:
    swift = swift.replace(old_resolve_guard, new_resolve_guard, 1)

old_resolve_success = """            guard url.startAccessingSecurityScopedResource() else {\n                result(\n                    FlutterError(\n                        code: \"ACCESS_DENIED\",\n                        message: \"startAccessingSecurityScopedResource returned false\",\n                        details: nil\n                    )\n                )\n                return\n            }\n\n            // Sideload updates/re-signing can make an otherwise resolvable\n"""
new_resolve_success = """            guard url.startAccessingSecurityScopedResource() else {\n                result(\n                    FlutterError(\n                        code: \"ACCESS_DENIED\",\n                        message: \"startAccessingSecurityScopedResource returned false\",\n                        details: nil\n                    )\n                )\n                return\n            }\n            activeSecurityScopedURLs[key] = url\n\n            // Sideload updates/re-signing can make an otherwise resolvable\n"""
if old_resolve_success in swift:
    swift = swift.replace(old_resolve_success, new_resolve_success, 1)

old_clear = """    private func clearBookmark(key: String, result: @escaping FlutterResult) {\n        UserDefaults.standard.removeObject(forKey: Self.bookmarkDefaultsKey(for: key))\n        result(nil)\n    }\n"""
new_clear = """    private func clearBookmark(key: String, result: @escaping FlutterResult) {\n        if let active = activeSecurityScopedURLs.removeValue(forKey: key) {\n            active.stopAccessingSecurityScopedResource()\n        }\n        UserDefaults.standard.removeObject(forKey: Self.bookmarkDefaultsKey(for: key))\n        result(nil)\n    }\n"""
if old_clear in swift:
    swift = swift.replace(old_clear, new_clear, 1)

write(swift_path, swift)


# ---------------------------------------------------------------------------
# Fin: always resolve the bookmark before scanning and add title fallback.
# ---------------------------------------------------------------------------
fin_path = "lib/services/fin_library_service.dart"
fin = read(fin_path)

if "screenscraper_service.dart" not in fin:
    fin = replace_once(
        fin,
        "import 'package:neostation/services/logger_service.dart';\n",
        "import 'package:neostation/services/logger_service.dart';\n"
        "import 'package:neostation/services/screenscraper_service.dart';\n"
        "import 'package:path_provider/path_provider.dart';\n",
        "Fin ScreenScraper/debug imports",
    )

if "_gameCubeScreenScraperSystemId" not in fin:
    fin = replace_once(
        fin,
        "  static const String _virtualScheme = 'fin';\n",
        "  static const String _virtualScheme = 'fin';\n"
        "  static const String _gameCubeScreenScraperSystemId = '13';\n"
        "  static const String _wiiScreenScraperSystemId = '16';\n",
        "Fin ScreenScraper IDs",
    )

old_link = """    final normalized = await _normalizeGamesRoot(selected);\n    if (normalized == null) {\n      throw const FormatException(\n        'Select Fin/Games (or the Fin folder that contains Games).',\n      );\n    }\n\n    _linkedGamesPath = normalized;\n    return syncLinkedLibrary();\n"""
new_link = """    // The picker callback stores a bookmark. Resolve it once before scanning so\n    // the security-scoped grant is active while Dart enumerates Fin/Games.\n    final resolved = await ExternalFolderAccess.resolveBookmarkedFolder(\n      key: bookmarkKey,\n    );\n    final normalized = await _normalizeGamesRoot(resolved ?? selected);\n    if (normalized == null) {\n      await _writeDebugFile(\n        'STATE: INVALID_SELECTION\\nSelected: $selected\\nResolved: $resolved',\n      );\n      throw const FormatException(\n        'Select Fin/Games (or the Fin folder that contains Games).',\n      );\n    }\n\n    _linkedGamesPath = normalized;\n    return syncLinkedLibrary();\n"""
if old_link in fin:
    fin = fin.replace(old_link, new_link, 1)

old_sync_start = """  static Future<FinSyncResult> syncLinkedLibrary() async {\n    final root = await _resolveLinkedGamesRoot();\n    if (root == null) {\n      throw StateError('Fin Games folder is not linked.');\n    }\n\n    final discovery = await discoverLibrary(root);\n"""
new_sync_start = """  static Future<FinSyncResult> syncLinkedLibrary() async {\n    final root = await _resolveLinkedGamesRoot();\n    if (root == null) {\n      await _writeDebugFile('STATE: NO_LINKED_FOLDER');\n      throw StateError('Fin Games folder is not linked.');\n    }\n\n    await _writeDebugFile('STATE: SCANNING\\nGames root: $root');\n    final discovery = await discoverLibrary(root, allowTitleLookup: true);\n"""
if old_sync_start in fin:
    fin = fin.replace(old_sync_start, new_sync_start, 1)

old_log = """    _log.i(\n      'FinLibraryService: ${discovery.games.length} games '\n      '($gameCubeGames GameCube, $wiiGames Wii), '\n      '${discovery.skipped} unclassified, '\n      '${importResult.virtualRows} virtual rows, '\n      '${importResult.physicalRows} physical rows, '\n      '${importResult.removedRows} stale rows removed.',\n    );\n\n    return FinSyncResult(\n"""
new_log = """    _log.i(\n      'FinLibraryService: ${discovery.games.length} games '\n      '($gameCubeGames GameCube, $wiiGames Wii), '\n      '${discovery.skipped} unclassified, '\n      '${importResult.virtualRows} virtual rows, '\n      '${importResult.physicalRows} physical rows, '\n      '${importResult.removedRows} stale rows removed.',\n    );\n    await _writeDebugFile(\n      'STATE: IMPORTED\\nGames root: $root\\n'\n      'Detected: ${discovery.games.length}\\n'\n      'GameCube: $gameCubeGames\\nWii: $wiiGames\\n'\n      'Unclassified: ${discovery.skipped}\\n'\n      'Virtual rows: ${importResult.virtualRows}\\n'\n      'Physical rows: ${importResult.physicalRows}\\n'\n      'Removed rows: ${importResult.removedRows}\\n\\n'\n      '${discovery.games.map((game) => '${game.systemFolder} | ${game.gameId ?? '-'} | ${game.relativePath}').join('\\n')}',\n    );\n\n    return FinSyncResult(\n"""
if old_log in fin:
    fin = fin.replace(old_log, new_log, 1)

old_discover_sig = """  static Future<({List<FinLibraryGame> games, int skipped})> discoverLibrary(\n    String gamesRoot,\n  ) async {\n"""
new_discover_sig = """  static Future<({List<FinLibraryGame> games, int skipped})> discoverLibrary(\n    String gamesRoot, {\n    bool allowTitleLookup = false,\n  }) async {\n"""
if old_discover_sig in fin:
    fin = fin.replace(old_discover_sig, new_discover_sig, 1)

old_loop = """      final info = await detectDiscInfo(\n        entity,\n        visitedPlaylists: visitedPlaylists,\n      );\n      if (info == null) {\n        skipped++;\n        continue;\n      }\n\n      var relative = path.relative(entity.path, from: root.path);\n      relative = relative.replaceAll('\\\\', '/');\n      final fileName = path.basename(entity.path);\n      var title = path.basenameWithoutExtension(fileName);\n      if (title.toLowerCase().endsWith('.nkit')) {\n        title = title.substring(0, title.length - 5);\n      }\n\n      games.add(\n        FinLibraryGame(\n          fileName: fileName,\n          relativePath: relative,\n          systemFolder: info.systemFolder,\n          title: title,\n          gameId: info.gameId,\n        ),\n      );\n"""
new_loop = """      var relative = path.relative(entity.path, from: root.path);\n      relative = relative.replaceAll('\\\\', '/');\n      final fileName = path.basename(entity.path);\n      var title = path.basenameWithoutExtension(fileName);\n      if (title.toLowerCase().endsWith('.nkit')) {\n        title = title.substring(0, title.length - 5);\n      }\n\n      var info = await detectDiscInfo(\n        entity,\n        visitedPlaylists: visitedPlaylists,\n      );\n      if (info == null && allowTitleLookup) {\n        info = await _classifyByTitle(title, fileName: fileName);\n      }\n      if (info == null) {\n        skipped++;\n        continue;\n      }\n\n      games.add(\n        FinLibraryGame(\n          fileName: fileName,\n          relativePath: relative,\n          systemFolder: info.systemFolder,\n          title: title,\n          gameId: info.gameId,\n        ),\n      );\n"""
if old_loop in fin:
    fin = fin.replace(old_loop, new_loop, 1)

# Add Nintendo disc-ID prefix fallback for RVZ/WIA when disc_type is malformed.
old_rvz = """      final discType = data.getUint32(0x48, Endian.big);\n      final gameId = _readGameId(bytes, 0x58);\n      if (discType == 1) return (systemFolder: 'gc', gameId: gameId);\n      if (discType == 2) return (systemFolder: 'wii', gameId: gameId);\n"""
new_rvz = """      final discType = data.getUint32(0x48, Endian.big);\n      final gameId = _readGameId(bytes, 0x58);\n      if (discType == 1) return (systemFolder: 'gc', gameId: gameId);\n      if (discType == 2) return (systemFolder: 'wii', gameId: gameId);\n      final idHint = _systemFromNintendoGameId(gameId);\n      if (idHint != null) return (systemFolder: idHint, gameId: gameId);\n"""
if old_rvz in fin:
    fin = fin.replace(old_rvz, new_rvz, 1)

# Add classification helpers before _pathHint.
if "_classifyByTitle(" not in fin:
    helper_anchor = "  static ({String systemFolder, String? gameId})? _pathHint(String value) {\n"
    helpers = """  static String? _systemFromNintendoGameId(String? gameId) {\n    final value = gameId?.trim().toUpperCase() ?? '';\n    if (value.length != 6) return null;\n    // Retail GameCube discs overwhelmingly use G as the first character; Wii\n    // retail IDs commonly use R/S. This is only a fallback after disc_type and\n    // optical-disc magic, never the primary classifier.\n    if (value.startsWith('G')) return 'gc';\n    if (value.startsWith('R') || value.startsWith('S')) return 'wii';\n    return null;\n  }\n\n  static Future<({String systemFolder, String? gameId})?> _classifyByTitle(\n    String title, {\n    required String fileName,\n  }) async {\n    final pathHint = _pathHint('$title $fileName');\n    if (pathHint != null) return pathHint;\n\n    // Last-resort platform lookup. The same mixed Fin/Games folder can contain\n    // both consoles, so ask ScreenScraper whether this title exists on each\n    // platform. A title that exists on only one platform is safe to classify.\n    // Ports that exist on both remain unclassified rather than being guessed.\n    try {\n      final gc = await ScreenScraperService.fetchGameInfo(\n        _gameCubeScreenScraperSystemId,\n        fileName,\n        gameName: title,\n      );\n      final wii = await ScreenScraperService.fetchGameInfo(\n        _wiiScreenScraperSystemId,\n        fileName,\n        gameName: title,\n      );\n      final hasGc = gc?['gameInfo'] is Map;\n      final hasWii = wii?['gameInfo'] is Map;\n      if (hasGc && !hasWii) return (systemFolder: 'gc', gameId: null);\n      if (hasWii && !hasGc) return (systemFolder: 'wii', gameId: null);\n    } catch (error) {\n      _log.w('FinLibraryService: title platform lookup failed for $title: $error');\n    }\n    return null;\n  }\n\n"""
    fin = replace_once(fin, helper_anchor, helpers + helper_anchor, "Fin title classifier")

# Always re-resolve the security-scoped bookmark before a scan.
old_resolve = """  static Future<String?> _resolveLinkedGamesRoot() async {\n    final cached = linkedGamesPath;\n    if (cached != null) return cached;\n    if (!Platform.isIOS) return null;\n\n    try {\n      final selected = await ExternalFolderAccess.resolveBookmarkedFolder(\n        key: bookmarkKey,\n      );\n      if (selected == null) return null;\n      final normalized = await _normalizeGamesRoot(selected);\n      if (normalized != null) _linkedGamesPath = normalized;\n      return normalized;\n    } catch (error) {\n      _log.w('FinLibraryService: failed resolving bookmark: $error');\n      return null;\n    }\n  }\n"""
new_resolve = """  static Future<String?> _resolveLinkedGamesRoot() async {\n    if (!Platform.isIOS) return linkedGamesPath;\n\n    try {\n      final selected = await ExternalFolderAccess.resolveBookmarkedFolder(\n        key: bookmarkKey,\n      );\n      if (selected != null) {\n        final normalized = await _normalizeGamesRoot(selected);\n        if (normalized != null) {\n          _linkedGamesPath = normalized;\n          return normalized;\n        }\n      }\n    } catch (error) {\n      _log.w('FinLibraryService: failed resolving bookmark: $error');\n    }\n\n    // Keep a best-effort fallback for an already-active path in the same app\n    // session, but never prefer it over resolving the bookmark first.\n    return linkedGamesPath;\n  }\n"""
if old_resolve in fin:
    fin = fin.replace(old_resolve, new_resolve, 1)

if "static Future<void> _writeDebugFile(" not in fin:
    fin = replace_once(
        fin,
        "  static Future<void> loadCachedLibrary() async {\n",
        "  static Future<void> _writeDebugFile(String content) async {\n"
        "    try {\n"
        "      final docs = await getApplicationDocumentsDirectory();\n"
        "      final file = File(path.join(docs.path, 'fin_sync_debug.txt'));\n"
        "      await file.writeAsString(\n"
        "        '--- ${DateTime.now().toIso8601String()} ---\\n$content',\n"
        "      );\n"
        "    } catch (error) {\n"
        "      _log.w('FinLibraryService: could not write sync diagnostics: $error');\n"
        "    }\n"
        "  }\n\n"
        "  static Future<void> loadCachedLibrary() async {\n",
        "Fin debug writer",
    )

write(fin_path, fin)


# ---------------------------------------------------------------------------
# Manga Provider registry: accept the JSON directly from Library > Add file.
# ---------------------------------------------------------------------------
provider_path = "lib/services/library_metadata_provider_service.dart"
provider = read(provider_path)

if "package:shared_preferences/shared_preferences.dart" not in provider:
    provider = replace_once(
        provider,
        "import 'package:neostation/services/logger_service.dart';\n",
        "import 'package:neostation/services/logger_service.dart';\n"
        "import 'package:shared_preferences/shared_preferences.dart';\n",
        "provider SharedPreferences import",
    )

if "_importedRegistryPrefsKey" not in provider:
    provider = replace_once(
        provider,
        "  static const String manifestAsset = 'assets/data/manga-providers.json';\n",
        "  static const String manifestAsset = 'assets/data/manga-providers.json';\n"
        "  static const String _importedRegistryPrefsKey =\n"
        "      'neostation_library_metadata_provider_registry_v1';\n",
        "provider registry preference key",
    )

old_initialize = """  Future<void> initialize() async {\n    if (_initialized) return;\n    final raw = await rootBundle.loadString(manifestAsset);\n    final decoded = jsonDecode(raw);\n    if (decoded is! Map) {\n      throw const FormatException('Metadata provider registry is not an object.');\n    }\n    final manifest = Map<String, dynamic>.from(decoded);\n    if (manifest['schemaVersion'] != 1) {\n      throw FormatException(\n        'Unsupported metadata provider schema: ${manifest['schemaVersion']}',\n      );\n    }\n    if (manifest['contentPolicy']?.toString() != 'metadata-only') {\n      throw const FormatException(\n        'NeoStation metadata provider registry must remain metadata-only.',\n      );\n    }\n    final rawProviders = manifest['providers'];\n    if (rawProviders is! List) {\n      throw const FormatException('Metadata provider registry has no providers.');\n    }\n\n    final parsed = <LibraryMetadataProviderDefinition>[];\n    final ids = <String>{};\n    for (final rawProvider in rawProviders) {\n      if (rawProvider is! Map) continue;\n      final definition = LibraryMetadataProviderDefinition.fromJson(\n        Map<String, dynamic>.from(rawProvider),\n      );\n      if (definition.id.isEmpty || definition.name.isEmpty) continue;\n      if (!ids.add(definition.id)) {\n        throw FormatException('Duplicate metadata provider: ${definition.id}');\n      }\n      parsed.add(definition);\n    }\n    _providers = List<LibraryMetadataProviderDefinition>.unmodifiable(parsed);\n    _initialized = true;\n  }\n"""
new_initialize = """  Future<void> initialize() async {\n    if (_initialized) return;\n    final prefs = await SharedPreferences.getInstance();\n    final imported = prefs.getString(_importedRegistryPrefsKey);\n    final raw = imported?.trim().isNotEmpty == true\n        ? imported!\n        : await rootBundle.loadString(manifestAsset);\n    _providers = _parseRegistry(raw);\n    _initialized = true;\n  }\n\n  /// Imports the exact Manga Provider document format used by NeoStation.\n  /// Returns null when the selected JSON is not a provider registry, allowing\n  /// the normal add-on/repository installer to try the same file.\n  Future<int?> importRegistryJsonIfSupported(String rawJson) async {\n    dynamic decoded;\n    try {\n      decoded = jsonDecode(rawJson);\n    } catch (_) {\n      return null;\n    }\n    if (decoded is! Map) return null;\n    final object = Map<String, dynamic>.from(decoded);\n    if (!object.containsKey('schemaVersion') ||\n        !object.containsKey('contentPolicy') ||\n        !object.containsKey('providers')) {\n      return null;\n    }\n\n    final parsed = _parseRegistry(rawJson);\n    final prefs = await SharedPreferences.getInstance();\n    await prefs.setString(_importedRegistryPrefsKey, rawJson);\n    _providers = parsed;\n    _initialized = true;\n    return parsed.length;\n  }\n\n  static List<LibraryMetadataProviderDefinition> _parseRegistry(String raw) {\n    final decoded = jsonDecode(raw);\n    if (decoded is! Map) {\n      throw const FormatException('Metadata provider registry is not an object.');\n    }\n    final manifest = Map<String, dynamic>.from(decoded);\n    if (manifest['schemaVersion'] != 1) {\n      throw FormatException(\n        'Unsupported metadata provider schema: ${manifest['schemaVersion']}',\n      );\n    }\n    if (manifest['contentPolicy']?.toString() != 'metadata-only') {\n      throw const FormatException(\n        'NeoStation metadata provider registry must remain metadata-only.',\n      );\n    }\n    final rawProviders = manifest['providers'];\n    if (rawProviders is! List) {\n      throw const FormatException('Metadata provider registry has no providers.');\n    }\n\n    final parsed = <LibraryMetadataProviderDefinition>[];\n    final ids = <String>{};\n    for (final rawProvider in rawProviders) {\n      if (rawProvider is! Map) continue;\n      final definition = LibraryMetadataProviderDefinition.fromJson(\n        Map<String, dynamic>.from(rawProvider),\n      );\n      if (definition.id.isEmpty || definition.name.isEmpty) continue;\n      if (!ids.add(definition.id)) {\n        throw FormatException('Duplicate metadata provider: ${definition.id}');\n      }\n      parsed.add(definition);\n    }\n    if (parsed.isEmpty) {\n      throw const FormatException('Metadata provider registry contains no providers.');\n    }\n    return List<LibraryMetadataProviderDefinition>.unmodifiable(parsed);\n  }\n"""
if old_initialize in provider:
    provider = provider.replace(old_initialize, new_initialize, 1)

# Remove any stale Library video parameter left by earlier experiments.
provider = provider.replace("          videoUrls: const <String>[],\n", "")
provider = provider.replace("    return html_parser.parseFragment(text).text.trim();\n", "    return html_parser.parseFragment(text).text?.trim() ?? '';\n")
write(provider_path, provider)


# Intercept Manga Provider JSON before the regular manifest parser.
screen_path = "lib/screens/library_screen/library_screen.dart"
screen = read(screen_path)
old_install = """      final install = await _addonService.installDocumentFromJson(\n        utf8.decode(bytes),\n        origin: 'file:${picked.name}',\n      );\n      await _loadAddons();\n"""
new_install = """      final rawJson = utf8.decode(bytes);\n      final providerCount = await _metadataProviderService\n          .importRegistryJsonIfSupported(rawJson);\n      if (providerCount != null) {\n        if (!mounted) return;\n        setState(() {\n          _sourceFilter = 'all';\n          _librarySelectedIndex = 0;\n        });\n        final fr = Localizations.localeOf(context).languageCode == 'fr';\n        _showMessage(\n          fr\n              ? '$providerCount source(s) Manga Provider intégrée(s).'\n              : '$providerCount Manga Provider source(s) imported.',\n        );\n        if (_titleQuery.trim().isNotEmpty) {\n          unawaited(_runTitleSearch(_titleQuery));\n        }\n        return;\n      }\n\n      final install = await _addonService.installDocumentFromJson(\n        rawJson,\n        origin: 'file:${picked.name}',\n      );\n      await _loadAddons();\n"""
if old_install in screen:
    screen = screen.replace(old_install, new_install, 1)
write(screen_path, screen)


# Add regression tests for provider registry import parsing and title classifier basics.
test_path = "test/library_metadata_provider_service_test.dart"
test = read(test_path)
if "parses the bundled Manga Provider registry format" not in test:
    insert = """\n  test('parses the bundled Manga Provider registry format', () async {\n    const raw = '''{\n      \"schemaVersion\": 1,\n      \"name\": \"NeoStation Manga Metadata Providers\",\n      \"contentPolicy\": \"metadata-only\",\n      \"providers\": [\n        {\n          \"id\": \"jikan\",\n          \"name\": \"Jikan\",\n          \"kind\": \"manga_database\",\n          \"transport\": \"rest\",\n          \"baseURL\": \"https://api.jikan.moe/v4\"\n        }\n      ]\n    }''';\n\n    final count = await LibraryMetadataProviderService.instance\n        .importRegistryJsonIfSupported(raw);\n    expect(count, 1);\n    expect(LibraryMetadataProviderService.instance.providerLabels['jikan'], 'Jikan');\n  });\n"""
    test = test.replace("\n}\n", insert + "\n}\n")
write(test_path, test)

print("Applied Fin security-scope/classification and Manga Provider direct-import fixes.")
