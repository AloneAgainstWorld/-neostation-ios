#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'Marker not found in {path}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# ---------------------------------------------------------------------------
# AppConfig: retain a read bridge to the historical v1 backend.
# ---------------------------------------------------------------------------
replace_once(
    'lib/utils/app_config.dart',
    "  static const String neoSyncBaseUrl = 'https://sync.neosync.cloud';\n",
    "  static const String neoSyncBaseUrl = 'https://sync.neosync.cloud';\n\n"
    "  /// Historical NeoSync v1 endpoint. Read/migration compatibility only.\n"
    "  static const String legacyNeoSyncBaseUrl =\n"
    "      'https://neosync.neogamelab.com';\n",
)

# ---------------------------------------------------------------------------
# iOS bookmark state: keep library roots and save roots independent.
# ---------------------------------------------------------------------------
replace_once(
    'lib/services/config_service.dart',
    "  static String? linkedArmsx2FolderPath;\n",
    "  static String? linkedArmsx2FolderPath;\n\n"
    "  /// iOS-only NeoSync save roots. These bookmarks are intentionally\n"
    "  /// separate from ROM/library folders so cloud-save configuration never\n"
    "  /// changes game discovery or launch paths.\n"
    "  static const String armsx2NeoSyncBookmarkKey = 'neosync-armsx2-saves';\n"
    "  static const String melonxNeoSyncBookmarkKey = 'neosync-melonx-saves';\n"
    "  static String? linkedArmsx2SaveFolderPath;\n"
    "  static String? linkedMelonxSaveFolderPath;\n",
)

replace_once(
    'lib/main.dart',
    "    ConfigService.linkedArmsx2FolderPath =\n"
    "        await ExternalFolderAccess.resolveBookmarkedFolder(key: 'armsx2');\n",
    "    ConfigService.linkedArmsx2FolderPath =\n"
    "        await ExternalFolderAccess.resolveBookmarkedFolder(key: 'armsx2');\n\n"
    "    // NeoSync save roots are independent from emulator library roots.\n"
    "    ConfigService.linkedArmsx2SaveFolderPath =\n"
    "        await ExternalFolderAccess.resolveBookmarkedFolder(\n"
    "          key: ConfigService.armsx2NeoSyncBookmarkKey,\n"
    "        );\n"
    "    ConfigService.linkedMelonxSaveFolderPath =\n"
    "        await ExternalFolderAccess.resolveBookmarkedFolder(\n"
    "          key: ConfigService.melonxNeoSyncBookmarkKey,\n"
    "        );\n",
)

# ---------------------------------------------------------------------------
# Provider graph: v2 primary + read-only v1 compatibility service.
# ---------------------------------------------------------------------------
replace_once(
    'lib/providers/neo_sync_provider.dart',
    "import '../services/neosync/neo_sync_service.dart';\n",
    "import '../services/neosync/neo_sync_service.dart';\n"
    "import '../services/neosync/legacy_neo_sync_service.dart';\n",
)
replace_once(
    'lib/providers/neo_sync_provider.dart',
    "  final NeoSyncService _neoSyncService;\n\n  NeoSyncProvider(this._neoSyncService);\n",
    "  final NeoSyncService _neoSyncService;\n"
    "  final LegacyNeoSyncService _legacyNeoSyncService = LegacyNeoSyncService();\n\n"
    "  NeoSyncProvider(this._neoSyncService);\n",
)

