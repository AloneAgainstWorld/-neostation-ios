from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


fin_path = "lib/services/fin_library_service.dart"
fin = read(fin_path)

signature = (
    "  static Future<({List<FinLibraryGame> games, int skipped})?>\n"
    "  _discoverLibraryNatively(\n"
)

if signature not in fin:
    marker = "  /// Scans the linked Fin folder and classifies formats without relying on\n"
    if marker not in fin:
        raise RuntimeError("Fin native discovery insertion marker not found")

    method = r'''  /// iOS-native discovery path. The security-scoped bookmark stays owned
  /// by the Swift URL while it enumerates the Files-visible Fin directory and
  /// reads only the first 256 bytes of each candidate image. This avoids the
  /// provider-backed folder traversal failure that can occur after returning a
  /// path string to Dart.
  static Future<({List<FinLibraryGame> games, int skipped})?>
  _discoverLibraryNatively(
    String gamesRoot, {
    required bool allowTitleLookup,
  }) async {
    if (!Platform.isIOS) return null;

    final bookmarkedRoot = await ExternalFolderAccess.resolveBookmarkedFolder(
      key: bookmarkKey,
    );
    if (bookmarkedRoot == null || bookmarkedRoot.trim().isEmpty) return null;

    final bookmarkPath = path.normalize(bookmarkedRoot);
    final normalizedGamesRoot = path.normalize(gamesRoot);
    String? subdirectory;
    if (bookmarkPath != normalizedGamesRoot) {
      final relative = path
          .relative(normalizedGamesRoot, from: bookmarkPath)
          .replaceAll('\\', '/');
      if (relative != '.' &&
          relative.isNotEmpty &&
          relative != '..' &&
          !relative.startsWith('../')) {
        subdirectory = relative;
      }
    }

    final entries = await ExternalFolderAccess.listBookmarkedFiles(
      key: bookmarkKey,
      subdirectory: subdirectory,
      extensions: _supportedExtensions
          .map((extension) => extension.replaceFirst('.', ''))
          .toList(growable: false),
      recursive: true,
      prefixBytes: 0x100,
    );
    if (entries == null) return null;

    final games = <FinLibraryGame>[];
    var skipped = 0;
    for (final entry in entries) {
      final relative =
          entry['relativePath']?.toString().replaceAll('\\', '/') ?? '';
      final fileName =
          entry['fileName']?.toString() ?? path.basename(relative);
      if (relative.isEmpty || fileName.isEmpty) continue;

      final extension = path.extension(fileName).toLowerCase();
      if (!_supportedExtensions.contains(extension)) continue;

      final rawPrefix = entry['prefix'];
      final Uint8List prefix;
      if (rawPrefix is Uint8List) {
        prefix = rawPrefix;
      } else if (rawPrefix is List) {
        prefix = Uint8List.fromList(
          rawPrefix.whereType<num>().map((value) => value.toInt()).toList(),
        );
      } else {
        prefix = Uint8List(0);
      }

      var title = path.basenameWithoutExtension(fileName);
      if (title.toLowerCase().endsWith('.nkit')) {
        title = title.substring(0, title.length - 5);
      }

      var info = detectDiscInfoFromPrefix(
        prefix,
        extension: extension,
        pathHint: relative,
      );
      if (info == null && allowTitleLookup) {
        info = await _classifyByTitle(title, fileName: fileName);
      }
      if (info == null) {
        skipped++;
        continue;
      }

      games.add(
        FinLibraryGame(
          fileName: fileName,
          relativePath: relative,
          systemFolder: info.systemFolder,
          title: title,
          gameId: info.gameId,
        ),
      );
    }

    games.sort((a, b) {
      final systemCompare = a.systemFolder.compareTo(b.systemFolder);
      if (systemCompare != 0) return systemCompare;
      return a.title.toLowerCase().compareTo(b.title.toLowerCase());
    });
    return (games: List<FinLibraryGame>.unmodifiable(games), skipped: skipped);
  }

'''
    fin = fin.replace(marker, method + marker, 1)

write(fin_path, fin)
print("Completed native Fin discovery method insertion.")
