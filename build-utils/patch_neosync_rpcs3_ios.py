#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:220]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def insert_before(path: str, marker: str, addition: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if addition in text:
        return
    if marker not in text:
        raise SystemExit(f'Insert marker not found in {path}: {marker[:220]!r}')
    p.write_text(text.replace(marker, addition + marker, 1), encoding='utf-8')

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
provider = 'lib/providers/neo_sync_provider.dart'
replace_once(
    provider,
    "import '../services/retroarch_config_service.dart';\n",
    "import '../services/retroarch_config_service.dart';\nimport '../services/rpcs3_library_service.dart';\n",
)

# -----------------------------------------------------------------------------
# PS3 system config: iOS-only RPCS3 savedata support.
# -----------------------------------------------------------------------------
ps3 = 'assets/systems/ps3.json'
replace_once(ps3, '"sync": false,', '"sync": true,')
replace_once(
    ps3,
    '''    "macos_sync_folder": []\n''',
    '''    "macos_sync_folder": [],\n    "ios_sync_folder": [\n      "{RPCS3_IOS_SAVEDATA}"\n    ]\n''',
)

# -----------------------------------------------------------------------------
# Path resolver
# -----------------------------------------------------------------------------
resolver = 'lib/providers/neosync/neosync_path_resolver.dart'
insert_before(
    resolver,
    "    // 3. Placeholder {NETHERSX2_MEMCARDS} (AetherSX2/NetherSX2 memcards)\n",
    '''    // RPCS3 iOS native PS3 save-data roots. Reuse the existing security-\n    // scoped bookmark for RPCS3 > Data; no second folder picker is required.\n    if (pathStr == '{RPCS3_IOS_SAVEDATA}' && Platform.isIOS) {\n      final dataRoot = Rpcs3LibraryService.linkedDataPath;\n      if (dataRoot == null || dataRoot.isEmpty) return [];\n      final home = Directory(path.join(dataRoot, 'dev_hdd0', 'home'));\n      if (!home.existsSync()) return [];\n      final paths = <String>[];\n      try {\n        for (final userDir in home.listSync(followLinks: false).whereType<Directory>()) {\n          final savedata = path.join(userDir.path, 'savedata');\n          if (Directory(savedata).existsSync()) paths.add(savedata);\n        }\n      } catch (e) {\n        NeoSyncProvider._log.w('Could not enumerate RPCS3 savedata profiles: $e');\n      }\n      return paths;\n    }\n\n''',
)