# ---------------------------------------------------------------------------
# Online list: v2 first, migrate recognizable v1 files non-destructively, keep
# unresolved v1 files visible with their v1: IDs.
# ---------------------------------------------------------------------------
Path('lib/providers/neosync/neosync_status.dart').write_text(r'''part of '../neo_sync_provider.dart';

extension NeoSyncStatus on NeoSyncProvider {
  Future<bool> loadFiles() async {
    if (!isNeoSyncAuthenticated) return false;

    _isLoadingOnlineFiles = true;
    _error = null;
    notify();

    try {
      final result = await _neoSyncService.getFiles();
      if (result['success'] == true) {
        _files = (result['files'] as List<NeoSyncFile>?) ?? <NeoSyncFile>[];
        notify();
        return true;
      }
      _error = result['message']?.toString();
      notify();
      return false;
    } catch (e) {
      _error = 'Error loading files: $e';
      notify();
      return false;
    } finally {
      _isLoadingOnlineFiles = false;
      notify();
    }
  }

  Future<bool> loadQuota() async {
    if (!isNeoSyncAuthenticated) return false;
    try {
      final result = await _neoSyncService.getQuota();
      if (result['success'] == true) {
        _quota = result['quota'] as NeoSyncQuota;
        notify();
        return true;
      }
      NeoSyncProvider._log.e('Failed to load quota: ${result['message']}');
      return false;
    } catch (e) {
      NeoSyncProvider._log.e('Error loading quota: $e');
      return false;
    }
  }

  Future<bool> deleteFile(NeoSyncFile file) async {
    if (!isNeoSyncAuthenticated) return false;
    try {
      final result = LegacyNeoSyncService.isLegacyId(file.id)
          ? await _legacyNeoSyncService.deleteFile(file.id)
          : await _neoSyncService.deleteFile(file.id);
      if (result['success'] == true) {
        _files.removeWhere((f) => f.id == file.id);
        _onlineFiles.removeWhere((f) => f.id == file.id);
        notify();
        return true;
      }
      return false;
    } catch (_) {
      return false;
    }
  }

  /// Loads v2 files and also probes the historical v1 account. Recognizable v1
  /// files are copied into v2 without deleting their originals. Any legacy file
  /// that cannot be mapped safely remains visible as a `[V1]` entry in the UI.
  Future<void> loadOnlineFiles() async {
    _isLoadingOnlineFiles = true;
    notify();

    try {
      final v2Result = await _neoSyncService.getFiles();
      var v2Files = v2Result['success'] == true
          ? ((v2Result['files'] as List<NeoSyncFile>?) ?? <NeoSyncFile>[])
          : <NeoSyncFile>[];

      final legacyResult = await _legacyNeoSyncService.getFiles();
      final legacyFiles = legacyResult['success'] == true
          ? ((legacyResult['files'] as List<NeoSyncFile>?) ?? <NeoSyncFile>[])
          : <NeoSyncFile>[];

      Set<String> migratedLegacyIds = <String>{};
      if (legacyFiles.isNotEmpty) {
        migratedLegacyIds = await _migrateLegacyFilesToV2(legacyFiles);
        if (migratedLegacyIds.isNotEmpty) {
          final refreshed = await _neoSyncService.getFiles();
          if (refreshed['success'] == true) {
            v2Files =
                (refreshed['files'] as List<NeoSyncFile>?) ?? <NeoSyncFile>[];
          }
          final quotaResult = await _neoSyncService.getQuota();
          if (quotaResult['success'] == true) {
            _quota = quotaResult['quota'] as NeoSyncQuota;
          }
        }
      }

      final unresolvedLegacy = legacyFiles
          .where((file) => !migratedLegacyIds.contains(file.id))
          .toList();
      _onlineFiles = <NeoSyncFile>[...v2Files, ...unresolvedLegacy]
        ..sort((a, b) => b.uploadedAt.compareTo(a.uploadedAt));

      if (legacyFiles.isNotEmpty) {
        NeoSyncProvider._log.i(
          'NeoSync v1 bridge: ${legacyFiles.length} found, '
          '${migratedLegacyIds.length} copied to v2, '
          '${unresolvedLegacy.length} kept as legacy entries',
        );
      }
    } catch (e) {
      NeoSyncProvider._log.e('Error loading online files: $e');
      _onlineFiles = <NeoSyncFile>[];
    } finally {
      _isLoadingOnlineFiles = false;
      notify();
    }
  }

  Future<bool> deleteOnlineFile(String fileId) async {
    try {
      final result = LegacyNeoSyncService.isLegacyId(fileId)
          ? await _legacyNeoSyncService.deleteFile(fileId)
          : await _neoSyncService.deleteFile(fileId);
      if (result['success'] == true) {
        _onlineFiles.removeWhere((file) => file.id == fileId);
        notify();
        return true;
      }
      NeoSyncProvider._log.e(
        'Failed to delete online file: ${result['message']}',
      );
      return false;
    } catch (e) {
      NeoSyncProvider._log.e('Error deleting online file: $e');
      return false;
    }
  }
}
''', encoding='utf-8')

