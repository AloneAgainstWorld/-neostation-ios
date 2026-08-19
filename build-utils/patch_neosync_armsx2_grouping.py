#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:160]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def insert_before(path: str, marker: str, block: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if block in text:
        return
    if marker not in text:
        raise SystemExit(f'Insert marker not found in {path}: {marker[:160]!r}')
    p.write_text(text.replace(marker, block + marker, 1), encoding='utf-8')


# ---------------------------------------------------------------------------
# ARMSX2: only sync memcards / savestates / sstates from the selected iOS root.
# ---------------------------------------------------------------------------
upload = 'lib/providers/neosync/neosync_upload.dart'
old = '''      final customSaveFiles =
          <({File file, String root, String system, String emulatorSlug})>[];
      if (Platform.isIOS) {
        final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;
        if (armsx2Root != null && Directory(armsx2Root).existsSync()) {
          for (final file in await _getSaveFiles(armsx2Root)) {
            customSaveFiles.add((
              file: file,
              root: armsx2Root,
              system: 'ps2',
              emulatorSlug: 'armsx2',
            ));
          }
        }
        final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;
        if (melonxRoot != null && Directory(melonxRoot).existsSync()) {
          for (final file in await _getSaveFiles(melonxRoot)) {
            customSaveFiles.add((
              file: file,
              root: melonxRoot,
              system: 'switch',
              emulatorSlug: 'melonx',
            ));
          }
        }
      }'''
new = '''      final customSaveFiles =
          <({
            File file,
            String root,
            String system,
            String emulatorSlug,
            bool isState,
          })>[];
      if (Platform.isIOS) {
        final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;
        if (armsx2Root != null && Directory(armsx2Root).existsSync()) {
          const categories = <String>['memcards', 'savestates', 'sstates'];
          final selectedName = path.basename(armsx2Root).toLowerCase();
          final roots = <({String folder, String category})>[];

          if (categories.contains(selectedName)) {
            roots.add((folder: armsx2Root, category: selectedName));
          } else {
            for (final category in categories) {
              final folder = path.join(armsx2Root, category);
              if (Directory(folder).existsSync()) {
                roots.add((folder: folder, category: category));
              }
            }
          }

          for (final rootInfo in roots) {
            final isState = rootInfo.category != 'memcards';
            for (final file in await _getSaveFiles(rootInfo.folder)) {
              customSaveFiles.add((
                file: file,
                root: armsx2Root,
                system: 'ps2',
                emulatorSlug: 'armsx2',
                isState: isState,
              ));
            }
          }
        }
        final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;
        if (melonxRoot != null && Directory(melonxRoot).existsSync()) {
          for (final file in await _getSaveFiles(melonxRoot)) {
            customSaveFiles.add((
              file: file,
              root: melonxRoot,
              system: 'switch',
              emulatorSlug: 'melonx',
              isState: false,
            ));
          }
        }
      }'''
replace_once(upload, old, new)

replace_once(
    upload,
    '''          isState: false,\n          customSystem: entry.system,''',
    '''          isState: entry.isState,\n          customSystem: entry.system,''',
)

replace_once(
    upload,
    '''      if (customSystem == 'switch' && customEmulatorSlug == 'melonx') {\n        await _uploadMeloNXFile(file, basePath);\n        return;\n      }''',
    '''      if (customSystem == 'ps2' && customEmulatorSlug == 'armsx2') {\n        await _uploadArmsx2File(file, basePath);\n        return;\n      }\n\n      if (customSystem == 'switch' && customEmulatorSlug == 'melonx') {\n        await _uploadMeloNXFile(file, basePath);\n        return;\n      }''',
)

