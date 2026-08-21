from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found for {label}: {old[:180]!r}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Dart wrapper: expose a native bookmark-aware file enumerator.
# ---------------------------------------------------------------------------
wrapper_path = "packages/external_folder_access/lib/external_folder_access.dart"
wrapper = read(wrapper_path)

if "listBookmarkedFiles" not in wrapper:
    anchor = """  /// Forgets the folder linked under [key]. The next call to
  /// [resolveBookmarkedFolder] with the same key returns `null` until a new
  /// folder is picked via [pickAndBookmarkFolder]. Other keys are
  /// untouched.
"""
    method = """  /// Enumerates files directly on the native iOS side while the security-
  /// scoped bookmark is active. This avoids relying on Dart `Directory.list`
  /// for app-owned folders exposed through Files, which can resolve a picked
  /// path successfully yet still fail to enumerate its children.
  ///
  /// [extensions] are supplied without a leading dot. [subdirectory] is
  /// relative to the bookmarked root. A small prefix of every matching file
  /// can be returned so callers can identify container formats without copying
  /// the full ROM into NeoStation's sandbox.
  static Future<List<Map<String, dynamic>>?> listBookmarkedFiles({
    String key = defaultBookmarkKey,
    String? subdirectory,
    List<String> extensions = const <String>[],
    bool recursive = true,
    int prefixBytes = 0,
  }) async {
    if (!Platform.isIOS) return null;
    try {
      final raw = await _channel.invokeMethod<List<dynamic>>(
        'listBookmarkedFiles',
        <String, dynamic>{
          'key': key,
          if (subdirectory != null && subdirectory.trim().isNotEmpty)
            'subdirectory': subdirectory,
          'extensions': extensions,
          'recursive': recursive,
          'prefixBytes': prefixBytes,
        },
      );
      if (raw == null) return null;
      return raw
          .whereType<Map>()
          .map((entry) => Map<String, dynamic>.from(entry))
          .toList(growable: false);
    } on PlatformException {
      return null;
    }
  }

"""
    wrapper = replace_once(wrapper, anchor, method + anchor, "Dart native file enumerator")

write(wrapper_path, wrapper)


# ---------------------------------------------------------------------------
# Swift plugin: enumerate/read prefixes while the bookmarked scope is active.
# ---------------------------------------------------------------------------
swift_path = "packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift"
swift = read(swift_path)

if 'case "listBookmarkedFiles":' not in swift:
    swift = replace_once(
        swift,
        """        case "resolveBookmarkedFolder":
            resolveBookmarkedFolder(key: Self.bookmarkKey(from: call), result: result)
        case "clearBookmark":
""",
        """        case "resolveBookmarkedFolder":
            resolveBookmarkedFolder(key: Self.bookmarkKey(from: call), result: result)
        case "listBookmarkedFiles":
            listBookmarkedFiles(call: call, result: result)
        case "clearBookmark":
""",
        "Swift method-channel dispatch",
    )