# ---------------------------------------------------------------------------
# V1 -> V2 migration and routed legacy download. Migration never deletes v1.
# ---------------------------------------------------------------------------
replace_once(
    'lib/providers/neosync/neosync_download.dart',
    "    final result = await _neoSyncService.downloadFile(cloudFile.id);\n",
    "    final result = LegacyNeoSyncService.isLegacyId(cloudFile.id)\n"
    "        ? await _legacyNeoSyncService.downloadFile(cloudFile.id)\n"
    "        : await _neoSyncService.downloadFile(cloudFile.id);\n",
)

download_path = Path('lib/providers/neosync/neosync_download.dart')
download_text = download_path.read_text(encoding='utf-8')
legacy_method_marker = '  Future<Set<String>> _migrateLegacyFilesToV2('
if legacy_method_marker not in download_text:
    insertion = r'''

  /// Copies recognizable NeoSync v1 files into the v2 namespace.
  ///
  /// This is intentionally non-destructive: the historical object remains in
  /// v1. Files that cannot be mapped to a local game/emulator are skipped and
  /// remain visible through the legacy bridge.
  Future<Set<String>> _migrateLegacyFilesToV2(
    List<NeoSyncFile> legacyFiles,
  ) async {
    final migrated = <String>{};

    for (final legacyFile in legacyFiles) {
      if (!LegacyNeoSyncService.isLegacyId(legacyFile.id)) continue;
      Directory? tempDir;
      try {
        final game = await _findGameForCloudFile(legacyFile);
        final system = game?.systemFolderName?.trim();
        final emulatorId = game?.emulatorName?.trim();
        if (game == null ||
            system == null ||
            system.isEmpty ||
            emulatorId == null ||
            emulatorId.isEmpty) {
          continue;
        }

        final emulatorSlug = CloudPathBuilder.slugFromEmulatorUniqueId(
          emulatorId,
        );
        if (emulatorSlug.isEmpty || emulatorSlug == 'standalone') continue;

        final downloaded = await _legacyNeoSyncService.downloadFile(
          legacyFile.id,
        );
        if (downloaded['success'] != true || downloaded['data'] == null) {
          continue;
        }

        final bytes = downloaded['data'] as List<int>;
        final fileName = path.basename(legacyFile.fileName);
        if (fileName.isEmpty) continue;
        final lowerName = fileName.toLowerCase();
        final systemLower = system.toLowerCase();
        final isState = legacyFile.fileName.startsWith('states/');
        final isShared =
            (systemLower == 'ps2' && lowerName.endsWith('.ps2')) ||
            ((systemLower == 'dc' || systemLower == 'dreamcast') &&
                lowerName.contains('vmu_save'));

        final v2Name = CloudPathBuilder.build(
          system: system,
          emulatorSlug: emulatorSlug,
          scope: isShared ? 'shared' : 'game',
          gameName: isShared
              ? null
              : path.basenameWithoutExtension(legacyFile.fileName),
          filePath: fileName,
          isState: isState,
        );

        tempDir = await Directory.systemTemp.createTemp('neosync-v1-migrate-');
        final tempFile = File(path.join(tempDir.path, fileName));
        await tempFile.parent.create(recursive: true);
        await tempFile.writeAsBytes(bytes, flush: true);
        try {
          await tempFile.setLastModified(
            legacyFile.fileModifiedAt ?? legacyFile.uploadedAt,
          );
        } catch (_) {}

        final result = await _neoSyncService.syncFile(
          tempFile,
          game.name,
          customFilename: v2Name,
          systemId: system,
          emulatorId: emulatorSlug,
          isState: isState,
          scope: isShared ? 'shared' : 'game',
        );
        if (result['success'] == true) {
          migrated.add(legacyFile.id);
        }
      } catch (e) {
        NeoSyncProvider._log.w(
          'NeoSync v1 migration skipped ${legacyFile.fileName}: $e',
        );
      } finally {
        if (tempDir != null) {
          try {
            await tempDir.delete(recursive: true);
          } catch (_) {}
        }
      }
    }

    return migrated;
  }
'''
    idx = download_text.rfind('\n}')
    if idx < 0:
        raise SystemExit('Could not find NeoSyncDownload extension end')
    download_text = download_text[:idx] + insertion + download_text[idx:]
    download_path.write_text(download_text, encoding='utf-8')