armsx2_upload_method = r'''  /// Uploads ARMSX2 memory cards and states from the three supported iOS
  /// folders. The rest of the ARMSX2 root (BIOS, cache, covers, logs, etc.) is
  /// deliberately excluded from NeoSync.
  Future<bool> _uploadArmsx2File(File file, String root) async {
    final resolved = _resolveArmsx2FileForCloud(file, root);
    if (resolved == null) {
      _skippedFiles++;
      return false;
    }

    final result = await _neoSyncService.syncFile(
      file,
      resolved.gameName,
      customFilename: resolved.cloudPath,
      systemId: 'ps2',
      emulatorId: 'armsx2',
      isState: resolved.isState,
      scope: 'shared',
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
    _processedItems.add('Failed to upload ${resolved.gameName}: $errorMessage');
    if (_checkQuotaExceeded(errorMessage)) {
      _quotaExceededActive = true;
      throw QuotaExceededException(errorMessage, _quotaExceededAttempts);
    }
    return false;
  }

'''
insert_before(upload, '  /// Uploads one MeloNX file using Title ID only to identify the local game.\n', armsx2_upload_method)


# ---------------------------------------------------------------------------
# Shared resolver for ARMSX2 local <-> cloud paths.
# ---------------------------------------------------------------------------
resolver = 'lib/providers/neosync/neosync_path_resolver.dart'
armsx2_resolver_block = r'''  ({String cloudPath, String gameName, bool isState, String category})?
  _resolveArmsx2FileForCloud(File file, String root) {
    const categories = <String>['memcards', 'savestates', 'sstates'];
    final relative = path.relative(file.path, from: root).replaceAll('\\', '/');
    if (relative == '..' || relative.startsWith('../')) return null;

    final rootName = path.basename(root).toLowerCase();
    final segments = relative
        .split('/')
        .where((part) => part.isNotEmpty)
        .toList();
    if (segments.isEmpty) return null;

    late final String category;
    late final String internalPath;
    if (categories.contains(rootName)) {
      category = rootName;
      internalPath = segments.join('/');
    } else {
      final candidate = segments.first.toLowerCase();
      if (!categories.contains(candidate) || segments.length < 2) return null;
      category = candidate;
      internalPath = segments.sublist(1).join('/');
    }

    final isState = category != 'memcards';
    final gameName = isState ? 'ARMSX2 Save States' : 'ARMSX2 Memory Cards';
    final cloudPath = CloudPathBuilder.build(
      system: 'ps2',
      emulatorSlug: 'armsx2',
      scope: 'shared',
      filePath: '$category/$internalPath',
      isState: isState,
    );
    return (
      cloudPath: cloudPath,
      gameName: gameName,
      isState: isState,
      category: category,
    );
  }

  String? _resolveArmsx2CloudFileToLocal(String root, String cloudFilePath) {
    const categories = <String>['memcards', 'savestates', 'sstates'];
    final segments = cloudFilePath
        .replaceAll('\\', '/')
        .split('/')
        .where((part) => part.isNotEmpty)
        .toList();
    if (segments.isEmpty) return null;

    final rootName = path.basename(root).toLowerCase();
    final category = segments.first.toLowerCase();
    if (!categories.contains(category)) {
      // Compatibility with the first iOS preview which stored paths relative
      // to the chosen folder without a category prefix.
      return path.join(root, cloudFilePath);
    }

    final internalPath = segments.length > 1
        ? segments.sublist(1).join(Platform.pathSeparator)
        : '';
    if (internalPath.isEmpty) return null;

    if (categories.contains(rootName)) {
      if (rootName != category) return null;
      return path.join(root, internalPath);
    }
    return path.join(root, category, internalPath);
  }

'''
insert_before(resolver, '  bool _isMeloNXTitleId(String value) =>\n', armsx2_resolver_block)

replace_once(
    resolver,
    '''      if (v2Path.emulatorSlug == 'armsx2') {\n        final root = ConfigService.linkedArmsx2SaveFolderPath;\n        if (root != null && root.isNotEmpty) {\n          return [path.join(root, v2Path.filePath)];\n        }\n      }''',
    '''      if (v2Path.emulatorSlug == 'armsx2') {\n        final root = ConfigService.linkedArmsx2SaveFolderPath;\n        if (root != null && root.isNotEmpty) {\n          final local = _resolveArmsx2CloudFileToLocal(root, v2Path.filePath);\n          return local == null ? [] : [local];\n        }\n      }''',
)


