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


# ---------------------------------------------------------------------------
# NeoSync service: allow content-hash-only uploads for stale-mtime containers,
# and return useful errors when the backend sends a non-JSON response (e.g. 413).
# ---------------------------------------------------------------------------
service = 'lib/services/neosync/neo_sync_service.dart'
replace_once(
    service,
    '''    bool? isState,\n    String? scope,\n  }) async {''',
    '''    bool? isState,\n    String? scope,\n    bool contentHashOnly = false,\n  }) async {''',
)
replace_once(
    service,
    '''        localModifiedAt: localModifiedAt,\n      );''',
    '''        localModifiedAt: contentHashOnly ? null : localModifiedAt,\n      );''',
)
replace_once(
    service,
    '''      if (checkResult['remote_newer']) {''',
    '''      if (checkResult['remote_newer'] && !contentHashOnly) {''',
)
replace_once(
    service,
    '''      final fileModifiedAtTimestamp = localModifiedAt.millisecondsSinceEpoch;''',
    '''      final fileModifiedAtTimestamp = contentHashOnly\n          ? DateTime.now().millisecondsSinceEpoch\n          : localModifiedAt.millisecondsSinceEpoch;''',
)
replace_once(
    service,
    '''      final response = await request.send();\n      final responseBody = await response.stream.bytesToString();\n      final data = jsonDecode(responseBody);\n\n      if (response.statusCode == 200 || response.statusCode == 201) {''',
    '''      final response = await request.send();\n      final responseBody = await response.stream.bytesToString();\n      Map<String, dynamic> data = <String, dynamic>{};\n      try {\n        final decoded = jsonDecode(responseBody);\n        if (decoded is Map<String, dynamic>) data = decoded;\n      } catch (_) {\n        // Some proxies return plain text/HTML for transport errors such as 413.\n      }\n\n      if (response.statusCode == 200 || response.statusCode == 201) {''',
)
replace_once(
    service,
    '''      } else {\n        final error = data['error'] ?? 'Upload failed';\n        _log.e('Upload failed: $error');\n        return {'success': false, 'message': error};\n      }''',
    '''      } else {\n        final body = responseBody.trim();\n        final bodyPreview = body.length > 240 ? '${body.substring(0, 240)}…' : body;\n        final error =\n            data['error'] ??\n            data['message'] ??\n            (bodyPreview.isNotEmpty\n                ? 'HTTP ${response.statusCode}: $bodyPreview'\n                : 'Upload failed (HTTP ${response.statusCode})');\n        _log.e('Upload failed: $error');\n        return {'success': false, 'message': error};\n      }''',
)

# ---------------------------------------------------------------------------
# ARMSX2 canonical path: memory-card .ps2 containers are stored compressed.
# Restore strips the NeoSync-only suffix before writing into ARMSX2/memcards.
# ---------------------------------------------------------------------------
resolver = 'lib/providers/neosync/neosync_path_resolver.dart'
replace_once(
    resolver,
    '''    final isState = category != 'memcards';\n    final gameName = isState ? 'ARMSX2 Save States' : 'ARMSX2 Memory Cards';\n    final cloudPath = CloudPathBuilder.build(\n      system: 'ps2',\n      emulatorSlug: 'armsx2',\n      scope: 'shared',\n      filePath: '$category/$internalPath',\n      isState: isState,\n    );''',
    '''    final isState = category != 'memcards';\n    final gameName = isState ? 'ARMSX2 Save States' : 'ARMSX2 Memory Cards';\n    final isMemoryCardContainer =\n        category == 'memcards' && internalPath.toLowerCase().endsWith('.ps2');\n    final cloudInternalPath = isMemoryCardContainer\n        ? '$category/$internalPath.neosync.gz'\n        : '$category/$internalPath';\n    final cloudPath = CloudPathBuilder.build(\n      system: 'ps2',\n      emulatorSlug: 'armsx2',\n      scope: 'shared',\n      filePath: cloudInternalPath,\n      isState: isState,\n    );''',
)
replace_once(
    resolver,
    '''  String? _resolveArmsx2CloudFileToLocal(String root, String cloudFilePath) {\n    const categories = <String>['memcards', 'savestates', 'sstates'];\n    final segments = cloudFilePath\n        .replaceAll('\\\\', '/')''',
    '''  String? _resolveArmsx2CloudFileToLocal(String root, String cloudFilePath) {\n    const categories = <String>['memcards', 'savestates', 'sstates'];\n    var localCloudPath = cloudFilePath;\n    if (localCloudPath.toLowerCase().endsWith('.neosync.gz')) {\n      localCloudPath = localCloudPath.substring(\n        0,\n        localCloudPath.length - '.neosync.gz'.length,\n      );\n    }\n    final segments = localCloudPath\n        .replaceAll('\\\\', '/')''',
)
replace_once(
    resolver,
    '''      return path.join(root, cloudFilePath);''',
    '''      return path.join(root, localCloudPath);''',
)