# ---------------------------------------------------------------------------
# iOS custom save roots in universal path resolution and v2 restore routing.
# ---------------------------------------------------------------------------
replace_once(
    'lib/providers/neosync/neosync_path_resolver.dart',
    "    if (Platform.isIOS && folders.isEmpty) {\n"
    "      final saves = await _getRetroArchSavesPath();\n"
    "      final states = await _getRetroArchStatesPath();\n"
    "      if (saves != null) resolvedPaths.add(saves);\n"
    "      if (states != null) resolvedPaths.add(states);\n"
    "    }\n",
    "    if (Platform.isIOS && folders.isEmpty) {\n"
    "      final saves = await _getRetroArchSavesPath();\n"
    "      final states = await _getRetroArchStatesPath();\n"
    "      if (saves != null) resolvedPaths.add(saves);\n"
    "      if (states != null) resolvedPaths.add(states);\n"
    "    }\n\n"
    "    if (Platform.isIOS) {\n"
    "      final systemFolder = system.folderName.toLowerCase();\n"
    "      if (systemFolder == 'ps2') {\n"
    "        final custom = ConfigService.linkedArmsx2SaveFolderPath;\n"
    "        if (custom != null && custom.isNotEmpty) resolvedPaths.add(custom);\n"
    "      } else if (systemFolder == 'switch') {\n"
    "        final custom = ConfigService.linkedMelonxSaveFolderPath;\n"
    "        if (custom != null && custom.isNotEmpty) resolvedPaths.add(custom);\n"
    "      }\n"
    "    }\n",
)

replace_once(
    'lib/providers/neosync/neosync_path_resolver.dart',
    "    final isSave = v2Path != null\n"
    "        ? !v2Path.isState\n"
    "        : cloudFile.fileName.startsWith('saves/');\n\n"
    "    // Buscar la carpeta más apropiada.\n",
    "    final isSave = v2Path != null\n"
    "        ? !v2Path.isState\n"
    "        : cloudFile.fileName.startsWith('saves/');\n\n"
    "    if (Platform.isIOS && v2Path != null) {\n"
    "      if (v2Path.emulatorSlug == 'armsx2') {\n"
    "        final root = ConfigService.linkedArmsx2SaveFolderPath;\n"
    "        if (root != null && root.isNotEmpty) {\n"
    "          return [path.join(root, v2Path.filePath)];\n"
    "        }\n"
    "      } else if (v2Path.emulatorSlug == 'melonx') {\n"
    "        final root = ConfigService.linkedMelonxSaveFolderPath;\n"
    "        if (root != null && root.isNotEmpty) {\n"
    "          return [path.join(root, v2Path.filePath)];\n"
    "        }\n"
    "      }\n"
    "    }\n\n"
    "    // Buscar la carpeta más apropiada.\n",
)