# ---------------------------------------------------------------------------
# Per-game sync path: make ARMSX2 files use the same canonical cloud paths.
# ---------------------------------------------------------------------------
core = 'lib/providers/neosync/neosync_core.dart'
replace_once(
    core,
    '''      // MeloNX on iOS stores saves below a Title-ID directory. Use that ID\n      // only for local matching, while the cloud keeps the readable game name.\n      final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;''',
    '''      final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n      if (Platform.isIOS &&\n          system.folderName.toLowerCase() == 'ps2' &&\n          armsx2Root != null &&\n          armsx2Root.isNotEmpty &&\n          path.isWithin(armsx2Root, file.path)) {\n        return await _uploadArmsx2File(file, armsx2Root);\n      }\n\n      // MeloNX on iOS stores saves below a Title-ID directory. Use that ID\n      // only for local matching, while the cloud keeps the readable game name.\n      final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;''',
)

# Give ARMSX2 files first-class matching before the old PS2 .ps2-only rule.
replace_once(
    core,
    '''          if (isSharedSystem) {\n            // Para sistemas compartidos, cualquier archivo de save/state válido es un match\n            // PS2: .ps2, DC: vmu_save\n            if (system.folderName == 'ps2' && fileName.endsWith('.ps2')) {\n              isMatch = true;''',
    '''          if (isSharedSystem) {\n            final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n            if (Platform.isIOS &&\n                system.folderName.toLowerCase() == 'ps2' &&\n                armsx2Root != null &&\n                armsx2Root.isNotEmpty &&\n                path.isWithin(armsx2Root, file.path) &&\n                _resolveArmsx2FileForCloud(file, armsx2Root) != null) {\n              isMatch = true;\n            } else if (system.folderName == 'ps2' &&\n                fileName.endsWith('.ps2')) {\n              isMatch = true;''',
)

replace_once(
    core,
    '''            String relativePath;\n            final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;''',
    '''            String relativePath;\n            final armsx2Root = ConfigService.linkedArmsx2SaveFolderPath;\n            if (Platform.isIOS &&\n                system.folderName.toLowerCase() == 'ps2' &&\n                armsx2Root != null &&\n                armsx2Root.isNotEmpty &&\n                path.isWithin(armsx2Root, file.path)) {\n              final armsx2 = _resolveArmsx2FileForCloud(file, armsx2Root);\n              if (armsx2 == null) continue;\n              relativePath = armsx2.cloudPath;\n            } else {\n              final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;''',
)

# Close the new ARMSX2 else around the existing MeloNX/generic resolver block.
replace_once(
    core,
    '''              relativePath = _calculateRelativePath(\n                file,\n                basePath,\n                isState: isState,\n              );\n            }\n\n            matchingFiles.add(''',
    '''              relativePath = _calculateRelativePath(\n                file,\n                basePath,\n                isState: isState,\n              );\n            }\n            }\n\n            matchingFiles.add(''',
)

# Cloud-side PS2 matching should include all canonical ARMSX2 shared saves/states,
# not only filenames ending in .ps2.
replace_once(
    core,
    '''        if (isSharedSystem) {\n          // Para sistemas compartidos, filtrar estrictamente por sistema\n          if (system.folderName == 'ps2' && fileName.endsWith('.ps2')) {\n            isMatch = true;''',
    '''        if (isSharedSystem) {\n          // Para sistemas compartidos, filtrar estrictamente por sistema\n          final parsed = CloudPathBuilder.parse(cloudFile.fileName);\n          if (system.folderName.toLowerCase() == 'ps2' &&\n              parsed?.emulatorSlug == 'armsx2' &&\n              parsed?.isShared == true) {\n            isMatch = true;\n          } else if (system.folderName == 'ps2' &&\n              fileName.endsWith('.ps2')) {\n            isMatch = true;''',
)


