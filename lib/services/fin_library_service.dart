import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/main.dart' show rootNavigatorKey;
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/sqlite_database_provider.dart';
import 'package:neostation/repositories/system_repository.dart';
import 'package:neostation/services/ios_shortcut_jit_launch_service.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as path;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

/// One discovered game in Fin's exposed `Games` folder.
class FinGameEntry {
  const FinGameEntry({
    required this.filePath,
    required this.fileName,
    required this.systemFolder,
    required this.title,
    required this.gameId,
  });

  final String filePath;
  final String fileName;
  final String systemFolder;
  final String title;
  final String? gameId;
}

/// Summary of the most recent Fin -> NeoStation library synchronization.
class FinLibrarySyncResult {
  const FinLibrarySyncResult({
    required this.discoveredGames,
    required this.importedGames,
    required this.gameCubeGames,
    required this.wiiGames,
    required this.unresolvedGames,
    required this.removedRows,
  });

  final int discoveredGames;
  final int importedGames;
  final int gameCubeGames;
  final int wiiGames;
  final int unresolvedGames;
  final int removedRows;

  Map<String, dynamic> toJson() => {
    'discoveredGames': discoveredGames,
    'importedGames': importedGames,
    'gameCubeGames': gameCubeGames,
    'wiiGames': wiiGames,
    'unresolvedGames': unresolvedGames,
    'removedRows': removedRows,
  };

  factory FinLibrarySyncResult.fromJson(Map<String, dynamic> json) {
    int number(String key) => int.tryParse('${json[key] ?? 0}') ?? 0;
    return FinLibrarySyncResult(
      discoveredGames: number('discoveredGames'),
      importedGames: number('importedGames'),
      gameCubeGames: number('gameCubeGames'),
      wiiGames: number('wiiGames'),
      unresolvedGames: number('unresolvedGames'),
      removedRows: number('removedRows'),
    );
  }
}

/// Integrates the App Store Fin emulator with NeoStation's existing GameCube
/// and Wii catalogues.
///
/// Fin exposes its Documents folder in Files. NeoStation bookmarks either the
/// `Fin/Games` folder itself or the Fin root containing a `Games` child, then
/// scans that folder directly without adding it to the generic ROM-folder
/// scanner. Keeping this import dedicated is important because GameCube and
/// Wii share many file extensions, including RVZ.
///
/// RVZ/WIA classification is deterministic and cheap: Dolphin stores a
/// `disc_type` field plus the first 0x80 bytes of the original disc header in
/// WIA header 2, outside the compressed game data. `disc_type == 1` is
/// GameCube and `disc_type == 2` is Wii. ISO/GCM files are classified from
/// their standard disc magic values. Formats that cannot be identified safely
/// are counted as unresolved instead of being guessed from the filename.
class FinLibraryService {
  FinLibraryService._();

  static final _log = LoggerService.instance;

  static const String bookmarkKey = 'fin-games';
  static const String finShortcutName = 'NeoStation+Fin';
  static const String _prefsKey = 'fin_library_sync_v1';

  static const String _gameCubeEmulatorId = 'gc.ios.fin';
  static const String _wiiEmulatorId = 'wii.ios.fin';

  static const Set<String> _candidateExtensions = {
    '.ciso',
    '.dol',
    '.elf',
    '.gcm',
    '.gcz',
    '.iso',
    '.rvz',
    '.tgc',
    '.wad',
    '.wbfs',
    '.wia',
  };

  static bool _initialized = false;
  static String? _gamesFolderPath;
  static FinLibrarySyncResult? _lastSync;

  static bool get isLinked => _gamesFolderPath != null;
  static String? get linkedGamesFolderPath => _gamesFolderPath;
  static bool get hasSyncedLibrary => _lastSync != null;
  static FinLibrarySyncResult? get lastSync => _lastSync;
  static int get syncedGameCount => _lastSync?.importedGames ?? 0;

  /// Restores the security-scoped folder bookmark and the last sync summary.
  /// Safe to call repeatedly and lazily from the settings card or launch path.
  static Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;