# ---------------------------------------------------------------------------
# Auto-upload custom ARMSX2/MeloNX save roots. Their relative folder structure
# is preserved under a shared v2 namespace so restore is lossless.
# ---------------------------------------------------------------------------
replace_once(
    'lib/providers/neosync/neosync_upload.dart',
    "      final statesPath = await _getRetroArchStatesPath();\n"
    "      List<File> retroArchStates = [];\n"
    "      if (statesPath != null) {\n"
    "        retroArchStates = await _getSaveFiles(statesPath);\n"
    "      }\n\n"
    "      // 2. Collect Switch NAND files\n",
    "      final statesPath = await _getRetroArchStatesPath();\n"
    "      List<File> retroArchStates = [];\n"
    "      if (statesPath != null) {\n"
    "        retroArchStates = await _getSaveFiles(statesPath);\n"
    "      }\n\n"
    "      final customSaveFiles =\n"
    "          <({File file, String root, String system, String emulatorSlug})>[];\n"
    "      if (Platform.isIOS) {\n"
    "        final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n"
    "        if (armsx2Root != null && Directory(armsx2Root).existsSync()) {\n"
    "          for (final file in await _getSaveFiles(armsx2Root)) {\n"
    "            customSaveFiles.add((\n"
    "              file: file,\n"
    "              root: armsx2Root,\n"
    "              system: 'ps2',\n"
    "              emulatorSlug: 'armsx2',\n"
    "            ));\n"
    "          }\n"
    "        }\n"
    "        final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;\n"
    "        if (melonxRoot != null && Directory(melonxRoot).existsSync()) {\n"
    "          for (final file in await _getSaveFiles(melonxRoot)) {\n"
    "            customSaveFiles.add((\n"
    "              file: file,\n"
    "              root: melonxRoot,\n"
    "              system: 'switch',\n"
    "              emulatorSlug: 'melonx',\n"
    "            ));\n"
    "          }\n"
    "        }\n"
    "      }\n\n"
    "      // 2. Collect Switch NAND files\n",
)

replace_once(
    'lib/providers/neosync/neosync_upload.dart',
    "      if (saveFiles.isEmpty) {\n",
    "      if (retroArchSaves.isEmpty &&\n"
    "          retroArchStates.isEmpty &&\n"
    "          customSaveFiles.isEmpty &&\n"
    "          saveFiles.isEmpty) {\n",
)
replace_once(
    'lib/providers/neosync/neosync_upload.dart',
    "          retroArchStates.length +\n"
    "          saveFiles.length; // saveFiles contains Switch files here\n",
    "          retroArchStates.length +\n"
    "          customSaveFiles.length +\n"
    "          saveFiles.length; // saveFiles contains Switch files here\n",
)
replace_once(
    'lib/providers/neosync/neosync_upload.dart',
    "      // Process the rest (Switch, etc.)\n",
    "      // Process iOS standalone-emulator save roots.\n"
    "      for (final entry in customSaveFiles) {\n"
    "        await _processAutoUploadFile(\n"
    "          entry.file,\n"
    "          entry.root,\n"
    "          isState: false,\n"
    "          customSystem: entry.system,\n"
    "          customEmulatorSlug: entry.emulatorSlug,\n"
    "        );\n"
    "        _processedFiles++;\n"
    "        _syncProgress = _totalFiles > 0 ? _processedFiles / _totalFiles : 0.0;\n"
    "        notify();\n"
    "      }\n\n"
    "      // Process the rest (Switch, etc.)\n",
)
replace_once(
    'lib/providers/neosync/neosync_upload.dart',
    "  Future<void> _processAutoUploadFile(\n"
    "    File file,\n"
    "    String basePath, {\n"
    "    bool isState = false,\n"
    "  }) async {\n",
    "  Future<void> _processAutoUploadFile(\n"
    "    File file,\n"
    "    String basePath, {\n"
    "    bool isState = false,\n"
    "    String? customSystem,\n"
    "    String? customEmulatorSlug,\n"
    "  }) async {\n",
)