# ---------------------------------------------------------------------------
# UI: group multi-file logical saves by game/emulator instead of one row/file.
# ---------------------------------------------------------------------------
ui = 'lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart'

group_methods = r'''  List<_OnlineSaveGroup> _groupedOnlineSaves(NeoSyncProvider provider) {
    final buckets = <String, List<NeoSyncFile>>{};
    final labels = <String, String>{};

    for (final file in provider.onlineFiles) {
      final lowerPath = file.fileName.toLowerCase();
      final isMeloNX =
          lowerPath.startsWith('v2/saves/switch/melonx/game/') ||
          lowerPath.startsWith('v2/states/switch/melonx/game/');
      final isArmsx2Save = lowerPath.startsWith('v2/saves/ps2/armsx2/');
      final isArmsx2State = lowerPath.startsWith('v2/states/ps2/armsx2/');

      String key;
      String label;
      if (isMeloNX) {
        label = file.gameName.trim().isNotEmpty
            ? file.gameName.trim()
            : _readableGameNameFromV2Path(file.fileName);
        key = 'melonx:${label.toLowerCase()}';
      } else if (isArmsx2Save || isArmsx2State) {
        label = file.gameName.trim().isNotEmpty
            ? file.gameName.trim()
            : (isArmsx2State
                  ? 'ARMSX2 Save States'
                  : 'ARMSX2 Memory Cards');
        key = 'armsx2:${isArmsx2State ? 'states' : 'saves'}:${label.toLowerCase()}';
      } else {
        label = file.id.startsWith('v1:') ? '[V1] ${file.fileName}' : file.fileName;
        key = 'file:${file.id}';
      }

      buckets.putIfAbsent(key, () => <NeoSyncFile>[]).add(file);
      labels[key] = label;
    }

    return [
      for (final entry in buckets.entries)
        _OnlineSaveGroup(files: entry.value, displayName: labels[entry.key]!),
    ];
  }

  String _readableGameNameFromV2Path(String cloudPath) {
    final parts = cloudPath.split('/');
    return parts.length > 5 ? parts[5] : cloudPath;
  }

'''
insert_before(ui, '  void _resetSelection() {\n', group_methods)

replace_once(
    ui,
    '''    if (neoSyncProvider.onlineFiles.isNotEmpty) {\n      final newIndex = _selectedSaveIndex > 0\n          ? _selectedSaveIndex - 1\n          : neoSyncProvider.onlineFiles.length - 1;\n      _updateSelectionIndex(newIndex);\n    }''',
    '''    final groups = _groupedOnlineSaves(neoSyncProvider);\n    if (groups.isNotEmpty) {\n      final newIndex = _selectedSaveIndex > 0\n          ? _selectedSaveIndex - 1\n          : groups.length - 1;\n      _updateSelectionIndex(newIndex);\n    }''',
)

replace_once(
    ui,
    '''    if (neoSyncProvider.onlineFiles.isNotEmpty) {\n      final newIndex =\n          (_selectedSaveIndex + 1) % neoSyncProvider.onlineFiles.length;\n      _updateSelectionIndex(newIndex);\n    }''',
    '''    final groups = _groupedOnlineSaves(neoSyncProvider);\n    if (groups.isNotEmpty) {\n      final newIndex = (_selectedSaveIndex + 1) % groups.length;\n      _updateSelectionIndex(newIndex);\n    }''',
)

