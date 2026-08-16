import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/repositories/system_repository.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

enum ICloudImportTarget { melonx, armsx2, retroarch }

extension ICloudImportTargetLabel on ICloudImportTarget {
  String get label => switch (this) {
    ICloudImportTarget.melonx => 'MeloNX',
    ICloudImportTarget.armsx2 => 'ARMSX2',
    ICloudImportTarget.retroarch => 'RetroArch',
  };
}

class ICloudLibraryItem {
  const ICloudLibraryItem({
    required this.system,
    required this.sourcePath,
    required this.relativePath,
    required this.target,
  });

  final SystemModel system;
  final String sourcePath;
  final String relativePath;
  final ICloudImportTarget target;

  String get filename => path.basename(sourcePath);
}

/// iOS iCloud Drive ROM library support.
///
/// The linked folder is a remote catalogue. ROMs are not copied into
/// NeoStation's permanent ROM directory. A selected file is copied only into
/// the application cache so iOS can hand it to the appropriate emulator.
class ICloudLibraryService {
  ICloudLibraryService._();

  static const String bookmarkKey = 'icloud_library';
  static const String switchFolderName = 'switch';

  static bool isSwitchFolder(String folderName) =>
      folderName.trim().toLowerCase() == switchFolderName;

  /// Switch is deliberately the only hard non-recursive iCloud exception.
  static bool shouldRecurse(String folderName) => !isSwitchFolder(folderName);

  static ICloudImportTarget targetForSystem(String folderName) {
    final normalized = folderName.trim().toLowerCase();
    if (normalized == switchFolderName) return ICloudImportTarget.melonx;
    if (normalized == 'ps2') return ICloudImportTarget.armsx2;
    return ICloudImportTarget.retroarch;
  }

  static Future<String?> resolveLinkedFolder() {
    return ExternalFolderAccess.resolveBookmarkedFolder(key: bookmarkKey);
  }

  static Future<String?> chooseFolder() {
    return ExternalFolderAccess.pickAndBookmarkFolder(key: bookmarkKey);
  }

  static Future<void> forgetFolder() {
    return ExternalFolderAccess.clearBookmark(key: bookmarkKey);
  }

  static Future<List<ICloudLibraryItem>> scan(String rootPath) async {
    final root = Directory(rootPath);
    if (!await root.exists()) return const [];

    final systems = await SystemRepository.getAllSystems();
    final lookup = <String, SystemModel>{};
    for (final system in systems) {
      if (system.isVirtual) continue;
      lookup[system.folderName.toLowerCase()] = system;
      for (final alias in system.folders) {
        if (alias.trim().isNotEmpty) lookup[alias.toLowerCase()] = system;
      }
    }

    final items = <ICloudLibraryItem>[];
    final rootName = path.basename(path.normalize(rootPath)).toLowerCase();
    final directSystem = lookup[rootName];
    if (directSystem != null) {
      await _scanSystemDirectory(
        directory: root,
        system: directSystem,
        rootPath: rootPath,
        output: items,
      );
    } else {
      await for (final entity in root.list(recursive: false, followLinks: false)) {
        if (entity is! Directory) continue;
        final name = path.basename(entity.path).toLowerCase();
        final system = lookup[name];
        if (system == null) continue;
        await _scanSystemDirectory(
          directory: entity,
          system: system,
          rootPath: rootPath,
          output: items,
        );
      }
    }

    items.sort((a, b) {
      final systemCompare = a.system.realName.compareTo(b.system.realName);
      if (systemCompare != 0) return systemCompare;
      return a.relativePath.toLowerCase().compareTo(b.relativePath.toLowerCase());
    });
    return items;
  }

  static Future<void> _scanSystemDirectory({
    required Directory directory,
    required SystemModel system,
    required String rootPath,
    required List<ICloudLibraryItem> output,
  }) async {
    final allowedExtensions = system.extensions
        .map((value) => value.toLowerCase().replaceFirst(RegExp(r'^\.'), ''))
        .where((value) => value.isNotEmpty)
        .toSet();
    if (allowedExtensions.isEmpty) return;

    final recursive = shouldRecurse(system.folderName);
    await for (final entity in directory.list(
      recursive: recursive,
      followLinks: false,
    )) {
      if (entity is! File) continue;
      final filename = path.basename(entity.path);
      if (filename.startsWith('.')) continue;
      final extension = path
          .extension(filename)
          .toLowerCase()
          .replaceFirst(RegExp(r'^\.'), '');
      if (!allowedExtensions.contains(extension)) continue;

      output.add(
        ICloudLibraryItem(
          system: system,
          sourcePath: entity.path,
          relativePath: path.relative(entity.path, from: rootPath),
          target: targetForSystem(system.folderName),
        ),
      );
    }
  }

  /// Materializes one selected iCloud file into NeoStation's temporary cache.
  /// Reading/copying the security-scoped file causes iOS File Provider/iCloud
  /// Drive to fetch its contents when the item is not already local.
  static Future<String> materializeForImport(ICloudLibraryItem item) async {
    final source = File(item.sourcePath);
    if (!await source.exists()) {
      throw FileSystemException('iCloud ROM is unavailable', item.sourcePath);
    }

    final tempRoot = Directory(
      path.join((await getTemporaryDirectory()).path, 'neostation_icloud_import'),
    );
    await tempRoot.create(recursive: true);

    // Keep the cache bounded to the current transfer only.
    await for (final entity in tempRoot.list(followLinks: false)) {
      try {
        await entity.delete(recursive: true);
      } catch (_) {}
    }

    final targetDir = Directory(
      path.join(tempRoot.path, item.system.folderName.toLowerCase()),
    );
    await targetDir.create(recursive: true);
    final targetPath = path.join(targetDir.path, item.filename);
    await source.copy(targetPath);
    return targetPath;
  }
}