replace_once(
    'lib/providers/neosync/neosync_upload.dart',
    "      final game = await _gameForSaveFile(file);\n",
    "      if (customSystem != null && customEmulatorSlug != null) {\n"
    "        final relativeFile = path\n"
    "            .relative(file.path, from: basePath)\n"
    "            .replaceAll('\\\\', '/');\n"
    "        if (relativeFile.startsWith('..')) {\n"
    "          _skippedFiles++;\n"
    "          return;\n"
    "        }\n"
    "        final cloudPath = CloudPathBuilder.build(\n"
    "          system: customSystem,\n"
    "          emulatorSlug: customEmulatorSlug,\n"
    "          scope: 'shared',\n"
    "          filePath: relativeFile,\n"
    "          isState: isState,\n"
    "        );\n"
    "        final result = await _neoSyncService.syncFile(\n"
    "          file,\n"
    "          _extractGameNameFromPath(file.path),\n"
    "          customFilename: cloudPath,\n"
    "          systemId: customSystem,\n"
    "          emulatorId: customEmulatorSlug,\n"
    "          isState: isState,\n"
    "          scope: 'shared',\n"
    "        );\n"
    "        if (result['success'] == true) {\n"
    "          if (result['skipped'] == true) {\n"
    "            _skippedFiles++;\n"
    "          } else {\n"
    "            _uploadedFiles++;\n"
    "            _resetQuotaAttempts();\n"
    "          }\n"
    "          _processedItems.add('NeoSync: $cloudPath');\n"
    "        } else {\n"
    "          final errorMessage = result['message']?.toString() ?? '';\n"
    "          _processedItems.add('Failed to upload: $cloudPath - $errorMessage');\n"
    "          if (_checkQuotaExceeded(errorMessage)) {\n"
    "            _quotaExceededActive = true;\n"
    "            throw QuotaExceededException(errorMessage, _quotaExceededAttempts);\n"
    "          }\n"
    "        }\n"
    "        return;\n"
    "      }\n\n"
    "      final game = await _gameForSaveFile(file);\n",
)

# ---------------------------------------------------------------------------
# Settings UI: save-folder pickers are separate from library synchronization.
# Resolve the bookmark immediately after picking so security-scoped access stays
# active for the rest of the session.
# ---------------------------------------------------------------------------
replace_once(
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    "      final selected = await ExternalFolderAccess.pickAndBookmarkFolder(\n"
    "        key: bookmarkKey,\n"
    "      );\n"
    "      if (selected == null || !mounted) return;\n\n"
    "      ConfigService.linkedExternalFolderPath = selected;\n",
    "      final selected = await ExternalFolderAccess.pickAndBookmarkFolder(\n"
    "        key: bookmarkKey,\n"
    "      );\n"
    "      if (selected == null || !mounted) return;\n"
    "      final resolved = await ExternalFolderAccess.resolveBookmarkedFolder(\n"
    "        key: bookmarkKey,\n"
    "      );\n"
    "      final activePath = resolved ?? selected;\n\n"
    "      ConfigService.linkedExternalFolderPath = activePath;\n",
)
replace_once(
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    "      await configProvider.addRomFolder(selected, scan: true);\n",
    "      await configProvider.addRomFolder(activePath, scan: true);\n",
)

settings_path = Path(
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart'
)
settings_text = settings_path.read_text(encoding='utf-8')
if 'Future<void> _linkNeoSyncSaveFolder' not in settings_text:
    marker = "  Future<void> _syncWithRetroArch() async {\n"
    method = r'''  Future<void> _linkNeoSyncSaveFolder({
    required String bookmarkKey,
    required String emulatorName,
  }) async {
    if (_linkingFolderKey != null) return;
    setState(() => _linkingFolderKey = bookmarkKey);
    try {
      final selected = await ExternalFolderAccess.pickAndBookmarkFolder(
        key: bookmarkKey,
      );
      if (selected == null || !mounted) return;
      final resolved = await ExternalFolderAccess.resolveBookmarkedFolder(
        key: bookmarkKey,
      );
      final activePath = resolved ?? selected;
      if (bookmarkKey == ConfigService.armsx2NeoSyncBookmarkKey) {
        ConfigService.linkedArmsx2SaveFolderPath = activePath;
      } else if (bookmarkKey == ConfigService.melonxNeoSyncBookmarkKey) {
        ConfigService.linkedMelonxSaveFolderPath = activePath;
      }
      if (mounted) setState(() {});
      _log.i('NeoSync $emulatorName save folder linked: $activePath');
    } catch (e) {
      _log.e('NeoSync $emulatorName save-folder link failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          AppLocale.iosEmuLinkingFailed
              .getString(context)
              .replaceFirst('{error}', e.toString()),
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) setState(() => _linkingFolderKey = null);
    }
  }

'''
    if marker not in settings_text:
        raise SystemExit('RetroArch sync marker not found in settings')
    settings_text = settings_text.replace(marker, method + marker, 1)
    settings_path.write_text(settings_text, encoding='utf-8')

