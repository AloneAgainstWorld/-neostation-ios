#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# ---------------------------------------------------------------------------
# Shared MeloNX helpers: Title ID is used only for local filesystem mapping.
# The NeoSync cloud path and game_name remain human-readable game names.
# ---------------------------------------------------------------------------
path_resolver = 'lib/providers/neosync/neosync_path_resolver.dart'
marker = '''  /// Resolves a local save file back to its library game.\n  Future<GameModel?> _gameForSaveFile(File file) async {'''
helpers = r'''  bool _isMeloNXTitleId(String value) =>
      RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(value.trim());

  /// Extracts the Switch Title ID from a MeloNX save path while preserving the
  /// path *inside* that game's save directory. The Title ID is a local lookup
  /// key only and is never used as the NeoSync-visible game name.
  ({String titleId, String internalPath})? _parseMeloNXSaveLocation(
    File file,
    String root,
  ) {
    final relative = path.relative(file.path, from: root).replaceAll('\\', '/');
    if (relative == '..' || relative.startsWith('../')) return null;

    final segments = relative.split('/').where((part) => part.isNotEmpty).toList();
    if (segments.isEmpty) return null;

    var titleIndex = -1;
    final saveIndex = segments.indexWhere(
      (part) => part.toLowerCase() == 'save',
    );
    if (saveIndex >= 0) {
      for (var i = saveIndex + 1; i < segments.length; i++) {
        if (_isMeloNXTitleId(segments[i])) {
          titleIndex = i;
          break;
        }
      }
    }
    if (titleIndex < 0) {
      titleIndex = segments.indexWhere(_isMeloNXTitleId);
    }
    if (titleIndex < 0 || titleIndex + 1 >= segments.length) return null;

    return (
      titleId: segments[titleIndex],
      internalPath: segments.sublist(titleIndex + 1).join('/'),
    );
  }

  Future<String?> _meloNXTitleIdForGame(GameModel game) async {
    var titleId = game.titleId?.trim();
    if (titleId == null || titleId.isEmpty) {
      titleId = await GameRepository.getTitleIdForGame(game.romname, game.name);
    }
    if (titleId == null || !_isMeloNXTitleId(titleId)) return null;
    return titleId;
  }

  /// Builds the canonical NeoSync v2 path for a MeloNX file. The Title ID is
  /// deliberately removed from the cloud path; NeoSync shows the game title.
  Future<({String cloudPath, String gameName, String titleId})?>
  _resolveMeloNXFileForCloud(
    File file,
    String root, {
    GameModel? preferredGame,
  }) async {
    final location = _parseMeloNXSaveLocation(file, root);
    if (location == null) return null;

    String? gameName;
    final preferredTitleId = await _meloNXTitleIdForGame(
      preferredGame ??
          GameModel(
            name: '',
            realname: '',
            romname: '',
            year: '',
            developer: '',
            publisher: '',
            genre: '',
            players: '',
            rating: 0,
          ),
    );
    if (preferredGame != null &&
        preferredTitleId != null &&
        preferredTitleId.toLowerCase() == location.titleId.toLowerCase()) {
      gameName = preferredGame.name.trim();
    }

    if (gameName == null || gameName.isEmpty) {
      final row = await GameRepository.findSwitchGameByTitleId(location.titleId);
      if (row == null) return null;
      final title = row['title_name']?.toString().trim() ?? '';
      final filename = row['filename']?.toString().trim() ?? '';
      gameName = title.isNotEmpty ? title : path.basenameWithoutExtension(filename);
    }
    if (gameName.isEmpty) return null;

    final cloudPath = CloudPathBuilder.build(
      system: 'switch',
      emulatorSlug: 'melonx',
      scope: 'game',
      gameName: gameName,
      filePath: location.internalPath,
      isState: false,
    );
    return (
      cloudPath: cloudPath,
      gameName: gameName,
      titleId: location.titleId,
    );
  }

  /// Finds the local MeloNX save directory for a game. Existing Title-ID
  /// directories are preferred. If the game directory does not exist yet, use
  /// the standard bis/user/save/... structure only when its user root already
  /// exists, avoiding creation of guessed account directories.
  String? _resolveMeloNXGameSaveDirectory(
    String root,
    String titleId, {
    bool allowCreate = false,
  }) {
    final rootDir = Directory(root);
    if (!rootDir.existsSync()) return null;

    try {
      for (final entity in rootDir.listSync(recursive: true, followLinks: false)) {
        if (entity is Directory &&
            path.basename(entity.path).toLowerCase() == titleId.toLowerCase()) {
          return entity.path;
        }
      }
    } catch (e) {
      NeoSyncProvider._log.w('Could not scan MeloNX save tree: $e');
    }

    if (!allowCreate) return null;

    var bisRoot = root;
    if (path.basename(root).toLowerCase() != 'bis') {
      final nestedBis = path.join(root, 'bis');
      if (Directory(nestedBis).existsSync()) bisRoot = nestedBis;
    }

    final saveBase = path.join(
      bisRoot,
      'user',
      'save',
      '0000000000000000',
    );
    final saveBaseDir = Directory(saveBase);
    if (!saveBaseDir.existsSync()) return null;

    try {
      final userDirs = saveBaseDir.listSync(followLinks: false).whereType<Directory>();
      if (userDirs.isEmpty) return null;
      return path.join(userDirs.first.path, titleId);
    } catch (_) {
      return null;
    }
  }

  /// Resolves a local save file back to its library game.
  Future<GameModel?> _gameForSaveFile(File file) async {'''