insert_before(
    resolver,
    '  bool _isMeloNXTitleId(String value) {\n',
    r'''  ({String profileId, String saveDirectory, String internalPath})?
  _parseRpcs3SaveLocation(File file, String dataRoot) {
    final relative = path.relative(file.path, from: dataRoot).replaceAll('\\', '/');
    if (relative == '..' || relative.startsWith('../')) return null;
    final segments = relative.split('/').where((part) => part.isNotEmpty).toList();
    if (segments.length < 6 ||
        segments[0].toLowerCase() != 'dev_hdd0' ||
        segments[1].toLowerCase() != 'home' ||
        segments[3].toLowerCase() != 'savedata') {
      return null;
    }
    if (segments.any((part) => part == '.' || part == '..')) return null;
    return (
      profileId: segments[2],
      saveDirectory: segments[4],
      internalPath: segments.sublist(5).join('/'),
    );
  }

  String? _rpcs3TitleIdFromSaveDirectory(String value) {
    final match = RegExp(r'^([A-Za-z]{4}[0-9]{5})').firstMatch(value.trim());
    return match?.group(1)?.toUpperCase();
  }

  Future<({String cloudPath, String gameName, String titleId})?>
  _resolveRpcs3FileForCloud(
    File file,
    String dataRoot, {
    GameModel? preferredGame,
  }) async {
    final location = _parseRpcs3SaveLocation(file, dataRoot);
    if (location == null) return null;

    var saveTitleId = _rpcs3TitleIdFromSaveDirectory(location.saveDirectory);
    String? sfoTitle;
    final sfo = File(path.join(
      dataRoot,
      'dev_hdd0',
      'home',
      location.profileId,
      'savedata',
      location.saveDirectory,
      'PARAM.SFO',
    ));
    if (sfo.existsSync()) {
      try {
        final values = Rpcs3LibraryService.parseParamSfoBytes(await sfo.readAsBytes());
        final sfoId = values['TITLE_ID']?.toString().trim() ?? '';
        if ((saveTitleId == null || saveTitleId.isEmpty) && sfoId.isNotEmpty) {
          saveTitleId = sfoId.toUpperCase();
        }
        sfoTitle = values['TITLE']?.toString().trim();
      } catch (e) {
        NeoSyncProvider._log.w('Could not parse RPCS3 save PARAM.SFO: $e');
      }
    }

    String? preferredTitleId = preferredGame?.titleId?.trim().toUpperCase();
    if (preferredGame != null && (preferredTitleId == null || preferredTitleId.isEmpty)) {
      final dbId = await GameRepository.getTitleIdForGame(
        preferredGame.romname,
        preferredGame.name,
      );
      preferredTitleId = dbId?.trim().toUpperCase();
      preferredTitleId ??= _rpcs3TitleIdFromSaveDirectory(preferredGame.romname);
    }

    if (preferredGame != null &&
        preferredTitleId != null &&
        preferredTitleId.isNotEmpty &&
        saveTitleId != null &&
        saveTitleId.isNotEmpty &&
        preferredTitleId != saveTitleId) {
      return null;
    }

    final cached = Rpcs3LibraryService.cachedGameForTitleId(saveTitleId);
    var canonicalName = cached?.title.trim() ?? '';
    if (canonicalName.isEmpty) canonicalName = sfoTitle ?? '';
    if (canonicalName.isEmpty) canonicalName = saveTitleId ?? location.saveDirectory;

    if (preferredGame != null &&
        (preferredTitleId == null || preferredTitleId.isEmpty)) {
      final expected = <String>{
        CloudPathBuilder.sanitizeGameName(preferredGame.name).toLowerCase(),
        if (preferredGame.titleName != null && preferredGame.titleName!.trim().isNotEmpty)
          CloudPathBuilder.sanitizeGameName(preferredGame.titleName!).toLowerCase(),
      };
      final actual = CloudPathBuilder.sanitizeGameName(canonicalName).toLowerCase();
      if (!expected.contains(actual)) return null;
    }

    final gameName = preferredGame?.name.trim().isNotEmpty == true
        ? preferredGame!.name.trim()
        : canonicalName;
    final cloudPath = CloudPathBuilder.build(
      system: 'ps3',
      emulatorSlug: 'rpcs3',
      scope: 'game',
      gameName: gameName,
      filePath:
          '${location.profileId}/${location.saveDirectory}/${location.internalPath}',
      isState: false,
    );
    return (
      cloudPath: cloudPath,
      gameName: gameName,
      titleId: saveTitleId ?? '',
    );
  }

  String? _resolveRpcs3CloudFileToLocal(String dataRoot, String cloudFilePath) {
    final segments = cloudFilePath
        .replaceAll('\\', '/')
        .split('/')
        .where((part) => part.isNotEmpty)
        .toList();
    if (segments.length < 3 ||
        segments.any((part) => part == '.' || part == '..')) {
      return null;
    }
    final profileId = segments[0];
    final saveDirectory = segments[1];
    final internal = segments.sublist(2).join(Platform.pathSeparator);
    return path.join(
      dataRoot,
      'dev_hdd0',
      'home',
      profileId,
      'savedata',
      saveDirectory,
      internal,
    );
  }

''',
)

replace_once(
    resolver,
    "      } else if (v2Path.emulatorSlug == 'melonx') {\n",
    "      } else if (v2Path.emulatorSlug == 'rpcs3') {\n"
    "        final root = Rpcs3LibraryService.linkedDataPath;\n"
    "        if (root != null && root.isNotEmpty) {\n"
    "          final local = _resolveRpcs3CloudFileToLocal(root, v2Path.filePath);\n"
    "          return local == null ? [] : [local];\n"
    "        }\n"
    "      } else if (v2Path.emulatorSlug == 'melonx') {\n",
)