# ---------------------------------------------------------------------------
# ARMSX2 upload: gzip .ps2 cards and force content-hash semantics. The visible
# card may carry an old filesystem timestamp even though its content changed.
# ---------------------------------------------------------------------------
upload = 'lib/providers/neosync/neosync_upload.dart'
old_method = '''  Future<bool> _uploadArmsx2File(File file, String root) async {\n    final resolved = _resolveArmsx2FileForCloud(file, root);\n    if (resolved == null) {\n      _skippedFiles++;\n      return false;\n    }\n\n    final result = await _neoSyncService.syncFile(\n      file,\n      resolved.gameName,\n      customFilename: resolved.cloudPath,\n      systemId: 'ps2',\n      emulatorId: 'armsx2',\n      isState: resolved.isState,\n      scope: 'shared',\n    );\n\n    if (result['success'] == true) {\n      if (result['skipped'] == true) {\n        _skippedFiles++;\n      } else {\n        _uploadedFiles++;\n        _resetQuotaAttempts();\n      }\n      _processedItems.add('NeoSync: ${resolved.gameName}');\n      return true;\n    }\n\n    final errorMessage = result['message']?.toString() ?? '';\n    _processedItems.add('Failed to upload ${resolved.gameName}: $errorMessage');\n    if (_checkQuotaExceeded(errorMessage)) {\n      _quotaExceededActive = true;\n      throw QuotaExceededException(errorMessage, _quotaExceededAttempts);\n    }\n    return false;\n  }'''
new_method = '''  Future<bool> _uploadArmsx2File(File file, String root) async {\n    final resolved = _resolveArmsx2FileForCloud(file, root);\n    if (resolved == null) {\n      _skippedFiles++;\n      return false;\n    }\n\n    final isMemoryCard =\n        resolved.category == 'memcards' &&\n        file.path.toLowerCase().endsWith('.ps2');\n    File uploadFile = file;\n    Directory? tempDir;\n\n    try {\n      if (isMemoryCard) {\n        final rawBytes = await file.readAsBytes();\n        final compressedBytes = gzip.encode(rawBytes);\n        tempDir = await Directory.systemTemp.createTemp('neosync-armsx2-card-');\n        uploadFile = File(\n          path.join(tempDir.path, '${path.basename(file.path)}.neosync.gz'),\n        );\n        await uploadFile.writeAsBytes(compressedBytes, flush: true);\n        _processedItems.add(\n          'ARMSX2 memory card detected: ${path.basename(file.path)} '\n          '(${rawBytes.length} B → ${compressedBytes.length} B)',\n        );\n      }\n\n      final result = await _neoSyncService.syncFile(\n        uploadFile,\n        resolved.gameName,\n        customFilename: resolved.cloudPath,\n        systemId: 'ps2',\n        emulatorId: 'armsx2',\n        isState: resolved.isState,\n        scope: 'shared',\n        contentHashOnly: isMemoryCard,\n      );\n\n      if (result['success'] == true) {\n        if (result['skipped'] == true) {\n          _skippedFiles++;\n        } else {\n          _uploadedFiles++;\n          _resetQuotaAttempts();\n        }\n        _processedItems.add('NeoSync: ${resolved.gameName}');\n        return true;\n      }\n\n      final errorMessage = result['message']?.toString() ?? '';\n      _processedItems.add('Failed to upload ${resolved.gameName}: $errorMessage');\n      if (_checkQuotaExceeded(errorMessage)) {\n        _quotaExceededActive = true;\n        throw QuotaExceededException(errorMessage, _quotaExceededAttempts);\n      }\n      return false;\n    } finally {\n      if (tempDir != null) {\n        try {\n          await tempDir.delete(recursive: true);\n        } catch (_) {}\n      }\n    }\n  }'''
replace_once(upload, old_method, new_method)

