import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/main.dart' show rootNavigatorKey;
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/sqlite_database_provider.dart';
import 'package:neostation/repositories/system_repository.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// iOS integration for iFly V1.
///
/// The current iFly V1 IPA does not register a custom URL scheme and does not
/// expose a frontend/library-export callback. It *does* expose its Documents
/// library to Files and keeps imported games in a ROMs folder. NeoStation
/// therefore links that ROMs folder with a security-scoped bookmark and imports
/// its contents directly into the Dreamcast catalogue.
///
/// Launching currently uses iOS' native "Open In" document hand-off. iFly V1
/// declares itself as an owner/viewer for Dreamcast ROM document types, so it
/// can be selected without copying the library into NeoStation. If iFly adds a
/// launch URL scheme later, only [launchGameByRomPath] needs to change.
class IflyLibraryService {
  IflyLibraryService._();

  static final _log = LoggerService.instance;

  static const String bookmarkKey = 'ifly';
  static const String _prefsPathsKey = 'ifly_library_paths_v1';

  static String? _linkedFolderPath;
  static Set<String> _syncedPaths = <String>{};
  static int _lastSyncedCount = 0;

  /// Extensions advertised by iFly V1 plus NeoStation's Dreamcast formats.
  /// `.bin` is treated specially below to avoid importing every track beside a
  /// `.gdi`/`.cue` descriptor as a separate game.
  static const Set<String> _supportedExtensions = {
    'iso',
    'cdi',
    'gdi',
    'chd',
    'cue',
    'bin',
    'elf',
    'zip',
    '7z',
    'dat',
    'lst',
    'm3u',
  };

  static String? get linkedFolderPath => _linkedFolderPath;
  static bool get hasLinkedFolder =>
      _linkedFolderPath != null && _linkedFolderPath!.trim().isNotEmpty;
  static bool get hasSyncedLibrary => _syncedPaths.isNotEmpty;
  static int get lastSyncedCount => _lastSyncedCount;

  /// Restores the security-scoped iFly ROMs folder and the set of paths that
  /// were imported by the previous sync.
  static Future<void> loadCachedLibrary() async {
    try {
      _linkedFolderPath = await ExternalFolderAccess.resolveBookmarkedFolder(
        key: bookmarkKey,
      );

      final prefs = await SharedPreferences.getInstance();
      final cached = prefs.getStringList(_prefsPathsKey) ?? const <String>[];
      _syncedPaths = cached.map(_normalizePath).toSet();
      _lastSyncedCount = _syncedPaths.length;
    } catch (e) {
      _log.e('IflyLibraryService: failed loading cached library: $e');
      _syncedPaths = <String>{};
      _lastSyncedCount = 0;
    }
  }

  /// Re-resolves the native bookmark. Useful after returning to Settings.
  static Future<String?> refreshLinkedFolder() async {
    try {
      _linkedFolderPath = await ExternalFolderAccess.resolveBookmarkedFolder(
        key: bookmarkKey,
      );
    } catch (e) {
      _log.e('IflyLibraryService: failed resolving iFly bookmark: $e');
      _linkedFolderPath = null;
    }
    return _linkedFolderPath;
  }

  /// Called immediately after the user picks iFly's ROMs folder.
  static void setLinkedFolderPath(String folderPath) {
    _linkedFolderPath = folderPath;
  }