replace_once(
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    "  /// ARMSX2 is sync-only, like MeloNX. Its exported library is authoritative\n"
    "  /// for PS2 discovery and does not require a user-selected folder.\n"
    "  Widget _buildIOSArmsx2Section(ThemeData theme) {\n"
    "    final hasSynced = Armsx2LibraryService.hasSyncedLibrary;\n",
    "  Widget _buildIOSArmsx2Section(ThemeData theme) {\n"
    "    final hasSynced = Armsx2LibraryService.hasSyncedLibrary;\n"
    "    final isSaveLinked = ConfigService.linkedArmsx2SaveFolderPath != null;\n",
)
replace_once(
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    "      isLinked: true,\n"
    "      bookmarkKey: ExternalFolderAccess.defaultBookmarkKey,\n"
    "      successMessage: '',\n"
    "      showLinkButton: false,\n"
    "      trailingAction: Row(\n",
    "      isLinked: isSaveLinked,\n"
    "      bookmarkKey: ConfigService.armsx2NeoSyncBookmarkKey,\n"
    "      successMessage: '',\n"
    "      onLinkPressed: () => _linkNeoSyncSaveFolder(\n"
    "        bookmarkKey: ConfigService.armsx2NeoSyncBookmarkKey,\n"
    "        emulatorName: 'ARMSX2',\n"
    "      ),\n"
    "      trailingAction: Row(\n",
)
replace_once(
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    "  Widget _buildIOSMeloNXSection(ThemeData theme) {\n"
    "    final hasSynced = MelonxLibraryService.hasSyncedLibrary;\n",
    "  Widget _buildIOSMeloNXSection(ThemeData theme) {\n"
    "    final hasSynced = MelonxLibraryService.hasSyncedLibrary;\n"
    "    final isSaveLinked = ConfigService.linkedMelonxSaveFolderPath != null;\n",
)
replace_once(
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    "      isLinked: true,\n"
    "      bookmarkKey: ExternalFolderAccess.defaultBookmarkKey,\n"
    "      successMessage: '',\n"
    "      showLinkButton: false,\n"
    "      trailingAction: Row(\n",
    "      isLinked: isSaveLinked,\n"
    "      bookmarkKey: ConfigService.melonxNeoSyncBookmarkKey,\n"
    "      successMessage: '',\n"
    "      onLinkPressed: () => _linkNeoSyncSaveFolder(\n"
    "        bookmarkKey: ConfigService.melonxNeoSyncBookmarkKey,\n"
    "        emulatorName: 'MeloNX',\n"
    "      ),\n"
    "      trailingAction: Row(\n",
)

# ---------------------------------------------------------------------------
# Make unresolved legacy objects explicit in the online list.
# ---------------------------------------------------------------------------
replace_once(
    'lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart',
    "                  child: Text(\n"
    "                    file.fileName,\n"
    "                    maxLines: 1,\n",
    "                  child: Text(\n"
    "                    file.id.startsWith('v1:')\n"
    "                        ? '[V1] ${file.fileName}'\n"
    "                        : file.fileName,\n"
    "                    maxLines: 1,\n",
)

print('Complete NeoSync iOS integration patch applied')