if "private func listBookmarkedFiles(" not in swift:
    anchor = """    private func clearBookmark(key: String, result: @escaping FlutterResult) {
"""
    native = r'''    /// Resolves a bookmark for native file operations. Unlike the Dart side,
    /// this keeps the URL object that owns the active security scope, so listing
    /// children cannot lose access between path resolution and enumeration.
    private func bookmarkedURLForNativeAccess(key: String) throws -> URL? {
        if let active = activeSecurityScopedURLs[key] {
            return active
        }

        guard
            let bookmarkData = UserDefaults.standard.data(
                forKey: Self.bookmarkDefaultsKey(for: key)
            )
        else {
            return nil
        }

        var isStale = false
        let url = try URL(
            resolvingBookmarkData: bookmarkData,
            options: [],
            relativeTo: nil,
            bookmarkDataIsStale: &isStale
        )
        guard url.startAccessingSecurityScopedResource() else {
            throw NSError(
                domain: "ExternalFolderAccess",
                code: 1,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "startAccessingSecurityScopedResource returned false"
                ]
            )
        }
        activeSecurityScopedURLs[key] = url

        if isStale {
            if let refreshed = try? url.bookmarkData(
                options: [],
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            ) {
                UserDefaults.standard.set(
                    refreshed,
                    forKey: Self.bookmarkDefaultsKey(for: key)
                )
            }
        }
        return url
    }

    /// Lists files from a bookmarked folder without handing the traversal back
    /// to Dart. This is intentionally generic; Fin uses it for RVZ/WIA headers,
    /// but other iOS integrations can reuse it for Files-visible app folders.
    private func listBookmarkedFiles(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        let args = call.arguments as? [String: Any] ?? [:]
        let key = (args["key"] as? String).flatMap { $0.isEmpty ? nil : $0 }
            ?? Self.defaultBookmarkKey
        let recursive = (args["recursive"] as? Bool) ?? true
        let requestedPrefix = (args["prefixBytes"] as? NSNumber)?.intValue ?? 0
        let prefixBytes = min(max(requestedPrefix, 0), 4096)
        let extensions = Set(
            ((args["extensions"] as? [String]) ?? []).map {
                $0.lowercased().trimmingCharacters(
                    in: CharacterSet(charactersIn: ".")
                )
            }
        )

        do {
            guard let bookmarkedRoot = try bookmarkedURLForNativeAccess(key: key) else {
                result(nil)
                return
            }

            let canonicalBookmark = bookmarkedRoot.standardizedFileURL
            var root = canonicalBookmark
            if let rawSubdirectory = args["subdirectory"] as? String,
                !rawSubdirectory.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            {
                let subdirectory = rawSubdirectory
                    .replacingOccurrences(of: "\\", with: "/")
                    .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                let candidate = canonicalBookmark
                    .appendingPathComponent(subdirectory, isDirectory: true)
                    .standardizedFileURL
                let bookmarkPath = canonicalBookmark.path
                let candidatePath = candidate.path
                guard candidatePath == bookmarkPath ||
                    candidatePath.hasPrefix(bookmarkPath + "/")
                else {
                    result(
                        FlutterError(
                            code: "INVALID_SUBDIRECTORY",
                            message: "Subdirectory escapes bookmarked root",
                            details: nil
                        )
                    )
                    return
                }
                root = candidate
            }

            let manager = FileManager.default
            let resourceKeys: [URLResourceKey] = [.isRegularFileKey, .fileSizeKey]
            var urls: [URL] = []

            if recursive {
                guard let enumerator = manager.enumerator(
                    at: root,
                    includingPropertiesForKeys: resourceKeys,
                    options: [.skipsHiddenFiles],
                    errorHandler: { _, _ in true }
                ) else {
                    result([])
                    return
                }
                for case let url as URL in enumerator {
                    urls.append(url)
                }
            } else {
                urls = try manager.contentsOfDirectory(
                    at: root,
                    includingPropertiesForKeys: resourceKeys,
                    options: [.skipsHiddenFiles]
                )
            }

            var entries: [[String: Any]] = []
            let rootPath = root.standardizedFileURL.path
            for url in urls {
                let values = try? url.resourceValues(forKeys: Set(resourceKeys))
                guard values?.isRegularFile == true else { continue }

                let ext = url.pathExtension.lowercased()
                if !extensions.isEmpty && !extensions.contains(ext) { continue }

                let canonicalFile = url.standardizedFileURL
                let filePath = canonicalFile.path
                guard filePath.hasPrefix(rootPath) else { continue }

                var relative = String(filePath.dropFirst(rootPath.count))
                while relative.hasPrefix("/") { relative.removeFirst() }
                if relative.isEmpty { continue }

                var prefix = Data()
                if prefixBytes > 0,
                    let handle = try? FileHandle(forReadingFrom: canonicalFile)
                {
                    defer { try? handle.close() }
                    prefix = (try? handle.read(upToCount: prefixBytes)) ?? Data()
                }

                entries.append([
                    "relativePath": relative,
                    "fileName": canonicalFile.lastPathComponent,
                    "size": values?.fileSize ?? 0,
                    "prefix": FlutterStandardTypedData(bytes: prefix),
                ])
            }

            result(entries)
        } catch {
            result(
                FlutterError(
                    code: "LIST_BOOKMARKED_FILES_FAILED",
                    message: error.localizedDescription,
                    details: nil
                )
            )
        }
    }

'''
    swift = replace_once(swift, anchor, native + anchor, "Swift native bookmarked listing")