  /// Scans the linked iFly ROMs folder and imports it directly into NeoStation's
  /// Dreamcast database, without adding the folder to the normal NeoStation ROM
  /// roots and without requiring a `dc/` subfolder.
  static Future<IflySyncResult> syncLibrary() async {
    final root = await refreshLinkedFolder();
    if (root == null || root.isEmpty) {
      await _writeDebugFile(
        'ifly_sync_debug.txt',
        'STATE: ERROR\nNo iFly folder is linked. Link iFly/ROMs first.',
      );
      return const IflySyncResult.failure('No iFly ROMs folder is linked.');
    }

    final directory = Directory(root);
    if (!await directory.exists()) {
      await _writeDebugFile(
        'ifly_sync_debug.txt',
        'STATE: ERROR\nLinked folder does not exist: $root',
      );
      return const IflySyncResult.failure('The linked iFly folder is unavailable.');
    }

    await _writeDebugFile(
      'ifly_sync_debug.txt',
      'STATE: SCANNING\nFolder: $root',
    );

    try {
      final candidates = <File>[];
      await for (final entity in directory.list(
        recursive: true,
        followLinks: false,
      )) {
        if (entity is! File) continue;
        final name = path.basename(entity.path);
        if (name.startsWith('.')) continue;

        final ext = path.extension(name).replaceFirst('.', '').toLowerCase();
        if (!_supportedExtensions.contains(ext)) continue;
        if (_isKnownBiosFile(name)) continue;
        candidates.add(entity);
      }

      // Track descriptors by directory. A Dreamcast GDI/CUE dump commonly has
      // multiple .bin track files; importing each one would create duplicates.
      final descriptorDirs = <String>{};
      for (final file in candidates) {
        final ext = path.extension(file.path).toLowerCase();
        if (ext == '.gdi' || ext == '.cue') {
          descriptorDirs.add(_normalizePath(path.dirname(file.path)));
        }
      }

      final files = <File>[];
      var skippedTrackBins = 0;
      for (final file in candidates) {
        final ext = path.extension(file.path).toLowerCase();
        if (ext == '.bin' &&
            descriptorDirs.contains(_normalizePath(path.dirname(file.path)))) {
          skippedTrackBins++;
          continue;
        }
        files.add(file);
      }
      files.sort((a, b) => a.path.toLowerCase().compareTo(b.path.toLowerCase()));

      final result = await _importIntoNeoStation(files);
      _lastSyncedCount = _syncedPaths.length;

      await _writeDebugFile(
        'ifly_sync_debug.txt',
        'STATE: IMPORTED\n'
            'Folder: $root\n'
            'Supported files found: ${files.length}\n'
            'Track .bin files skipped: $skippedTrackBins\n'
            'New/updated iFly rows: ${result.importedRows}\n'
            'Stale iFly rows removed: ${result.removedRows}\n'
            'Dreamcast rows now in NeoStation: ${result.totalDreamcastRows}\n\n'
            'Imported paths:\n${files.map((f) => f.path).join('\n')}',
      );

      await _refreshNeoStationUi();
      return IflySyncResult.success(
        importedRows: result.importedRows,
        removedRows: result.removedRows,
        totalDreamcastRows: result.totalDreamcastRows,
      );
    } catch (e, stack) {
      _log.e('IflyLibraryService: sync failed: $e');
      await _writeDebugFile(
        'ifly_sync_debug.txt',
        'STATE: ERROR\nFolder: $root\nError: $e\nStack: $stack',
      );
      return IflySyncResult.failure(e.toString());
    }
  }