# Replace the selected-file/delete block with grouped deletion.
old_select = '''    if (neoSyncProvider.onlineFiles.isNotEmpty &&
        _selectedSaveIndex < neoSyncProvider.onlineFiles.length) {
      final selectedFile = neoSyncProvider.onlineFiles[_selectedSaveIndex];

      bool disableNeoSync = false; // Estado del checkbox, por defecto false

      final confirmed = await _showDeleteDialog(selectedFile, (value) {
        disableNeoSync = value;
      });

      if (confirmed == true) {
        // Si el usuario marcó el checkbox, desactivar NeoSync para este juego
        if (disableNeoSync) {
          try {
            // Buscar el sistema y filename del juego usando el gameName
            final systemFolderName =
                await GameRepository.getSystemFolderForGame(
                  selectedFile.gameName,
                );
            if (systemFolderName != null) {
              await GameRepository.updateCloudSyncEnabled(
                systemFolderName,
                selectedFile.gameName,
                false,
              );
            }
          } catch (e) {
            // Mostrar error pero continuar con la eliminación
            if (!mounted) return;
            custom.AppNotification.showNotification(
              context,
              AppLocale.failedToDisableNeoSync.getString(context),
              type: custom.NotificationType.error,
            );
          }
        }

        final success = await neoSyncProvider.deleteOnlineFile(selectedFile.id);
        if (success) {
          // Ajustar índice seleccionado si es necesario después de eliminar
          final remainingFiles = neoSyncProvider.onlineFiles.length - 1;
          if (_selectedSaveIndex >= remainingFiles && remainingFiles > 0) {
            setState(() {
              _selectedSaveIndex = remainingFiles - 1;
            });
          } else if (remainingFiles == 0) {
            setState(() {
              _selectedSaveIndex = 0;
            });
          }

          // Actualizar el quota después de eliminar el archivo
          await neoSyncProvider.loadQuota();
          // Show success message
          if (!mounted) return;
          custom.AppNotification.showNotification(
            context,
            AppLocale.saveFileDeleted.getString(context),
            type: custom.NotificationType.success,
          );
        } else {
          // Show error message
          if (!mounted) return;
          custom.AppNotification.showNotification(
            context,
            AppLocale.failedToDeleteSave.getString(context),
            type: custom.NotificationType.error,
          );
        }
      }
    } else {}'''
new_select = '''    final groups = _groupedOnlineSaves(neoSyncProvider);
    if (groups.isNotEmpty && _selectedSaveIndex < groups.length) {
      final selectedGroup = groups[_selectedSaveIndex];
      final selectedFile = selectedGroup.primaryFile;

      bool disableNeoSync = false;
      final confirmed = await _showDeleteDialog(selectedGroup, (value) {
        disableNeoSync = value;
      });

      if (confirmed == true) {
        if (disableNeoSync) {
          try {
            final systemFolderName = await GameRepository.getSystemFolderForGame(
              selectedFile.gameName,
            );
            if (systemFolderName != null) {
              await GameRepository.updateCloudSyncEnabled(
                systemFolderName,
                selectedFile.gameName,
                false,
              );
            }
          } catch (e) {
            if (!mounted) return;
            custom.AppNotification.showNotification(
              context,
              AppLocale.failedToDisableNeoSync.getString(context),
              type: custom.NotificationType.error,
            );
          }
        }

        var success = true;
        for (final file in selectedGroup.files) {
          final deleted = await neoSyncProvider.deleteOnlineFile(file.id);
          if (!deleted) success = false;
        }

        if (success) {
          final remainingGroups = _groupedOnlineSaves(neoSyncProvider).length;
          if (mounted) {
            setState(() {
              if (remainingGroups == 0) {
                _selectedSaveIndex = 0;
              } else if (_selectedSaveIndex >= remainingGroups) {
                _selectedSaveIndex = remainingGroups - 1;
              }
            });
          }

          await neoSyncProvider.loadQuota();
          if (!mounted) return;
          custom.AppNotification.showNotification(
            context,
            AppLocale.saveFileDeleted.getString(context),
            type: custom.NotificationType.success,
          );
        } else {
          if (!mounted) return;
          custom.AppNotification.showNotification(
            context,
            AppLocale.failedToDeleteSave.getString(context),
            type: custom.NotificationType.error,
          );
        }
      }
    }'''
replace_once(ui, old_select, new_select)

