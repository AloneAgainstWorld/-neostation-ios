#!/usr/bin/env python3
"""Apply the first safe NeoSync v2 + iOS compatibility port.

This is intentionally scoped to RetroArch for iOS. It refuses to fall back to
legacy v1 cloud paths when a system/core cannot be identified.
"""

from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    if new in source and old not in source:
        return
    if old not in source:
        raise SystemExit(f"{label}: expected source fragment not found in {path}")
    p.write_text(source.replace(old, new, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# iOS RetroArch filesystem discovery through the existing security bookmark.
# ---------------------------------------------------------------------------
p = Path("lib/services/retroarch_config_service.dart")
s = p.read_text(encoding="utf-8")
marker = "  /// Returns the merged configuration by discovering the platform's standard\n"
ios_helpers = r'''  /// Resolves RetroArch directories from the security-scoped folder linked
  /// by NeoStation on iOS. The bookmark itself is restored in main.dart before
  /// providers are created, so filesystem access is already active here.
  Future<RetroArchConfig?> _getIOSLinkedConfig() async {
    if (!Platform.isIOS) return null;

    final linkedRoot = ConfigService.linkedExternalFolderPath?.trim();
    if (linkedRoot == null || linkedRoot.isEmpty) {
      _log.w('iOS RetroArch folder is not linked; NeoSync local paths unavailable');
      return null;
    }

    final root = Directory(linkedRoot);
    if (!await root.exists()) {
      _log.w('iOS linked RetroArch folder no longer exists: $linkedRoot');
      return null;
    }

    String? configPath;
    final configCandidates = <String>[
      path.join(linkedRoot, 'retroarch.cfg'),
      path.join(linkedRoot, 'config', 'retroarch.cfg'),
      path.join(linkedRoot, 'RetroArch', 'retroarch.cfg'),
    ];
    for (final candidate in configCandidates) {
      if (File(candidate).existsSync()) {
        configPath = candidate;
        break;
      }
    }

    if (configPath == null) {
      try {
        for (final child in root.listSync(followLinks: false).whereType<Directory>()) {
          final candidate = path.join(child.path, 'retroarch.cfg');
          if (File(candidate).existsSync()) {
            configPath = candidate;
            break;
          }
        }
      } catch (e) {
        _log.w('Could not inspect linked RetroArch folder for retroarch.cfg: $e');
      }
    }

    RetroArchConfig? parsed;
    if (configPath != null) {
      try {
        parsed = await parseConfig(configPath);
      } catch (e) {
        _log.w('Could not parse linked iOS RetroArch config: $e');
      }
    }

    String resolveDirectory(String logicalName, String? configured) {
      if (configured != null &&
          configured.isNotEmpty &&
          Directory(configured).existsSync()) {
        return configured;
      }

      final names = <String>{logicalName.toLowerCase()};
      if (configured != null && configured.isNotEmpty) {
        names.add(path.basename(configured).toLowerCase());
      }

      final candidates = <String>[
        for (final name in names) path.join(linkedRoot, name),
        for (final name in names) path.join(linkedRoot, 'RetroArch', name),
      ];
      for (final candidate in candidates) {
        if (Directory(candidate).existsSync()) return candidate;
      }

      try {
        for (final child in root.listSync(followLinks: false).whereType<Directory>()) {
          if (names.contains(path.basename(child.path).toLowerCase())) {
            return child.path;
          }
        }
      } catch (_) {}

      // Downloads stay inside the bookmarked RetroArch folder even if the
      // directory has not been created by RetroArch yet.
      return path.join(linkedRoot, logicalName);
    }

    final resolved = RetroArchConfig(
      configPath: configPath ?? '',
      systemDirectory: resolveDirectory('system', parsed?.systemDirectory),
      savefileDirectory: resolveDirectory('saves', parsed?.savefileDirectory),
      savestateDirectory: resolveDirectory('states', parsed?.savestateDirectory),
    );
    _log.i(
      'iOS RetroArch paths resolved for NeoSync: '
      'saves=${resolved.savefileDirectory}, states=${resolved.savestateDirectory}',
    );
    return resolved;
  }

'''
if "Future<RetroArchConfig?> _getIOSLinkedConfig()" not in s:
    if marker not in s:
        raise SystemExit("RetroArchConfigService insertion marker not found")
    s = s.replace(marker, ios_helpers + marker, 1)

cache_marker = '''    if (_cachedConfig != null && !forceRefresh) {
      return _cachedConfig!;
    }

    String? configPath;
'''
cache_new = '''    if (_cachedConfig != null && !forceRefresh) {
      return _cachedConfig!;
    }

    if (Platform.isIOS) {
      final iosConfig = await _getIOSLinkedConfig();
      if (iosConfig != null) {
        _cachedConfig = iosConfig;
        return iosConfig;
      }
      return RetroArchConfig(
        configPath: '',
        systemDirectory: null,
        savefileDirectory: null,
        savestateDirectory: null,
      );
    }

    String? configPath;
'''
if cache_new not in s:
    if cache_marker not in s:
        raise SystemExit("RetroArchConfigService cache marker not found")
    s = s.replace(cache_marker, cache_new, 1)
p.write_text(s, encoding="utf-8")

# Canonical v2 path helper available to all NeoSync part files.
replace_once(
    "lib/providers/neo_sync_provider.dart",
    "import '../services/retroarch_config_service.dart';\n",
    "import '../services/retroarch_config_service.dart';\nimport '../utils/cloud_path_builder.dart';\n",
    "NeoSync provider import",
)

# Include the per-game emulator override/core identifier when matching saves.
replace_once(
    "lib/repositories/game_repository.dart",
    "SELECT ur.filename, ur.title_name, s.folder_name\n",
    "SELECT ur.filename, ur.title_name, s.folder_name, ur.app_emulator_unique_id AS emulator_name\n",
    "GameRepository emulator metadata",
)

# ---------------------------------------------------------------------------
# NeoSync v2 HTTP API.
# ---------------------------------------------------------------------------
p = Path("lib/services/neosync/neo_sync_service.dart")
s = p.read_text(encoding="utf-8").replace("/api/v1/", "/api/v2/")
old_sig = '''  Future<Map<String, dynamic>> syncFile(
    File file,
    String gameName, {
    String? customFilename,
  }) async {
'''
new_sig = '''  Future<Map<String, dynamic>> syncFile(
    File file,
    String gameName, {
    String? customFilename,
    String? systemId,
    String? emulatorId,
    String? gameHash,
    bool? isState,
    String? scope,
  }) async {
'''
if new_sig not in s:
    if old_sig not in s:
        raise SystemExit("NeoSyncService syncFile signature not found")
    s = s.replace(old_sig, new_sig, 1)

metadata_marker = '''      request.fields['file_modified_at_timestamp'] = fileModifiedAtTimestamp
          .toString();
'''
metadata_extra = '''      if (systemId != null && systemId.isNotEmpty) {
        request.fields['system_id'] = systemId;
      }
      if (emulatorId != null && emulatorId.isNotEmpty) {
        request.fields['emulator_id'] = emulatorId;
      }
      if (gameHash != null && gameHash.isNotEmpty) {
        request.fields['game_hash'] = gameHash;
      }
      if (isState != null) {
        request.fields['is_state'] = isState.toString();
      }
      if (scope != null && scope.isNotEmpty) {
        request.fields['scope'] = scope;
      }
'''
if "request.fields['system_id']" not in s:
    if metadata_marker not in s:
        raise SystemExit("NeoSyncService upload metadata marker not found")
    s = s.replace(metadata_marker, metadata_marker + metadata_extra, 1)

old_files_uri = "      final uri = Uri.parse('$baseUrl/api/v2/files');\n"
new_files_uri = """      final uri = Uri.parse('$baseUrl/api/v2/files').replace(
        queryParameters: const {'limit': '200', 'offset': '0'},
      );
"""
if new_files_uri not in s:
    if old_files_uri not in s:
        raise SystemExit("NeoSyncService getFiles URI marker not found")
    s = s.replace(old_files_uri, new_files_uri, 1)
p.write_text(s, encoding="utf-8")

# ---------------------------------------------------------------------------
# iOS path routing + v2 cloud namespace.
# ---------------------------------------------------------------------------
p = Path("lib/providers/neosync/neosync_path_resolver.dart")
s = p.read_text(encoding="utf-8")
folders_marker = '''    final folders = system.neosync.getFoldersForCurrentPlatform();
    final List<String> resolvedPaths = [];

    for (final folder in folders) {
'''
folders_new = '''    final folders = system.neosync.getFoldersForCurrentPlatform();
    final List<String> resolvedPaths = [];

    // System JSON predates iOS NeoSync and has no ios_sync_folder entries.
    // RetroArch's bookmarked saves/states roots are authoritative for preview 1.
    if (Platform.isIOS && folders.isEmpty) {
      final saves = await _getRetroArchSavesPath();
      final states = await _getRetroArchStatesPath();
      if (saves != null) resolvedPaths.add(saves);
      if (states != null) resolvedPaths.add(states);
    }

    for (final folder in folders) {
'''
if folders_new not in s:
    if folders_marker not in s:
        raise SystemExit("resolveUniversalPaths marker not found")
    s = s.replace(folders_marker, folders_new, 1)

start = s.find("  /// Helper to calculate relative path for sync")
end = s.find("  /// Calcula la ruta relativa para sincronización", start)
if "Future<GameModel?> _gameForSaveFile" not in s:
    if start < 0 or end < 0:
        raise SystemExit("Could not locate legacy sync path builder block")
    v2_builder = r'''  /// Resolves a local save file back to its library game.
  Future<GameModel?> _gameForSaveFile(File file) async {
    final saveBase = path.basenameWithoutExtension(file.path);
    try {
      final row = await GameRepository.findRomByFilenamePrefix(saveBase);
      if (row == null) return null;
      final romname = row['filename']?.toString() ?? saveBase;
      final title = row['title_name']?.toString();
      return GameModel(
        name: (title == null || title.isEmpty) ? romname : title,
        realname: (title == null || title.isEmpty) ? romname : title,
        romname: romname,
        systemFolderName: row['folder_name']?.toString(),
        emulatorName: row['emulator_name']?.toString(),
        year: '',
        developer: '',
        publisher: '',
        genre: '',
        players: '',
        rating: 0.0,
      );
    } catch (e) {
      NeoSyncProvider._log.w('Could not map save ${file.path} to a game: $e');
      return null;
    }
  }

  /// Builds the canonical NeoSync v2 path for a local game save/state.
  /// Never falls back to a v1 cloud path.
  Future<String> _calculateSyncRelativePath(
    GameModel game,
    File file,
    String basePath, {
    bool isState = false,
  }) async {
    final systemFolder =
        game.systemFolderName ??
        await GameRepository.getSystemFolderForGame(game.romname);
    if (systemFolder == null || systemFolder.isEmpty) {
      throw StateError('NeoSync v2: system could not be resolved for ${game.romname}');
    }

    String? emulatorSlug;
    final relative = path.relative(file.path, from: basePath);
    final segments = relative.split(RegExp(r'[/\\]'));
    if (!relative.startsWith('..') && segments.length > 1) {
      final coreFolder = segments.first;
      if (coreFolder.isNotEmpty) {
        emulatorSlug = CloudPathBuilder.retroArchCoreSlug(coreFolder);
      }
    }

    if ((emulatorSlug == null || emulatorSlug.isEmpty) &&
        game.coreName != null &&
        game.coreName!.trim().isNotEmpty) {
      emulatorSlug = CloudPathBuilder.retroArchCoreSlug(game.coreName!);
    }
    if ((emulatorSlug == null || emulatorSlug.isEmpty) &&
        game.emulatorName != null &&
        game.emulatorName!.trim().isNotEmpty) {
      emulatorSlug = CloudPathBuilder.slugFromEmulatorUniqueId(game.emulatorName!);
    }
    if (emulatorSlug == null || emulatorSlug.isEmpty) {
      throw StateError(
        'NeoSync v2: emulator/core could not be resolved for ${game.romname}',
      );
    }

    final lowerName = path.basename(file.path).toLowerCase();
    final systemLower = systemFolder.toLowerCase();
    final isSharedCard =
        (systemLower == 'ps2' && lowerName.endsWith('.ps2')) ||
        ((systemLower == 'dc' || systemLower == 'dreamcast') &&
            lowerName.contains('vmu_save'));

    return CloudPathBuilder.build(
      system: systemFolder,
      emulatorSlug: emulatorSlug,
      scope: isSharedCard ? 'shared' : 'game',
      gameName: isSharedCard ? null : path.basenameWithoutExtension(file.path),
      filePath: path.basename(file.path),
      isState: isState,
    );
  }

  Future<String?> _retroArchCoreFolderForSlug(
    String emulatorSlug,
    String baseFolder,
  ) async {
    if (!emulatorSlug.startsWith('retroarch.')) return null;
    try {
      final base = Directory(baseFolder);
      if (!base.existsSync()) return null;
      for (final child in base.listSync(followLinks: false).whereType<Directory>()) {
        final name = path.basename(child.path);
        if (CloudPathBuilder.retroArchCoreSlug(name) == emulatorSlug) {
          return name;
        }
      }
    } catch (e) {
      NeoSyncProvider._log.w('Could not map $emulatorSlug under $baseFolder: $e');
    }
    return null;
  }

'''
    s = s[:start] + v2_builder + s[end:]

old_kind = '''    final isState = cloudFile.fileName.startsWith('states/');
    final isSave = cloudFile.fileName.startsWith('saves/');
'''
new_kind = '''    final v2Path = CloudPathBuilder.parse(cloudFile.fileName);
    final isState = v2Path?.isState ?? cloudFile.fileName.startsWith('states/');
    final isSave = v2Path != null
        ? !v2Path.isState
        : cloudFile.fileName.startsWith('saves/');
'''
if new_kind not in s:
    if old_kind not in s:
        raise SystemExit("Cloud path kind marker not found")
    s = s.replace(old_kind, new_kind, 1)

old_relative = r'''    String relativeName = cloudFile.fileName;
    if (isState) {
      relativeName = relativeName.replaceFirst(RegExp(r'^states[/\\]'), '');
    }
    if (isSave) {
      relativeName = relativeName.replaceFirst(RegExp(r'^saves[/\\]'), '');
    }
'''
new_relative = r'''    String relativeName = cloudFile.fileName;
    if (v2Path != null) {
      relativeName = v2Path.filePath;
      if (v2Path.emulatorSlug.startsWith('retroarch.')) {
        final coreFolder = await _retroArchCoreFolderForSlug(
          v2Path.emulatorSlug,
          targetFolder,
        );
        if (coreFolder != null && coreFolder.isNotEmpty) {
          relativeName = path.join(coreFolder, relativeName);
        }
      }
    } else if (isState) {
      relativeName = relativeName.replaceFirst(RegExp(r'^states[/\\]'), '');
    } else if (isSave) {
      relativeName = relativeName.replaceFirst(RegExp(r'^saves[/\\]'), '');
    }
'''
if new_relative not in s:
    if old_relative not in s:
        raise SystemExit("Cloud relative name marker not found")
    s = s.replace(old_relative, new_relative, 1)
p.write_text(s, encoding="utf-8")

# ---------------------------------------------------------------------------
# Auto-upload: map every RetroArch file to a game, then require a v2 path.
# ---------------------------------------------------------------------------
p = Path("lib/providers/neosync/neosync_upload.dart")
s = p.read_text(encoding="utf-8")
old_auto = '''      String relativePath = _calculateRelativePath(
        file,
        basePath,
        isState: isState,
      );
      final gameName = _extractGameNameFromPath(file.path);

      final result = await _neoSyncService.syncFile(
        file,
        gameName,
        customFilename: relativePath,
      );
'''
new_auto = '''      final game = await _gameForSaveFile(file);
      if (game == null) {
        _skippedFiles++;
        _processedItems.add(
          'Skipped unrecognized save (NeoSync v2 safety): ${path.basename(file.path)}',
        );
        return;
      }

      final relativePath = await _calculateSyncRelativePath(
        game,
        file,
        basePath,
        isState: isState,
      );
      final v2Path = CloudPathBuilder.parse(relativePath);
      if (v2Path == null) {
        _skippedFiles++;
        _processedItems.add('Skipped non-v2 path: $relativePath');
        return;
      }

      final result = await _neoSyncService.syncFile(
        file,
        game.name,
        customFilename: relativePath,
        systemId: v2Path.system,
        emulatorId: v2Path.emulatorSlug,
        isState: v2Path.isState,
        scope: v2Path.scope,
      );
'''
if new_auto not in s:
    count = s.count(old_auto)
    if count < 2:
        raise SystemExit(f"Expected two generic upload blocks, found {count}")
    s = s.replace(old_auto, new_auto, 2)
p.write_text(s, encoding="utf-8")

# Per-game upload already knows the GameModel; attach v2 metadata.
p = Path("lib/providers/neosync/neosync_core.dart")
s = p.read_text(encoding="utf-8")
old_core = '''      final result = await _neoSyncService.syncFile(
        file,
        game.name,
        customFilename: relativePath,
      );
'''
new_core = '''      final v2Path = CloudPathBuilder.parse(relativePath);
      if (v2Path == null) return false;

      final result = await _neoSyncService.syncFile(
        file,
        game.name,
        customFilename: relativePath,
        systemId: v2Path.system,
        emulatorId: v2Path.emulatorSlug,
        isState: v2Path.isState,
        scope: v2Path.scope,
      );
'''
if new_core not in s:
    if old_core not in s:
        raise SystemExit("Per-game NeoSync upload block not found")
    s = s.replace(old_core, new_core, 1)
p.write_text(s, encoding="utf-8")

# Auto-download: understand v2 game paths before legacy heuristics.
p = Path("lib/providers/neosync/neosync_download.dart")
s = p.read_text(encoding="utf-8")
find_marker = '''  Future<GameModel?> _findGameForCloudFile(NeoSyncFile cloudFile) async {
    final parts = cloudFile.fileName.split('/');
'''
find_new = '''  Future<GameModel?> _findGameForCloudFile(NeoSyncFile cloudFile) async {
    final v2Path = CloudPathBuilder.parse(cloudFile.fileName);
    if (v2Path != null && !v2Path.isShared) {
      final saveBase = path.basenameWithoutExtension(v2Path.filePath);
      try {
        final row = await GameRepository.findRomByFilenamePrefix(saveBase);
        if (row != null) {
          final romname = row['filename'].toString();
          final title = row['title_name']?.toString();
          return GameModel(
            name: (title == null || title.isEmpty) ? romname : title,
            realname: (title == null || title.isEmpty) ? romname : title,
            romname: romname,
            systemFolderName: row['folder_name']?.toString() ?? v2Path.system,
            emulatorName: row['emulator_name']?.toString(),
            year: '',
            developer: '',
            publisher: '',
            genre: '',
            players: '',
            rating: 0.0,
          );
        }
      } catch (e) {
        NeoSyncProvider._log.w('Could not map v2 cloud save to local game: $e');
      }
    }

    final parts = cloudFile.fileName.split('/');
'''
if find_new not in s:
    if find_marker not in s:
        raise SystemExit("NeoSync download game resolver marker not found")
    s = s.replace(find_marker, find_new, 1)
p.write_text(s, encoding="utf-8")

print("NeoSync v2 iOS preview source patch applied")