  static Future<({int importedRows, int removedRows, int totalDreamcastRows})>
      _importIntoNeoStation(List<File> files) async {
    final dreamcast = await SystemRepository.getSystemByFolderName('dc');
    if (dreamcast?.id == null) {
      throw StateError('NeoStation Dreamcast system definition was not found');
    }

    final db = await SqliteService.getDatabase();
    final desiredPaths = files.map((file) => _normalizePath(file.path)).toSet();
    var importedRows = 0;

    await db.transaction((txn) async {
      for (final file in files) {
        final fileName = path.basename(file.path);
        final titleName = _displayTitle(fileName);

        await txn.rawInsert(
          '''
          INSERT INTO user_roms
            (app_system_id, app_emulator_unique_id, app_emulator_os_id,
             filename, rom_path, title_name, created_at, updated_at)
          VALUES (?, NULL, NULL, ?, ?, ?, datetime('now'), datetime('now'))
          ON CONFLICT(rom_path) DO UPDATE SET
            app_system_id = excluded.app_system_id,
            filename = excluded.filename,
            title_name = CASE
              WHEN user_roms.title_name IS NULL OR user_roms.title_name = ''
              THEN excluded.title_name ELSE user_roms.title_name END,
            updated_at = datetime('now')
          ''',
          [dreamcast!.id!, fileName, file.path, titleName],
        );
        importedRows++;
      }
    });

    // Only remove paths that *this service* imported on a previous sync. This
    // deliberately leaves normal NeoStation/RetroArch Dreamcast rows alone.
    final stalePaths = _syncedPaths.difference(desiredPaths).toList();
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
            'DELETE FROM user_roms WHERE app_system_id = ? '
            'AND lower(rom_path) IN ($placeholders)',
            [dreamcast!.id!, ...batch],
          );
        }
      });
    }

    _syncedPaths = desiredPaths;
    final prefs = await SharedPreferences.getInstance();
    final persisted = desiredPaths.toList()..sort();
    await prefs.setStringList(_prefsPathsKey, persisted);

    final countRows = await db.rawQuery(
      'SELECT COUNT(*) AS count FROM user_roms WHERE app_system_id = ?',
      [dreamcast!.id!],
    );
    final totalDreamcastRows =
        int.tryParse('${countRows.first['count'] ?? 0}') ?? 0;

    if (totalDreamcastRows > 0) {
      await SystemRepository.addDetectedSystem(dreamcast.id!, 'dc');
    } else {
      await SystemRepository.removeDetectedSystem(dreamcast.id!);
    }

    return (
      importedRows: importedRows,
      removedRows: removedRows,
      totalDreamcastRows: totalDreamcastRows,
    );
  }

  /// True when [romPath] came from the last iFly folder sync.
  static bool isManagedRomPath(String romPath) {
    if (romPath.isEmpty) return false;
    return _syncedPaths.contains(_normalizePath(romPath));
  }

  /// Best launch mechanism available in iFly V1.
  ///
  /// The examined V1 IPA has no CFBundleURLTypes/custom URL scheme, so iOS
  /// cannot address iFly directly by deeplink. It does register Dreamcast ROM
  /// document types, therefore the supported hand-off is the native Open In
  /// menu. This method is intentionally isolated so a future iFly scheme can
  /// replace it without touching game-list/database code.
  static Future<bool> launchGameByRomPath(String romPath) async {
    if (!isManagedRomPath(romPath)) return false;

    final file = File(romPath);
    if (!await file.exists()) {
      await _writeDebugFile(
        'ifly_launch_debug.txt',
        'STATE: ERROR\nROM does not exist: $romPath',
      );
      return false;
    }

    try {
      final presented =
          await ExternalFolderAccess.openInMenu(romPath) ?? false;
      await _writeDebugFile(
        'ifly_launch_debug.txt',
        'STATE: ${presented ? 'OPEN_IN_PRESENTED' : 'OPEN_IN_FAILED'}\n'
            'ROM: $romPath\n'
            'iFly V1 exposes no custom URL scheme; launch uses iOS Open In.',
      );
      return presented;
    } catch (e) {
      _log.e('IflyLibraryService: Open In failed: $e');
      await _writeDebugFile(
        'ifly_launch_debug.txt',
        'STATE: ERROR\nROM: $romPath\nError: $e',
      );
      return false;
    }
  }

  static Future<void> _refreshNeoStationUi() async {
    try {
      final context = rootNavigatorKey.currentContext;
      if (context == null) return;

      await Provider.of<SqliteDatabaseProvider>(
        context,
        listen: false,
      ).loadGamesForSystem('dc');
      await Provider.of<SqliteConfigProvider>(
        context,
        listen: false,
      ).refreshDetectedSystems();
    } catch (e) {
      _log.e('IflyLibraryService: UI refresh failed: $e');
    }
  }

  static String _displayTitle(String fileName) {
    var value = path.basenameWithoutExtension(fileName).replaceAll('_', ' ');
    value = value.replaceAll(RegExp(r'\s+'), ' ').trim();
    return value.isEmpty ? fileName : value;
  }

  static bool _isKnownBiosFile(String fileName) {
    final lower = fileName.toLowerCase();
    return lower == 'dc_boot.bin' ||
        lower == 'dc_flash.bin' ||
        lower == 'boot.bin' ||
        lower == 'flash.bin';
  }

  static String _normalizePath(String value) {
    return path.normalize(value).toLowerCase();
  }

  static Future<void> _writeDebugFile(String name, String content) async {
    try {
      final docsDir = await getApplicationDocumentsDirectory();
      final file = File(path.join(docsDir.path, name));
      await file.writeAsString('--- ${DateTime.now()} ---\n$content');
    } catch (e) {
      _log.e('IflyLibraryService: failed writing debug file $name: $e');
    }
  }
}

class IflySyncResult {
  final bool success;
  final int importedRows;
  final int removedRows;
  final int totalDreamcastRows;
  final String? error;

  const IflySyncResult._({
    required this.success,
    required this.importedRows,
    required this.removedRows,
    required this.totalDreamcastRows,
    this.error,
  });

  const IflySyncResult.failure(String error)
      : this._(
          success: false,
          importedRows: 0,
          removedRows: 0,
          totalDreamcastRows: 0,
          error: error,
        );

  const IflySyncResult.success({
    required int importedRows,
    required int removedRows,
    required int totalDreamcastRows,
  }) : this._(
          success: true,
          importedRows: importedRows,
          removedRows: removedRows,
          totalDreamcastRows: totalDreamcastRows,
        );
}
