#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:180]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# 1) Shared-save cache must never be populated merely by discovering a file.
core = 'lib/providers/neosync/neosync_core.dart'
replace_once(
    core,
    '''            // Marcar como procesado si es compartido para evitar re-comprobación en esta sesión\n            if (isSharedSystem) {\n              _processedMultiEmulatorFilesInSession.add(file.path);\n            }\n''',
    '''            // Do not mark shared cards as processed while merely discovering them.\n            // The upload/check loop owns that marker after a real sync decision.\n''',
)

# Reset the shared-card cache for every fresh game detection. A PS2 memory card
# can change between two different ARMSX2 launches in the same NeoStation run.
replace_once(
    core,
    '''  Future<void> detectGameSaveFiles(GameModel game) async {\n    if (!isNeoSyncAuthenticated) {''',
    '''  Future<void> detectGameSaveFiles(GameModel game) async {\n    // A shared PS2/DC card may have changed since the previous game session.\n    // Never carry the processed marker across independent detections.\n    _processedMultiEmulatorFilesInSession.clear();\n\n    if (!isNeoSyncAuthenticated) {''',
)

# The generic detector ignores files above 10 MB. PCSX2/ARMSX2 save states can
# legitimately exceed that size, so exempt files under the dedicated iOS
# ARMSX2 bookmark only; keep the safety cap for every other emulator/path.
replace_once(
    core,
    '''      // 3. Escanear archivos en esas rutas pero en un Isolate para no bloquear la UI\n      final List<File> allFiles = [];\n      const int maxFileSize = 10 * 1024 * 1024; // 10MB\n\n      // Execute heavy listing and filtering in background\n      final List<String> filePaths = await Isolate.run(() {''',
    '''      // 3. Escanear archivos en esas rutas pero en un Isolate para no bloquear la UI\n      final List<File> allFiles = [];\n      const int maxFileSize = 10 * 1024 * 1024; // 10MB\n      final armsx2ScanRoot =\n          Platform.isIOS && system.folderName.toLowerCase() == 'ps2'\n          ? ConfigService.linkedArmsx2SaveFolderPath\n          : null;\n\n      // Execute heavy listing and filtering in background\n      final List<String> filePaths = await Isolate.run(() {''',
)
replace_once(
    core,
    '''                  final size = file.lengthSync();\n                  return size <= maxFileSize;''',
    '''                  final size = file.lengthSync();\n                  final inArmsx2Root =\n                      armsx2ScanRoot != null &&\n                      (path.isWithin(armsx2ScanRoot, file.path) ||\n                          path.equals(armsx2ScanRoot, file.parent.path));\n                  return inArmsx2Root || size <= maxFileSize;''',
)

# 2) Make iOS a first-class NeoSync platform instead of relying on the empty
# fallback that was originally added around Android/desktop-only system JSON.
model = 'lib/models/neo_sync_models.dart'
replace_once(
    model,
    '''  /// List of monitored save directories on macOS devices.\n  final List<String> macosSyncFolder;\n\n  const NeoSyncConfig({\n    required this.sync,\n    required this.androidSyncFolder,\n    required this.windowsSyncFolder,\n    required this.linuxSyncFolder,\n    required this.macosSyncFolder,\n  });''',
    '''  /// List of monitored save directories on macOS devices.\n  final List<String> macosSyncFolder;\n\n  /// List of monitored save directories on iOS devices.\n  final List<String> iosSyncFolder;\n\n  const NeoSyncConfig({\n    required this.sync,\n    required this.androidSyncFolder,\n    required this.windowsSyncFolder,\n    required this.linuxSyncFolder,\n    required this.macosSyncFolder,\n    required this.iosSyncFolder,\n  });''',
)
replace_once(
    model,
    '''      macosSyncFolder: _parseList(json['macos_sync_folder']),\n    );''',
    '''      macosSyncFolder: _parseList(json['macos_sync_folder']),\n      iosSyncFolder: _parseList(json['ios_sync_folder']),\n    );''',
)
replace_once(
    model,
    '''      'macos_sync_folder': macosSyncFolder,\n    };''',
    '''      'macos_sync_folder': macosSyncFolder,\n      'ios_sync_folder': iosSyncFolder,\n    };''',
)
replace_once(
    model,
    '''    if (Platform.isMacOS) return macosSyncFolder;\n    return [];''',
    '''    if (Platform.isMacOS) return macosSyncFolder;\n    if (Platform.isIOS) return iosSyncFolder;\n    return [];''',
)
replace_once(
    model,
    '''    macosSyncFolder: [],\n  );''',
    '''    macosSyncFolder: [],\n    iosSyncFolder: [],\n  );''',
)

# 3) Explicit PS2 iOS roots: RetroArch plus the security-scoped ARMSX2 root.
ps2 = 'assets/systems/ps2.json'
replace_once(
    ps2,
    '''    "macos_sync_folder": [\n      "{SYNC_DIR}"\n    ]\n  }''',
    '''    "macos_sync_folder": [\n      "{SYNC_DIR}"\n    ],\n    "ios_sync_folder": [\n      "{SYNC_DIR}",\n      "{ARMSX2_IOS_SAVES}"\n    ]\n  }''',
)

# 4) Resolve the explicit iOS placeholder only from the dedicated bookmark.
resolver = 'lib/providers/neosync/neosync_path_resolver.dart'
replace_once(
    resolver,
    '''    // 2. Placeholder {NETHERSX2_MEMCARDS} (AetherSX2/NetherSX2 memcards)\n    if (pathStr == '{NETHERSX2_MEMCARDS}' && Platform.isAndroid) {''',
    '''    // 2. iOS ARMSX2 NeoSync root. This never falls back to Android paths.\n    if (pathStr == '{ARMSX2_IOS_SAVES}' && Platform.isIOS) {\n      final root = ConfigService.linkedArmsx2SaveFolderPath;\n      if (root != null && root.isNotEmpty) {\n        if (!ensureExists || Directory(root).existsSync()) return [root];\n      }\n      return [];\n    }\n\n    // 3. Placeholder {NETHERSX2_MEMCARDS} (AetherSX2/NetherSX2 memcards)\n    if (pathStr == '{NETHERSX2_MEMCARDS}' && Platform.isAndroid) {''',
)

print('ARMSX2 iOS shared-card NeoSync patch applied')