# -----------------------------------------------------------------------------
# Upload: scan RPCS3 native save-data tree and upload each constituent file.
# -----------------------------------------------------------------------------
upload = 'lib/providers/neosync/neosync_upload.dart'
replace_once(
    upload,
    '''        if (melonxRoot != null && Directory(melonxRoot).existsSync()) {\n          for (final file in await _getSaveFiles(melonxRoot)) {\n            customSaveFiles.add((\n              file: file,\n              root: melonxRoot,\n              system: 'switch',\n              emulatorSlug: 'melonx',\n              isState: false,\n            ));\n          }\n        }\n      }\n''',
    '''        if (melonxRoot != null && Directory(melonxRoot).existsSync()) {\n          for (final file in await _getSaveFiles(melonxRoot)) {\n            customSaveFiles.add((\n              file: file,\n              root: melonxRoot,\n              system: 'switch',\n              emulatorSlug: 'melonx',\n              isState: false,\n            ));\n          }\n        }\n\n        final rpcs3Root = Rpcs3LibraryService.linkedDataPath;\n        if (rpcs3Root != null && Directory(rpcs3Root).existsSync()) {\n          final home = Directory(path.join(rpcs3Root, 'dev_hdd0', 'home'));\n          if (home.existsSync()) {\n            for (final userDir in home.listSync(followLinks: false).whereType<Directory>()) {\n              final savedata = Directory(path.join(userDir.path, 'savedata'));\n              if (!savedata.existsSync()) continue;\n              for (final file in await _getSaveFiles(savedata.path)) {\n                customSaveFiles.add((\n                  file: file,\n                  root: rpcs3Root,\n                  system: 'ps3',\n                  emulatorSlug: 'rpcs3',\n                  isState: false,\n                ));\n              }\n            }\n          }\n        }\n      }\n''',
)

replace_once(
    upload,
    '''      if (customSystem == 'switch' && customEmulatorSlug == 'melonx') {\n        await _uploadMeloNXFile(file, basePath);\n        return;\n      }\n\n''',
    '''      if (customSystem == 'switch' && customEmulatorSlug == 'melonx') {\n        await _uploadMeloNXFile(file, basePath);\n        return;\n      }\n\n      if (customSystem == 'ps3' && customEmulatorSlug == 'rpcs3') {\n        await _uploadRpcs3File(file, basePath);\n        return;\n      }\n\n''',
)

insert_before(
    upload,
    '  /// Uploads one MeloNX file using Title ID only to identify the local game.\n',
    '''  /// Uploads one constituent file from a native RPCS3 PS3 save-data folder.\n  /// The technical PS3 profile/save directory is preserved in the cloud path,\n  /// while NeoSync exposes the human-readable game title.\n  Future<bool> _uploadRpcs3File(\n    File file,\n    String dataRoot, {\n    GameModel? preferredGame,\n  }) async {\n    final resolved = await _resolveRpcs3FileForCloud(\n      file,\n      dataRoot,\n      preferredGame: preferredGame,\n    );\n    if (resolved == null) {\n      _skippedFiles++;\n      return false;\n    }\n\n    final result = await _neoSyncService.syncFile(\n      file,\n      resolved.gameName,\n      customFilename: resolved.cloudPath,\n      systemId: 'ps3',\n      emulatorId: 'rpcs3',\n      isState: false,\n      scope: 'game',\n    );\n\n    if (result['success'] == true) {\n      if (result['skipped'] == true) {\n        _skippedFiles++;\n      } else {\n        _uploadedFiles++;\n        _resetQuotaAttempts();\n      }\n      _processedItems.add('NeoSync RPCS3: ${resolved.gameName}');\n      return true;\n    }\n\n    final errorMessage = result['message']?.toString() ?? '';\n    _processedItems.add('Failed to upload ${resolved.gameName}: $errorMessage');\n    if (_checkQuotaExceeded(errorMessage)) {\n      _quotaExceededActive = true;\n      throw QuotaExceededException(errorMessage, _quotaExceededAttempts);\n    }\n    return false;\n  }\n\n''',
)