write(swift_path, swift)


# ---------------------------------------------------------------------------
# Fin service: use the native scan on iOS and force a full UI/database reload.
# ---------------------------------------------------------------------------
fin_path = "lib/services/fin_library_service.dart"
fin = read(fin_path)

# A Files picker URL can be perfectly valid on iOS even when Dart's synchronous
# Directory.existsSync() cannot traverse the provider-backed children.
old_getter = """  static String? get linkedGamesPath {
    final value = _linkedGamesPath;
    if (value == null || value.isEmpty) return null;
    return Directory(value).existsSync() ? value : null;
  }
"""
new_getter = """  static String? get linkedGamesPath {
    final value = _linkedGamesPath;
    if (value == null || value.isEmpty) return null;
    if (Platform.isIOS) return value;
    return Directory(value).existsSync() ? value : null;
  }
"""
if old_getter in fin:
    fin = fin.replace(old_getter, new_getter, 1)

# Startup reconciliation should use the same native scanner as manual sync.
old_startup = """        final discovery = await discoverLibrary(root);
        await _importIntoNeoStation(discovery.games);
"""
new_startup = """        final discovery =
            await _discoverLibraryNatively(root, allowTitleLookup: false) ??
            await discoverLibrary(root);
        await _importIntoNeoStation(discovery.games);
"""
if old_startup in fin:
    fin = fin.replace(old_startup, new_startup, 1)

# Manual sync: prefer native enumeration and record which route was used.
old_sync = """    await _writeDebugFile('STATE: SCANNING\\nGames root: $root');
    final discovery = await discoverLibrary(root, allowTitleLookup: true);
    final importResult = await _importIntoNeoStation(discovery.games);
"""
new_sync = """    await _writeDebugFile('STATE: SCANNING\\nGames root: $root');
    final nativeDiscovery = await _discoverLibraryNatively(
      root,
      allowTitleLookup: true,
    );
    final discovery =
        nativeDiscovery ?? await discoverLibrary(root, allowTitleLookup: true);
    final discoveryMode = nativeDiscovery == null ? 'dart' : 'native-ios';
    final importResult = await _importIntoNeoStation(discovery.games);
"""
if old_sync in fin:
    fin = fin.replace(old_sync, new_sync, 1)

old_debug = """      'STATE: IMPORTED\\nGames root: $root\\n'
      'Detected: ${discovery.games.length}\\n'
"""
new_debug = """      'STATE: IMPORTED\\nGames root: $root\\n'
      'Discovery mode: $discoveryMode\\n'
      'Detected: ${discovery.games.length}\\n'
"""
if old_debug in fin:
    fin = fin.replace(old_debug, new_debug, 1)