replace_once(
    ui,
    '''  Future<bool?> _showDeleteDialog(\n    NeoSyncFile file,\n    Function(bool) onDisableNeoSyncChanged,\n  ) async {''',
    '''  Future<bool?> _showDeleteDialog(\n    _OnlineSaveGroup group,\n    Function(bool) onDisableNeoSyncChanged,\n  ) async {''',
)
replace_once(ui, '          file: file,\n', '          file: group.displayFile,\n')

# Build column from grouped entries.
replace_once(
    ui,
    '''      builder: (context, neoSyncProvider, child) {\n        return Container(''',
    '''      builder: (context, neoSyncProvider, child) {\n        final groups = _groupedOnlineSaves(neoSyncProvider);\n        return Container(''',
)
replace_once(ui, ': neoSyncProvider.onlineFiles.isEmpty\n', ': groups.isEmpty\n')
replace_once(ui, '                        files: neoSyncProvider.onlineFiles,\n', '                        groups: groups,\n')
replace_once(ui, '                        onDeleteRequest: (file, index) async {\n', '                        onDeleteRequest: (group, index) async {\n')

# Add compact logical-save model before the list widget.
group_class = r'''class _OnlineSaveGroup {
  final List<NeoSyncFile> files;
  final String displayName;

  const _OnlineSaveGroup({required this.files, required this.displayName});

  NeoSyncFile get primaryFile => files.first;
  int get totalBytes => files.fold(0, (sum, file) => sum + file.fileSize);
  DateTime get newestAt => files
      .map((file) => file.uploadedAt)
      .reduce((a, b) => a.isAfter(b) ? a : b);

  String get sizeFormatted {
    final bytes = totalBytes;
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  String get subtitle {
    final date = newestAt.toLocal().toString().split(' ')[0];
    return files.length > 1
        ? '${files.length}× • $sizeFormatted • $date'
        : '$sizeFormatted • $date';
  }

  NeoSyncFile get displayFile => NeoSyncFile(
    id: primaryFile.id,
    fileName: displayName,
    filePath: primaryFile.filePath,
    fileSize: totalBytes,
    gameName: primaryFile.gameName,
    uploadedAt: newestAt,
    fileModifiedAt: primaryFile.fileModifiedAt,
    fileModifiedAtTimestamp: primaryFile.fileModifiedAtTimestamp,
    userId: primaryFile.userId,
    checksum: primaryFile.checksum,
  );
}

'''
insert_before(ui, 'class OnlineSavesListView extends StatefulWidget {\n', group_class)

replace_once(ui, '  final List<NeoSyncFile> files;\n', '  final List<_OnlineSaveGroup> groups;\n')
replace_once(ui, '  final Function(NeoSyncFile, int) onDeleteRequest;\n', '  final Function(_OnlineSaveGroup, int) onDeleteRequest;\n')
replace_once(ui, '    required this.files,\n', '    required this.groups,\n')

# Every widget.files reference below belongs to OnlineSavesListView.
p = Path(ui)
text = p.read_text(encoding='utf-8')
text = text.replace('widget.files.length', 'widget.groups.length')
text = text.replace('widget.files[index]', 'widget.groups[index]')
text = text.replace('  Widget _buildOnlineSaveItem(\n    BuildContext context,\n    NeoSyncFile file,\n    int index,\n  ) {',
                    '  Widget _buildOnlineSaveItem(\n    BuildContext context,\n    _OnlineSaveGroup group,\n    int index,\n  ) {')
text = text.replace("                    file.id.startsWith('v1:')\n                        ? '[V1] ${file.fileName}'\n                        : file.fileName,",
                    '                    group.displayName,')
text = text.replace("                    '${file.fileSizeFormatted} • ${file.uploadedAt.toLocal().toString().split(' ')[0]}',",
                    '                    group.subtitle,')
text = text.replace('            onPressed: () => widget.onDeleteRequest(file, index),',
                    '            onPressed: () => widget.onDeleteRequest(group, index),')
p.write_text(text, encoding='utf-8')

print('NeoSync ARMSX2 + grouped online-save patch applied')