# ---------------------------------------------------------------------------
# Per-game status: compare compressed content hash for ARMSX2 cards, and if the
# content differs always prefer the local card. Never overwrite a live card just
# because its filesystem date is old.
# ---------------------------------------------------------------------------
core = 'lib/providers/neosync/neosync_core.dart'
replace_once(
    core,
    '''      final localBytes = await localFile.readAsBytes();\n      final localHash = _neoSyncService.calculateFileHash(localBytes);\n\n      // Comparar hashes si están disponibles\n      final cloudHash = cloudSave!.checksum;\n      final hashesMatch = cloudHash != null && localHash == cloudHash;''',
    '''      final localBytes = await localFile.readAsBytes();\n      final localHash = _neoSyncService.calculateFileHash(localBytes);\n\n      // ARMSX2 memory cards are cloud-compressed. Compare the exact gzip payload\n      // hash, and when it differs always prefer the existing local card. Its\n      // filesystem timestamp can legitimately remain years old on iOS.\n      final cloudHash = cloudSave!.checksum;\n      final isArmsx2CompressedCard =\n          cloudSave.fileName.toLowerCase().contains('/ps2/armsx2/') &&\n          cloudSave.fileName.toLowerCase().endsWith('.ps2.neosync.gz');\n      if (isArmsx2CompressedCard) {\n        final compressedHash = _neoSyncService.calculateFileHash(\n          gzip.encode(localBytes),\n        );\n        if (cloudHash != null && compressedHash == cloudHash) {\n          return neo_sync.GameSyncStatus.upToDate;\n        }\n        return neo_sync.GameSyncStatus.localOnly;\n      }\n\n      // Comparar hashes si están disponibles\n      final hashesMatch = cloudHash != null && localHash == cloudHash;''',
)

# ---------------------------------------------------------------------------
# Restore paths: decode NeoSync-compressed cards before writing. The ordinary
# provider helper and the legacy-aware download helper both need this behavior.
# ---------------------------------------------------------------------------
provider = 'lib/providers/neo_sync_provider.dart'
replace_once(
    provider,
    '''      final bytes = result['data'] as List<int>;\n      await localFile.writeAsBytes(bytes);''',
    '''      final bytes = result['data'] as List<int>;\n      final payload = cloudFile.fileName.toLowerCase().endsWith('.neosync.gz')\n          ? gzip.decode(bytes)\n          : bytes;\n      await localFile.writeAsBytes(payload);''',
)

download = 'lib/providers/neosync/neosync_download.dart'
replace_once(
    download,
    '''      final bytes = result['data'] as List<int>;\n      await localFile.writeAsBytes(bytes);''',
    '''      final bytes = result['data'] as List<int>;\n      final payload = cloudFile.fileName.toLowerCase().endsWith('.neosync.gz')\n          ? gzip.decode(bytes)\n          : bytes;\n      await localFile.writeAsBytes(payload);''',
)

# Shared ARMSX2 objects don't belong to a single game, so auto-download them
# directly through the configured bookmark. If a memory card already exists,
# never replace it automatically; local-first upload will reconcile it instead.
replace_once(
    download,
    '''    try {\n      // 1. Resolve the game associated with the file\n      GameModel? game = await _findGameForCloudFile(cloudFile);''',
    '''    try {\n      final parsed = CloudPathBuilder.parse(cloudFile.fileName);\n      if (Platform.isIOS &&\n          parsed?.emulatorSlug == 'armsx2' &&\n          parsed?.isShared == true) {\n        final root = ConfigService.linkedArmsx2SaveFolderPath;\n        if (root == null || root.isEmpty) return;\n        final localPath = _resolveArmsx2CloudFileToLocal(root, parsed!.filePath);\n        if (localPath == null) return;\n        final localFile = File(localPath);\n        final isMemoryCard = parsed.filePath.toLowerCase().startsWith('memcards/');\n        if (isMemoryCard && localFile.existsSync()) {\n          // Existing ARMSX2 cards are authoritative; stale mtimes are common.\n          _skippedFiles++;\n          return;\n        }\n        if (!localFile.existsSync()) {\n          await localFile.parent.create(recursive: true);\n          await _downloadCloudFileImpl(cloudFile, localFile);\n          _downloadedFiles++;\n        }\n        return;\n      }\n\n      // 1. Resolve the game associated with the file\n      GameModel? game = await _findGameForCloudFile(cloudFile);''',
)

print('ARMSX2 memory-card hash/compression patch applied')