# Insert native discovery before the ordinary Dart scanner.
if "_discoverLibraryNatively(" not in fin:
    marker = """  /// Scans the linked Fin folder and classifies formats without relying on
"""
    native_discovery = r'''  /// iOS-native discovery path. The security-scoped bookmark stays owned
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
      final relative = entry['relativePath']?.toString().replaceAll('\\', '/') ?? '';
      final fileName = entry['fileName']?.toString() ?? path.basename(relative);
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
    fin = replace_once(fin, marker, native_discovery + marker, "Fin native discovery")

# Add a pure prefix classifier used by the native scan and unit tests.
if "detectDiscInfoFromPrefix(" not in fin:
    marker = """  /// Public only for deterministic unit tests and diagnostics.
  @visibleForTesting
  static Future<({String systemFolder, String? gameId})?> detectDiscInfo(
"""
    classifier = r'''  /// Classifies a game from the small prefix read by the native iOS
  /// bookmark scanner. RVZ/WIA stores disc_type and the raw optical-disc header
  /// in this prefix, so the full multi-gigabyte image never needs to be copied.
  @visibleForTesting
  static ({String systemFolder, String? gameId})? detectDiscInfoFromPrefix(
    Uint8List bytes, {
    required String extension,
    String pathHint = '',
  }) {
    final normalizedExtension = extension.toLowerCase();
    if (_gameCubeExtensions.contains(normalizedExtension)) {
      return (systemFolder: 'gc', gameId: null);
    }
    if (_wiiExtensions.contains(normalizedExtension)) {
      return (systemFolder: 'wii', gameId: null);
    }

    if (bytes.length >= 0x5e &&
        (_startsWith(bytes, const <int>[0x52, 0x56, 0x5a, 0x01]) ||
            _startsWith(bytes, const <int>[0x57, 0x49, 0x41, 0x01]))) {
      final data = ByteData.sublistView(bytes);
      final discType = data.getUint32(0x48, Endian.big);
      final gameId = _readGameId(bytes, 0x58);
      if (discType == 1) return (systemFolder: 'gc', gameId: gameId);
      if (discType == 2) return (systemFolder: 'wii', gameId: gameId);
      final idHint = _systemFromNintendoGameId(gameId);
      if (idHint != null) return (systemFolder: idHint, gameId: gameId);
    }

    if (bytes.length >= 0x20) {
      final data = ByteData.sublistView(bytes);
      final wiiMagic = data.getUint32(0x18, Endian.big);
      final gameCubeMagic = data.getUint32(0x1c, Endian.big);
      final gameId = _readGameId(bytes, 0);
      if (wiiMagic == 0x5d1c9ea3) {
        return (systemFolder: 'wii', gameId: gameId);
      }
      if (gameCubeMagic == 0xc2339f3d) {
        return (systemFolder: 'gc', gameId: gameId);
      }
    }

    return pathHint.isEmpty ? null : _pathHint(pathHint);
  }

'''
    fin = replace_once(fin, marker, classifier + marker, "Fin prefix classifier")

# Make detectDiscInfo delegate to the same classifier after reading the prefix.
old_classification = r'''    // Dolphin RVZ/WIA Header 1 is 0x48 bytes. Header 2 starts with a big-endian
    // disc_type: 1 = GameCube, 2 = Wii, followed by a 0x80-byte raw disc header.
    if (bytes.length >= 0x5e &&
        (_startsWith(bytes, const <int>[0x52, 0x56, 0x5a, 0x01]) ||
            _startsWith(bytes, const <int>[0x57, 0x49, 0x41, 0x01]))) {
      final data = ByteData.sublistView(bytes);
      final discType = data.getUint32(0x48, Endian.big);
      final gameId = _readGameId(bytes, 0x58);
      if (discType == 1) return (systemFolder: 'gc', gameId: gameId);
      if (discType == 2) return (systemFolder: 'wii', gameId: gameId);
      final idHint = _systemFromNintendoGameId(gameId);
      if (idHint != null) return (systemFolder: idHint, gameId: gameId);
    }

    // Standard optical-disc header magic used by Dolphin.
    if (bytes.length >= 0x20) {
      final data = ByteData.sublistView(bytes);
      final wiiMagic = data.getUint32(0x18, Endian.big);
      final gameCubeMagic = data.getUint32(0x1c, Endian.big);
      final gameId = _readGameId(bytes, 0);
      if (wiiMagic == 0x5d1c9ea3) {
        return (systemFolder: 'wii', gameId: gameId);
      }
      if (gameCubeMagic == 0xc2339f3d) {
        return (systemFolder: 'gc', gameId: gameId);
      }
    }

    return _pathHint(file.path);
'''
new_classification = r'''    return detectDiscInfoFromPrefix(
      bytes,
      extension: extension,
      pathHint: file.path,
    );
