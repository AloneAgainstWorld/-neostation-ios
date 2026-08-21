from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# The primary patch adds the _classifyByTitle call before adding its helper.
# Ensure the helper exists even when the guard saw the call-site first.
# ---------------------------------------------------------------------------
fin_path = "lib/services/fin_library_service.dart"
fin = read(fin_path)
helper_signature = (
    "  static Future<({String systemFolder, String? gameId})?> _classifyByTitle(\n"
)
if helper_signature not in fin:
    anchor = "  static ({String systemFolder, String? gameId})? _pathHint(String value) {\n"
    if anchor not in fin:
        raise RuntimeError("Fin _pathHint anchor not found")
    helpers = """  static String? _systemFromNintendoGameId(String? gameId) {
    final value = gameId?.trim().toUpperCase() ?? '';
    if (value.length != 6) return null;
    // Fallback only. Primary classification remains the RVZ/WIA disc_type or
    // the optical-disc magic. Retail GameCube IDs overwhelmingly begin with G,
    // while Wii retail IDs commonly begin with R or S.
    if (value.startsWith('G')) return 'gc';
    if (value.startsWith('R') || value.startsWith('S')) return 'wii';
    return null;
  }

  static Future<({String systemFolder, String? gameId})?> _classifyByTitle(
    String title, {
    required String fileName,
  }) async {
    final pathHint = _pathHint('$title $fileName');
    if (pathHint != null) return pathHint;

    // Mixed Fin/Games folders are normal. Only use the title database as a
    // last resort when the disc itself could not be classified. If a title
    // exists on exactly one of GameCube/Wii, the platform is unambiguous. A
    // port that exists on both stays unclassified rather than being guessed.
    try {
      final gc = await ScreenScraperService.fetchGameInfo(
        _gameCubeScreenScraperSystemId,
        fileName,
        gameName: title,
      );
      final wii = await ScreenScraperService.fetchGameInfo(
        _wiiScreenScraperSystemId,
        fileName,
        gameName: title,
      );
      final hasGc = gc?['gameInfo'] is Map;
      final hasWii = wii?['gameInfo'] is Map;
      if (hasGc && !hasWii) return (systemFolder: 'gc', gameId: null);
      if (hasWii && !hasGc) return (systemFolder: 'wii', gameId: null);
    } catch (error) {
      _log.w('FinLibraryService: title platform lookup failed for $title: $error');
    }
    return null;
  }

"""
    fin = fin.replace(anchor, helpers + anchor, 1)

# The primary patch is intentionally usable on older branch snapshots. Once
# the generated source has already landed, its short RVZ anchor still matches
# the prefix of the upgraded block and could add the same idHint twice. Collapse
# any repeated fallback so CI can re-run the patch safely.
single_id_hint = """      final idHint = _systemFromNintendoGameId(gameId);
      if (idHint != null) return (systemFolder: idHint, gameId: gameId);
"""
double_id_hint = single_id_hint + single_id_hint
while double_id_hint in fin:
    fin = fin.replace(double_id_hint, single_id_hint, 1)

write(fin_path, fin)


# ---------------------------------------------------------------------------
# Manga Provider registry import. The first patch can add the preference key
# without replacing initialize() because dart format changed that exact block.
# Make this second stage structural rather than whitespace-sensitive.
# ---------------------------------------------------------------------------
provider_path = "lib/services/library_metadata_provider_service.dart"
provider = read(provider_path)

if "package:shared_preferences/shared_preferences.dart" not in provider:
    provider = provider.replace(
        "import 'package:neostation/services/logger_service.dart';\n",
        "import 'package:neostation/services/logger_service.dart';\n"
        "import 'package:shared_preferences/shared_preferences.dart';\n",
        1,
    )

if "_importedRegistryPrefsKey" not in provider:
    provider = provider.replace(
        "  static const String manifestAsset = 'assets/data/manga-providers.json';\n",
        "  static const String manifestAsset = 'assets/data/manga-providers.json';\n"
        "  static const String _importedRegistryPrefsKey =\n"
        "      'neostation_library_metadata_provider_registry_v1';\n",
        1,
    )