# -----------------------------------------------------------------------------
# Per-game sync: identify native PS3 save folders by Title ID and use RPCS3 path.
# -----------------------------------------------------------------------------
core = 'lib/providers/neosync/neosync_core.dart'
replace_once(
    core,
    '''      final armsx2ScanRoot =\n          Platform.isIOS && system.folderName.toLowerCase() == 'ps2'\n          ? ConfigService.linkedArmsx2SaveFolderPath\n          : null;\n''',
    '''      final armsx2ScanRoot =\n          Platform.isIOS && system.folderName.toLowerCase() == 'ps2'\n          ? ConfigService.linkedArmsx2SaveFolderPath\n          : null;\n      final rpcs3ScanRoot =\n          Platform.isIOS && system.folderName.toLowerCase() == 'ps3'\n          ? Rpcs3LibraryService.linkedDataPath\n          : null;\n''',
)
replace_once(
    core,
    '''                  final inArmsx2Root =\n                      armsx2ScanRoot != null &&\n                      (path.isWithin(armsx2ScanRoot, file.path) ||\n                          path.equals(armsx2ScanRoot, file.parent.path));\n                  return inArmsx2Root || size <= maxFileSize;\n''',
    '''                  final inArmsx2Root =\n                      armsx2ScanRoot != null &&\n                      (path.isWithin(armsx2ScanRoot, file.path) ||\n                          path.equals(armsx2ScanRoot, file.parent.path));\n                  final inRpcs3Root =\n                      rpcs3ScanRoot != null &&\n                      (path.isWithin(rpcs3ScanRoot, file.path) ||\n                          path.equals(rpcs3ScanRoot, file.parent.path));\n                  return inArmsx2Root || inRpcs3Root || size <= maxFileSize;\n''',
)

replace_once(
    core,
    '''          if (isSharedSystem) {\n            final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n''',
    '''          final rpcs3Root = Rpcs3LibraryService.linkedDataPath;\n          if (Platform.isIOS &&\n              system.folderName.toLowerCase() == 'ps3' &&\n              rpcs3Root != null &&\n              rpcs3Root.isNotEmpty &&\n              path.isWithin(rpcs3Root, file.path)) {\n            final rpcs3 = await _resolveRpcs3FileForCloud(\n              file,\n              rpcs3Root,\n              preferredGame: game,\n            );\n            isMatch = rpcs3 != null;\n          } else if (isSharedSystem) {\n            final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n''',
)

replace_once(
    core,
    '''            String relativePath;\n            final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n            if (Platform.isIOS &&\n                system.folderName.toLowerCase() == 'ps2' &&\n''',
    '''            String relativePath;\n            final rpcs3Root = Rpcs3LibraryService.linkedDataPath;\n            final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n            if (Platform.isIOS &&\n                system.folderName.toLowerCase() == 'ps3' &&\n                rpcs3Root != null &&\n                rpcs3Root.isNotEmpty &&\n                path.isWithin(rpcs3Root, file.path)) {\n              final rpcs3 = await _resolveRpcs3FileForCloud(\n                file,\n                rpcs3Root,\n                preferredGame: game,\n              );\n              if (rpcs3 == null) continue;\n              relativePath = rpcs3.cloudPath;\n            } else if (Platform.isIOS &&\n                system.folderName.toLowerCase() == 'ps2' &&\n''',
)

replace_once(
    core,
    '''      final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n      if (Platform.isIOS &&\n          system.folderName.toLowerCase() == 'ps2' &&\n''',
    '''      final rpcs3Root = Rpcs3LibraryService.linkedDataPath;\n      if (Platform.isIOS &&\n          system.folderName.toLowerCase() == 'ps3' &&\n          rpcs3Root != null &&\n          rpcs3Root.isNotEmpty &&\n          path.isWithin(rpcs3Root, file.path)) {\n        return await _uploadRpcs3File(file, rpcs3Root, preferredGame: game);\n      }\n\n      final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n      if (Platform.isIOS &&\n          system.folderName.toLowerCase() == 'ps2' &&\n''',
)

