from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


# The primary patch adds the _classifyByTitle call before adding its helper.
# Ensure the helper exists even when the guard saw the call-site first.
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
write(fin_path, fin)


# Make the provider import regression test deterministic under flutter_test.
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

print("Completed Fin classifier helper and deterministic Manga Provider import test.")