if "Future<int?> importRegistryJsonIfSupported" not in provider:
    init_start = provider.find("  Future<void> initialize() async {\n")
    search_marker = provider.find(
        "  /// Searches every requested provider with a small concurrency cap",
        init_start,
    )
    if init_start < 0 or search_marker < 0:
        raise RuntimeError("Could not locate metadata provider initialize block")

    replacement = """  Future<void> initialize() async {
    if (_initialized) return;
    final prefs = await SharedPreferences.getInstance();
    final imported = prefs.getString(_importedRegistryPrefsKey);
    final raw = imported?.trim().isNotEmpty == true
        ? imported!
        : await rootBundle.loadString(manifestAsset);
    _providers = _parseRegistry(raw);
    _initialized = true;
  }

  /// Imports NeoStation's Manga Provider registry directly from the Library
  /// file picker. Returns null for unrelated JSON so the normal add-on parser
  /// can continue handling NeoStation/Tachiyomi/Aidoku manifests.
  Future<int?> importRegistryJsonIfSupported(String rawJson) async {
    dynamic decoded;
    try {
      decoded = jsonDecode(rawJson);
    } catch (_) {
      return null;
    }
    if (decoded is! Map) return null;
    final object = Map<String, dynamic>.from(decoded);
    if (!object.containsKey('schemaVersion') ||
        !object.containsKey('contentPolicy') ||
        !object.containsKey('providers')) {
      return null;
    }

    final parsed = _parseRegistry(rawJson);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_importedRegistryPrefsKey, rawJson);
    _providers = parsed;
    _initialized = true;
    return parsed.length;
  }

  static List<LibraryMetadataProviderDefinition> _parseRegistry(String raw) {
    final decoded = jsonDecode(raw);
    if (decoded is! Map) {
      throw const FormatException(
        'Metadata provider registry is not an object.',
      );
    }
    final manifest = Map<String, dynamic>.from(decoded);
    if (manifest['schemaVersion'] != 1) {
      throw FormatException(
        'Unsupported metadata provider schema: ${manifest['schemaVersion']}',
      );
    }
    if (manifest['contentPolicy']?.toString() != 'metadata-only') {
      throw const FormatException(
        'NeoStation metadata provider registry must remain metadata-only.',
      );
    }
    final rawProviders = manifest['providers'];
    if (rawProviders is! List) {
      throw const FormatException(
        'Metadata provider registry has no providers.',
      );
    }

    final parsed = <LibraryMetadataProviderDefinition>[];
    final ids = <String>{};
    for (final rawProvider in rawProviders) {
      if (rawProvider is! Map) continue;
      final definition = LibraryMetadataProviderDefinition.fromJson(
        Map<String, dynamic>.from(rawProvider),
      );
      if (definition.id.isEmpty || definition.name.isEmpty) continue;
      if (!ids.add(definition.id)) {
        throw FormatException('Duplicate metadata provider: ${definition.id}');
      }
      parsed.add(definition);
    }
    if (parsed.isEmpty) {
      throw const FormatException(
        'Metadata provider registry contains no providers.',
      );
    }
    return List<LibraryMetadataProviderDefinition>.unmodifiable(parsed);
  }

"""
    provider = provider[:init_start] + replacement + provider[search_marker:]

# Remove compile leftovers from the abandoned video experiment.
provider = provider.replace("          videoUrls: const <String>[],\n", "")
provider = provider.replace(
    "    return html_parser.parseFragment(text).text.trim();\n",
    "    return html_parser.parseFragment(text).text?.trim() ?? '';\n",
)
write(provider_path, provider)


# ---------------------------------------------------------------------------
# Make the provider import regression test deterministic under flutter_test.
# ---------------------------------------------------------------------------
test_path = "test/library_metadata_provider_service_test.dart"
test = read(test_path)
if "package:shared_preferences/shared_preferences.dart" not in test:
    test = test.replace(
        "import 'package:neostation/services/library_metadata_provider_service.dart';\n",
        "import 'package:neostation/services/library_metadata_provider_service.dart';\n"
        "import 'package:shared_preferences/shared_preferences.dart';\n",
        1,
    )
if "SharedPreferences.setMockInitialValues(<String, Object>{});" not in test:
    marker = "  test('parses the bundled Manga Provider registry format', () async {\n"
    if marker in test:
        test = test.replace(
            marker,
            marker + "    SharedPreferences.setMockInitialValues(<String, Object>{});\n",
            1,
        )
write(test_path, test)

print("Completed Fin classifier helper and Manga Provider direct-import support.")