# Explicit cloud matching for RPCS3 before the existing MeloNX name mapping.
replace_once(
    core,
    '''        } else {\n          final parsed = CloudPathBuilder.parse(cloudFile.fileName);\n          if (system.folderName.toLowerCase() == 'switch' &&\n''',
    '''        } else {\n          final parsed = CloudPathBuilder.parse(cloudFile.fileName);\n          if (system.folderName.toLowerCase() == 'ps3' &&\n              parsed?.emulatorSlug == 'rpcs3' &&\n              parsed?.gameName != null) {\n            var expectedTitleId = game.titleId?.trim().toUpperCase();\n            if (expectedTitleId == null || expectedTitleId.isEmpty) {\n              expectedTitleId = (await GameRepository.getTitleIdForGame(\n                game.romname,\n                game.name,\n              ))?.trim().toUpperCase();\n            }\n            final parts = parsed!.filePath.split('/');\n            final cloudSaveDirectory = parts.length >= 2 ? parts[1] : '';\n            final cloudTitleId = _rpcs3TitleIdFromSaveDirectory(cloudSaveDirectory);\n            final expectedNames = <String>{\n              CloudPathBuilder.sanitizeGameName(game.name).toLowerCase(),\n              if (game.titleName != null && game.titleName!.trim().isNotEmpty)\n                CloudPathBuilder.sanitizeGameName(game.titleName!).toLowerCase(),\n            };\n            final cloudGameName = parsed.gameName!.toLowerCase();\n            if ((expectedTitleId != null &&\n                    expectedTitleId.isNotEmpty &&\n                    cloudTitleId == expectedTitleId) ||\n                expectedNames.contains(cloudGameName)) {\n              isMatch = true;\n            }\n          }\n\n          if (!isMatch &&\n              system.folderName.toLowerCase() == 'switch' &&\n''',
)

# -----------------------------------------------------------------------------
# Download: direct RPCS3 restore path + cloud-to-game fallback.
# -----------------------------------------------------------------------------
download = 'lib/providers/neosync/neosync_download.dart'
insert_before(
    download,
    '      // 1. Resolve the game associated with the file\n',
    '''      if (Platform.isIOS && parsed?.emulatorSlug == 'rpcs3') {\n        final root = Rpcs3LibraryService.linkedDataPath;\n        if (root == null || root.isEmpty) return;\n        final localPath = _resolveRpcs3CloudFileToLocal(root, parsed!.filePath);\n        if (localPath == null) return;\n        final localFile = File(localPath);\n        if (localFile.existsSync()) {\n          final stat = await localFile.stat();\n          if (cloudFile.checksum != null && cloudFile.checksum!.isNotEmpty) {\n            final hash = _neoSyncService.calculateFileHash(await localFile.readAsBytes());\n            if (hash == cloudFile.checksum) {\n              _skippedFiles++;\n              return;\n            }\n          }\n          final cloudTime = cloudFile.fileModifiedAtTimestamp ?? 0;\n          if (cloudTime <= stat.modified.millisecondsSinceEpoch) {\n            _skippedFiles++;\n            return;\n          }\n        } else {\n          await localFile.parent.create(recursive: true);\n        }\n        await _downloadCloudFileImpl(cloudFile, localFile);\n        _downloadedFiles++;\n        _processedItems.add('RPCS3 restored: ${cloudFile.gameName}');\n        return;\n      }\n\n''',
)

replace_once(
    download,
    '''  Future<GameModel?> _findGameForCloudFile(NeoSyncFile cloudFile) async {\n    final v2Path = CloudPathBuilder.parse(cloudFile.fileName);\n    if (v2Path != null &&\n        v2Path.emulatorSlug == 'melonx' &&\n''',
    '''  Future<GameModel?> _findGameForCloudFile(NeoSyncFile cloudFile) async {\n    final v2Path = CloudPathBuilder.parse(cloudFile.fileName);\n    if (v2Path != null &&\n        v2Path.emulatorSlug == 'rpcs3' &&\n        v2Path.gameName != null) {\n      final parts = v2Path.filePath.split('/');\n      final saveDirectory = parts.length >= 2 ? parts[1] : '';\n      final titleId = _rpcs3TitleIdFromSaveDirectory(saveDirectory) ?? '';\n      final cached = Rpcs3LibraryService.cachedGameForTitleId(titleId);\n      final displayName = cached?.title.trim().isNotEmpty == true\n          ? cached!.title.trim()\n          : (cloudFile.gameName.trim().isNotEmpty\n                ? cloudFile.gameName.trim()\n                : v2Path.gameName!);\n      return GameModel(\n        name: displayName,\n        realname: displayName,\n        romname: titleId.isNotEmpty ? titleId : displayName,\n        systemFolderName: 'ps3',\n        systemId: 'ps3',\n        year: '',\n        developer: '',\n        publisher: '',\n        genre: '',\n        players: '',\n        rating: 0.0,\n      ).copyWith(titleId: titleId.isEmpty ? null : titleId);\n    }\n\n    if (v2Path != null &&\n        v2Path.emulatorSlug == 'melonx' &&\n''',
)

print('RPCS3 iOS NeoSync patch applied')