    if (Platform.isIOS) {
      try {
        final bookmarked = await ExternalFolderAccess.resolveBookmarkedFolder(
          key: bookmarkKey,
        );
        if (bookmarked != null) {
          _gamesFolderPath = await _resolveGamesFolder(bookmarked);
        }
      } catch (e) {
        _log.w('FinLibraryService: could not restore Games bookmark: $e');
      }
    }

    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_prefsKey);
      if (raw != null) {
        final decoded = jsonDecode(raw);
        if (decoded is Map) {
          _lastSync = FinLibrarySyncResult.fromJson(
            Map<String, dynamic>.from(decoded),
          );
        }
      }
    } catch (e) {
      _log.w('FinLibraryService: could not restore sync summary: $e');
    }
  }

  /// Opens the iOS folder picker, bookmarks the selected Fin location, and
  /// immediately imports every safely-identifiable GameCube/Wii title.
  ///
  /// The user may select either `Fin/Games` or the Fin root containing it.
  static Future<FinLibrarySyncResult?> linkAndSync() async {
    if (!Platform.isIOS) return null;
    await initialize();

    final selected = await ExternalFolderAccess.pickAndBookmarkFolder(
      key: bookmarkKey,
    );
    if (selected == null) return null;

    final gamesFolder = await _resolveGamesFolder(selected);
    if (gamesFolder == null) {
      await ExternalFolderAccess.clearBookmark(key: bookmarkKey);
      throw const FormatException(
        'Select the Fin/Games folder, or the Fin folder that contains Games.',
      );
    }

    _gamesFolderPath = gamesFolder;
    return syncLinkedLibrary();
  }

  /// Re-scans the currently linked Fin library and refreshes NeoStation's
  /// native GameCube and Wii catalogue rows.
  static Future<FinLibrarySyncResult> syncLinkedLibrary() async {
    await initialize();

    final root = _gamesFolderPath;
    if (root == null || !await Directory(root).exists()) {
      throw StateError('Fin Games folder is not linked.');
    }

    final candidates = <File>[];
    await for (final entity in Directory(root).list(
      recursive: true,
      followLinks: false,
    )) {
      if (entity is! File) continue;
      final extension = path.extension(entity.path).toLowerCase();
      if (_candidateExtensions.contains(extension)) {
        candidates.add(entity);
      }
    }

    final games = <FinGameEntry>[];
    var unresolved = 0;
    for (final file in candidates) {
      try {
        final entry = await inspectGameFile(file.path);
        if (entry == null) {
          unresolved++;
        } else {
          games.add(entry);
        }
      } catch (e) {
        unresolved++;
        _log.w('FinLibraryService: could not inspect ${file.path}: $e');
      }
    }

    final gcSystem = await SystemRepository.getSystemByFolderName('gc');
    final wiiSystem = await SystemRepository.getSystemByFolderName('wii');
    if (gcSystem?.id == null || wiiSystem?.id == null) {
      throw StateError('NeoStation GameCube/Wii system definitions are missing.');
    }

    final desiredPaths = games.map((game) => game.filePath).toSet();
    final db = await SqliteService.getDatabase();

    await db.transaction((txn) async {
      for (final game in games) {
        final isWii = game.systemFolder == 'wii';
        final systemId = isWii ? wiiSystem!.id! : gcSystem!.id!;
        final emulatorId = isWii
            ? _wiiEmulatorId
            : _gameCubeEmulatorId;

        await txn.rawInsert(
          '''
          INSERT INTO user_roms
            (app_system_id, app_emulator_unique_id, app_emulator_os_id,
             filename, rom_path, title_id, title_name, created_at, updated_at)
          VALUES (?, ?, NULL, ?, ?, ?, ?, datetime('now'), datetime('now'))
          ON CONFLICT(rom_path) DO UPDATE SET
            app_system_id = excluded.app_system_id,
            app_emulator_unique_id = excluded.app_emulator_unique_id,
            filename = excluded.filename,
            title_id = CASE
              WHEN excluded.title_id IS NOT NULL AND excluded.title_id != ''
              THEN excluded.title_id ELSE user_roms.title_id END,
            title_name = CASE
              WHEN excluded.title_name IS NOT NULL AND excluded.title_name != ''
              THEN excluded.title_name ELSE user_roms.title_name END,
            updated_at = datetime('now')
          ''',
          [
            systemId,
            emulatorId,
            game.fileName,
            game.filePath,
            game.gameId,
            game.title,
          ],
        );
      }
    });

    final existingFinRows = await db.rawQuery(
      '''
      SELECT rom_path FROM user_roms
      WHERE app_emulator_unique_id IN (?, ?)
      ''',
      [_gameCubeEmulatorId, _wiiEmulatorId],
    );
    final stalePaths = existingFinRows
        .map((row) => row['rom_path']?.toString() ?? '')
        .where(
          (romPath) =>
              romPath.isNotEmpty && !desiredPaths.contains(romPath),
        )
        .toList();

    var removedRows = 0;
    if (stalePaths.isNotEmpty) {
      await db.transaction((txn) async {
        const batchSize = 100;
        for (var i = 0; i < stalePaths.length; i += batchSize) {
          final end = (i + batchSize < stalePaths.length)
              ? i + batchSize
              : stalePaths.length;
          final batch = stalePaths.sublist(i, end);
          final placeholders = List.filled(batch.length, '?').join(',');
          removedRows += await txn.rawDelete(
            'DELETE FROM user_roms WHERE rom_path IN ($placeholders) '
            'AND app_emulator_unique_id IN (?, ?)',
            [...batch, _gameCubeEmulatorId, _wiiEmulatorId],
          );
        }
      });
    }

    final gcCount = games.where((game) => game.systemFolder == 'gc').length;
    final wiiCount = games.where((game) => game.systemFolder == 'wii').length;

    await _refreshDetectedSystem(
      db: db,
      systemId: gcSystem!.id!,
      folderName: 'gc',
    );
    await _refreshDetectedSystem(
      db: db,
      systemId: wiiSystem!.id!,
      folderName: 'wii',
    );

    final result = FinLibrarySyncResult(
      discoveredGames: candidates.length,
      importedGames: games.length,
      gameCubeGames: gcCount,
      wiiGames: wiiCount,
      unresolvedGames: unresolved,
      removedRows: removedRows,
    );
    _lastSync = result;
    await _persistSummary(result);
    await _refreshNeoStationUi();

    _log.i(
      'FinLibraryService: ${result.importedGames}/${result.discoveredGames} '
      'games imported (${result.gameCubeGames} GC, ${result.wiiGames} Wii, '
      '${result.unresolvedGames} unresolved, ${result.removedRows} removed)',
    );

    return result;
  }

  /// Reads only the small uncompressed container/disc header needed to
  /// distinguish GameCube from Wii and obtain a stable disc ID/title.
  static Future<FinGameEntry?> inspectGameFile(String filePath) async {
    final file = File(filePath);
    if (!await file.exists()) return null;

    final extension = path.extension(filePath).toLowerCase();
    final fileName = path.basename(filePath);

    if (extension == '.rvz' || extension == '.wia') {
      final bytes = await _readPrefix(file, 0xd8);
      if (bytes.length < 0xd8) return null;

      final expectedMagic = extension == '.rvz'
          ? const [0x52, 0x56, 0x5a, 0x01]
          : const [0x57, 0x49, 0x41, 0x01];
      if (!_startsWith(bytes, expectedMagic)) return null;

      final data = ByteData.sublistView(bytes);
      final discType = data.getUint32(0x48, Endian.big);
      final systemFolder = switch (discType) {
        1 => 'gc',
        2 => 'wii',
        _ => null,
      };
      if (systemFolder == null) return null;

      const discHeaderOffset = 0x58;
      final gameId = _readAscii(bytes, discHeaderOffset, 6);
      final title = _readAscii(bytes, discHeaderOffset + 0x20, 0x60);

      return FinGameEntry(
        filePath: filePath,
        fileName: fileName,
        systemFolder: systemFolder,
        title: title.isEmpty ? path.basenameWithoutExtension(fileName) : title,
        gameId: gameId.isEmpty ? null : gameId,
      );
    }

    if (extension == '.iso' || extension == '.gcm') {
      final bytes = await _readPrefix(file, 0x80);
      if (bytes.length < 0x20) return null;
      final data = ByteData.sublistView(bytes);
      final wiiMagic = data.getUint32(0x18, Endian.big);
      final gameCubeMagic = data.getUint32(0x1c, Endian.big);
      final systemFolder = wiiMagic == 0x5d1c9ea3
          ? 'wii'
          : gameCubeMagic == 0xc2339f3d
          ? 'gc'
          : null;
      if (systemFolder == null) return null;

      final gameId = _readAscii(bytes, 0, 6);
      final title = bytes.length > 0x20
          ? _readAscii(bytes, 0x20, bytes.length - 0x20)
          : '';
      return FinGameEntry(
        filePath: filePath,
        fileName: fileName,
        systemFolder: systemFolder,
        title: title.isEmpty ? path.basenameWithoutExtension(fileName) : title,
        gameId: gameId.isEmpty ? null : gameId,
      );
    }

    // TGC is a GameCube container; WAD is a Wii title package. These formats
    // do not need filename heuristics to determine the platform. Title/ID
    // enrichment can be added later if needed.
    if (extension == '.tgc' || extension == '.wad') {
      return FinGameEntry(
        filePath: filePath,
        fileName: fileName,
        systemFolder: extension == '.tgc' ? 'gc' : 'wii',
        title: path.basenameWithoutExtension(fileName),
        gameId: null,
      );
    }

    return null;
  }

  /// Returns the text input NeoStation sends to the `NeoStation+Fin`
  /// Shortcut. The Shortcut only needs a path relative to Fin/Games, never a
  /// volatile absolute iOS sandbox path.
  static Future<String?> shortcutInputForPath(String romPath) async {
    await initialize();
    final root = _gamesFolderPath;
    if (root == null) return null;

    final normalizedRoot = path.normalize(root);
    final normalizedRom = path.normalize(romPath);
    if (normalizedRom != normalizedRoot &&
        !path.isWithin(normalizedRoot, normalizedRom)) {
      return null;
    }

    final relative = path.relative(normalizedRom, from: normalizedRoot);
    if (relative == '.' || relative.startsWith('..')) return null;
    return relative.replaceAll('\\', '/');
  }

  /// Launch groundwork used once the user-created Shortcut is configured.
  static Future<bool> launchGameByRomPath(String romPath) async {
    final input = await shortcutInputForPath(romPath);
    if (input == null || input.isEmpty) return false;
    return IosShortcutJitLaunchService.run(
      shortcutName: finShortcutName,
      input: input,
    );
  }

  /// Opens Shortcuts at the create-shortcut screen. We intentionally do not
  /// ship an iCloud installer URL yet: the exact Fin action/input contract will
  /// be built and verified together before it is shared from NeoStation.
  static Future<bool> openShortcutSetup() async {
    if (!Platform.isIOS) return false;
    try {
      return await launchUrl(
        Uri.parse('shortcuts://create-shortcut'),
        mode: LaunchMode.externalApplication,
      );
    } catch (e) {
      _log.e('FinLibraryService: failed to open Shortcut setup: $e');
      return false;
    }
  }

  static Future<String?> _resolveGamesFolder(String selectedPath) async {
    final selected = Directory(selectedPath);
    if (!await selected.exists()) return null;

    if (path.basename(path.normalize(selectedPath)).toLowerCase() == 'games') {
      return path.normalize(selectedPath);
    }

    try {
      await for (final entity in selected.list(followLinks: false)) {
        if (entity is Directory &&
            path.basename(entity.path).toLowerCase() == 'games') {
          return path.normalize(entity.path);
        }
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  static Future<Uint8List> _readPrefix(File file, int length) async {
    final handle = await file.open(mode: FileMode.read);
    try {
      return Uint8List.fromList(await handle.read(length));
    } finally {
      await handle.close();
    }
  }

  static bool _startsWith(Uint8List bytes, List<int> expected) {
    if (bytes.length < expected.length) return false;
    for (var i = 0; i < expected.length; i++) {
      if (bytes[i] != expected[i]) return false;
    }
    return true;
  }

  static String _readAscii(Uint8List bytes, int offset, int length) {
    if (offset >= bytes.length || length <= 0) return '';
    final end = (offset + length < bytes.length)
        ? offset + length
        : bytes.length;
    final slice = bytes.sublist(offset, end);
    final zero = slice.indexOf(0);
    final content = zero >= 0 ? slice.sublist(0, zero) : slice;
    return latin1.decode(content, allowInvalid: true).trim();
  }

  static Future<void> _refreshDetectedSystem({
    required dynamic db,
    required int systemId,
    required String folderName,
  }) async {
    final rows = await db.rawQuery(
      'SELECT COUNT(*) AS count FROM user_roms WHERE app_system_id = ?',
      [systemId],
    );
    final count = int.tryParse('${rows.first['count'] ?? 0}') ?? 0;
    if (count > 0) {
      await SystemRepository.addDetectedSystem(systemId, folderName);
    } else {
      await SystemRepository.removeDetectedSystem(systemId);
    }
  }

  static Future<void> _persistSummary(FinLibrarySyncResult result) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefsKey, jsonEncode(result.toJson()));
    } catch (e) {
      _log.w('FinLibraryService: could not persist sync summary: $e');
    }
  }

  static Future<void> _refreshNeoStationUi() async {
    try {
      final context = rootNavigatorKey.currentContext;
      if (context == null) return;
      await Provider.of<SqliteDatabaseProvider>(
        context,
        listen: false,
      ).loadGamesForSystem('gc');
      await Provider.of<SqliteDatabaseProvider>(
        context,
        listen: false,
      ).loadGamesForSystem('wii');
      await Provider.of<SqliteConfigProvider>(
        context,
        listen: false,
      ).refreshDetectedSystems();
    } catch (e) {
      _log.w('FinLibraryService: UI refresh failed: $e');
    }
  }
}