replace_once(path_resolver, marker, helpers)

# Replace the old direct MeloNX restore path with Title-ID local resolution.
old = '''      } else if (v2Path.emulatorSlug == 'melonx') {\n        final root = ConfigService.linkedMelonxSaveFolderPath;\n        if (root != null && root.isNotEmpty) {\n          return [path.join(root, v2Path.filePath)];\n        }\n      }'''
new = '''      } else if (v2Path.emulatorSlug == 'melonx') {\n        final root = ConfigService.linkedMelonxSaveFolderPath;\n        if (root != null && root.isNotEmpty) {\n          final titleId = await _meloNXTitleIdForGame(game);\n          if (titleId == null) return [];\n          final gameSaveRoot = _resolveMeloNXGameSaveDirectory(\n            root,\n            titleId,\n            allowCreate: true,\n          );\n          if (gameSaveRoot == null) return [];\n          return [path.join(gameSaveRoot, v2Path.filePath)];\n        }\n      }'''
replace_once(path_resolver, old, new)

# ---------------------------------------------------------------------------
# Upload: MeloNX gets a dedicated game-aware path, never a generic shared tree.
# ---------------------------------------------------------------------------
upload = 'lib/providers/neosync/neosync_upload.dart'
old = '''      if (customSystem != null && customEmulatorSlug != null) {\n        final relativeFile = path'''
new = '''      if (customSystem == 'switch' && customEmulatorSlug == 'melonx') {\n        await _uploadMeloNXFile(file, basePath);\n        return;\n      }\n\n      if (customSystem != null && customEmulatorSlug != null) {\n        final relativeFile = path'''
replace_once(upload, old, new)

marker = '''  /// Maneja la subida automática de archivos de Switch NAND\n  Future<void> _handleSwitchNandAutoUpload(File file) async {'''
method = r'''  /// Uploads one MeloNX file using Title ID only to identify the local game.
  /// The NeoSync-visible path and game_name use the human-readable game title.
  Future<bool> _uploadMeloNXFile(
    File file,
    String root, {
    GameModel? preferredGame,
  }) async {
    final resolved = await _resolveMeloNXFileForCloud(
      file,
      root,
      preferredGame: preferredGame,
    );
    if (resolved == null) {
      _skippedFiles++;
      return false;
    }

    final result = await _neoSyncService.syncFile(
      file,
      resolved.gameName,
      customFilename: resolved.cloudPath,
      systemId: 'switch',
      emulatorId: 'melonx',
      isState: false,
      scope: 'game',
    );

    if (result['success'] == true) {
      if (result['skipped'] == true) {
        _skippedFiles++;
      } else {
        _uploadedFiles++;
        _resetQuotaAttempts();
      }
      _processedItems.add('NeoSync: ${resolved.gameName}');
      return true;
    }

    final errorMessage = result['message']?.toString() ?? '';
    _processedItems.add(
      'Failed to upload ${resolved.gameName}: $errorMessage',
    );
    if (_checkQuotaExceeded(errorMessage)) {
      _quotaExceededActive = true;
      throw QuotaExceededException(errorMessage, _quotaExceededAttempts);
    }
    return false;
  }

  /// Maneja la subida automática de archivos de Switch NAND
  Future<void> _handleSwitchNandAutoUpload(File file) async {'''
replace_once(upload, marker, method)

# ---------------------------------------------------------------------------
# Per-game sync: when a MeloNX game closes, generate the exact same readable
# cloud path as the global scan instead of trying RetroArch-style filenames.
# ---------------------------------------------------------------------------
core = 'lib/providers/neosync/neosync_core.dart'
old = '''      // 2. Determinar la ruta relativa de manera universal\n      final savesPath = await _getRetroArchSavesPath();\n      final statesPath = await _getRetroArchStatesPath();'''
new = '''      // MeloNX on iOS stores saves below a Title-ID directory. Use that ID\n      // only for local matching, while the cloud keeps the readable game name.\n      final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;\n      if (Platform.isIOS &&\n          system.folderName.toLowerCase() == 'switch' &&\n          melonxRoot != null &&\n          melonxRoot.isNotEmpty &&\n          (path.isWithin(melonxRoot, file.path) ||\n              path.equals(file.parent.path, melonxRoot))) {\n        return await _uploadMeloNXFile(\n          file,\n          melonxRoot,\n          preferredGame: game,\n        );\n      }\n\n      // 2. Determinar la ruta relativa de manera universal\n      final savesPath = await _getRetroArchSavesPath();\n      final statesPath = await _getRetroArchStatesPath();'''
replace_once(core, old, new)