'''
if old_classification in fin:
    fin = fin.replace(old_classification, new_classification, 1)

# Ensure system definitions are synchronized before treating a missing lookup as fatal.
old_system_lookup = """    final gameCube = await SystemRepository.getSystemByFolderName('gc');
    final wii = await SystemRepository.getSystemByFolderName('wii');
    if (gameCube?.id == null || wii?.id == null) {
"""
new_system_lookup = """    var gameCube = await SystemRepository.getSystemByFolderName('gc');
    var wii = await SystemRepository.getSystemByFolderName('wii');
    if (gameCube?.id == null || wii?.id == null) {
      await SystemRepository.getAllSystems();
      gameCube = await SystemRepository.getSystemByFolderName('gc');
      wii = await SystemRepository.getSystemByFolderName('wii');
    }
    if (gameCube?.id == null || wii?.id == null) {
"""
if old_system_lookup in fin:
    fin = fin.replace(old_system_lookup, new_system_lookup, 1)

# A complete database reload is safer than refreshing two cache buckets when
# the import has just made previously-undetected systems visible.
old_refresh = """      await databaseProvider.loadGamesForSystem('gc');
      await databaseProvider.loadGamesForSystem('wii');
      await Provider.of<SqliteConfigProvider>(
        context,
        listen: false,
      ).refreshDetectedSystems();
"""
new_refresh = """      await Provider.of<SqliteConfigProvider>(
        context,
        listen: false,
      ).refreshDetectedSystems();
      await databaseProvider.loadDatabase();
"""
if old_refresh in fin:
    fin = fin.replace(old_refresh, new_refresh, 1)

# Do the same after startup restore.
fin = fin.replace(
    """        await databaseProvider.loadGamesForSystem('gc');
        await databaseProvider.loadGamesForSystem('wii');
        await configProvider.refreshDetectedSystems();
""",
    """        await configProvider.refreshDetectedSystems();
        await databaseProvider.loadDatabase();
""",
)
fin = fin.replace(
    """      await databaseProvider.loadGamesForSystem('gc');
      await databaseProvider.loadGamesForSystem('wii');
      await configProvider.refreshDetectedSystems();
""",
    """      await configProvider.refreshDetectedSystems();
      await databaseProvider.loadDatabase();
""",
)

# On iOS, accept a directly-picked Games folder by name before asking Dart to
# stat/list the provider-backed URL.
old_normalize = """  static Future<String?> _normalizeGamesRoot(String selected) async {
    final root = Directory(path.normalize(selected));
    if (!await root.exists()) return null;

    final base = path.basename(root.path).toLowerCase();
    if (base == 'games' || base == 'software') return root.path;
"""
new_normalize = """  static Future<String?> _normalizeGamesRoot(String selected) async {
    final normalizedPath = path.normalize(selected);
    final base = path.basename(normalizedPath).toLowerCase();
    if (base == 'games' || base == 'software') return normalizedPath;

    final root = Directory(normalizedPath);
    if (!await root.exists()) return null;
"""
if old_normalize in fin:
    fin = fin.replace(old_normalize, new_normalize, 1)

write(fin_path, fin)


# ---------------------------------------------------------------------------
# Regression test for the exact prefix path used by native iOS enumeration.
# ---------------------------------------------------------------------------
test_path = "test/fin_library_service_test.dart"
test = read(test_path)
if "classifies RVZ prefix returned by native iOS scan" not in test:
    marker = """  test('reads GameCube disc_type from RVZ header', () async {
"""
    test_block = """  test('classifies RVZ prefix returned by native iOS scan', () {
    final bytes = Uint8List(0x100);
    bytes.setRange(0, 4, const <int>[0x52, 0x56, 0x5a, 0x01]);
    ByteData.sublistView(bytes).setUint32(0x48, 2, Endian.big);
    bytes.setRange(0x58, 0x5e, 'RMCE01'.codeUnits);

    final info = FinLibraryService.detectDiscInfoFromPrefix(
      bytes,
      extension: '.rvz',
      pathHint: 'Mario Kart Wii (Europe).rvz',
    );
    expect(info?.systemFolder, 'wii');
    expect(info?.gameId, 'RMCE01');
  });

"""
    test = replace_once(test, marker, test_block + marker, "Fin native prefix test")
write(test_path, test)

print("Applied native iOS Fin library enumeration and full library refresh fix.")