# In _findGameSaveFiles, calculate MeloNX's canonical readable v2 path instead
# of a generic saves/<file> relative name.
old = '''            final relativePath = _calculateRelativePath(\n              file,\n              basePath,\n              isState: isState,\n            );'''
new = '''            String relativePath;\n            final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;\n            if (Platform.isIOS &&\n                system.folderName.toLowerCase() == 'switch' &&\n                melonxRoot != null &&\n                melonxRoot.isNotEmpty &&\n                path.isWithin(melonxRoot, file.path)) {\n              final melonx = await _resolveMeloNXFileForCloud(\n                file,\n                melonxRoot,\n                preferredGame: game,\n              );\n              if (melonx == null) continue;\n              relativePath = melonx.cloudPath;\n            } else {\n              relativePath = _calculateRelativePath(\n                file,\n                basePath,\n                isState: isState,\n              );\n            }'''
replace_once(core, old, new)

# Cloud matching for a currently selected MeloNX game must use the readable
# game name stored in the v2 path / metadata, not the synthetic Title-ID ROM name.
old = '''        } else {\n          // Para sistemas estándar, filtrar por romname\n          // Usamos la ruta completa del cloudFile por si está en carpetas (ej. Switch)\n          final fullCloudPathLower = cloudFile.fileName.toLowerCase();'''
new = '''        } else {\n          final parsed = CloudPathBuilder.parse(cloudFile.fileName);\n          if (system.folderName.toLowerCase() == 'switch' &&\n              parsed?.emulatorSlug == 'melonx' &&\n              parsed?.gameName != null) {\n            final expectedNames = <String>{\n              CloudPathBuilder.sanitizeGameName(game.name).toLowerCase(),\n              if (game.titleName != null && game.titleName!.trim().isNotEmpty)\n                CloudPathBuilder.sanitizeGameName(game.titleName!).toLowerCase(),\n            };\n            final cloudGameName = parsed!.gameName!.toLowerCase();\n            if (expectedNames.contains(cloudGameName) ||\n                cloudFile.gameName.toLowerCase() == game.name.toLowerCase()) {\n              isMatch = true;\n            }\n          }\n\n          // Para sistemas estándar, filtrar por romname cuando no haya match v2.\n          // Usamos la ruta completa del cloudFile por si está en carpetas.\n          final fullCloudPathLower = cloudFile.fileName.toLowerCase();'''
replace_once(core, old, new)

# Prevent the generic name matcher from overriding logic unnecessarily; it may
# still provide compatibility for old/non-MeloNX Switch saves.
old = '''          if (fileName.contains(gameRomName) ||\n              fullCloudPathLower.contains(gameRomName)) {\n            isMatch = true;\n          } else {'''
new = '''          if (!isMatch &&\n              (fileName.contains(gameRomName) ||\n                  fullCloudPathLower.contains(gameRomName))) {\n            isMatch = true;\n          } else if (!isMatch) {'''
replace_once(core, old, new)

# ---------------------------------------------------------------------------
# Download: map a readable MeloNX v2 game name back to its local Title ID.
# ---------------------------------------------------------------------------
download = 'lib/providers/neosync/neosync_download.dart'
old = '''    if (v2Path != null && !v2Path.isShared) {\n      final saveBase = path.basenameWithoutExtension(v2Path.filePath);\n      try {'''
new = '''    if (v2Path != null &&\n        v2Path.emulatorSlug == 'melonx' &&\n        v2Path.gameName != null) {\n      final displayName = cloudFile.gameName.trim().isNotEmpty\n          ? cloudFile.gameName.trim()\n          : v2Path.gameName!;\n      try {\n        final row = await GameRepository.findSwitchGameByName(displayName);\n        if (row != null) {\n          final romname = row['filename'].toString();\n          final title = row['title_name']?.toString();\n          final titleId = row['title_id']?.toString();\n          final romPath = row['rom_path']?.toString();\n          return GameModel(\n            name: (title == null || title.isEmpty) ? displayName : title,\n            realname: (title == null || title.isEmpty) ? displayName : title,\n            romname: romname,\n            romPath: romPath,\n            titleName: title,\n            systemFolderName: 'switch',\n            systemId: 'switch',\n            year: '',\n            developer: '',\n            publisher: '',\n            genre: '',\n            players: '',\n            rating: 0.0,\n          ).copyWith(titleId: titleId);\n        }\n      } catch (e) {\n        NeoSyncProvider._log.w('Could not map MeloNX cloud save by game name: $e');\n      }\n    }\n\n    if (v2Path != null && !v2Path.isShared) {\n      final saveBase = path.basenameWithoutExtension(v2Path.filePath);\n      try {'''
replace_once(download, old, new)

print('MeloNX Title-ID mapping / readable NeoSync name patch applied')
