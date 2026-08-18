from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding='utf-8')
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'Marker not found in {path}: {old[:120]!r}')
    file.write_text(text.replace(old, new, 1), encoding='utf-8')


# ---------------------------------------------------------------------------
# 1. Keep RPCS3 virtual rows alive during normal filesystem rescans.
# ---------------------------------------------------------------------------
sqlite_db_path = Path('lib/data/datasources/sqlite_database_service.dart')
sqlite_db = sqlite_db_path.read_text(encoding='utf-8')
if "package:flutter/foundation.dart" not in sqlite_db:
    sqlite_db = sqlite_db.replace(
        "import 'package:path/path.dart' as path;\n",
        "import 'package:path/path.dart' as path;\n"
        "import 'package:flutter/foundation.dart';\n",
        1,
    )

cleanup_marker = """  static Future<({int removed, Set<String> knownPaths})>
  _cleanupOrphanedRomsOptimized(
"""
helper = """  /// Returns whether [romPath] belongs to an external emulator library.
  ///
  /// These rows intentionally use launch/synchronization URIs instead of local
  /// files. A physical ROM scan must never delete them; their owning emulator
  /// service removes stale rows during its own synchronization pass.
  @visibleForTesting
  static bool isPersistentExternalLibraryPath(String romPath) {
    final lowerPath = romPath.toLowerCase();
    return lowerPath.startsWith('armsx2://') ||
        lowerPath.startsWith('melonx://') ||
        lowerPath.startsWith('rpcs3-library://');
  }

  static Future<({int removed, Set<String> knownPaths})>
  _cleanupOrphanedRomsOptimized(
"""
if helper not in sqlite_db:
    if cleanup_marker not in sqlite_db:
        raise SystemExit('RPCS3 cleanup insertion marker not found')
    sqlite_db = sqlite_db.replace(cleanup_marker, helper, 1)

old_virtual_guard = """        final lowerPath = path.toLowerCase();
        if (lowerPath.startsWith('armsx2://') ||
            lowerPath.startsWith('melonx://')) {
          knownPaths.add(path);
          continue;
        }
"""
new_virtual_guard = """        if (isPersistentExternalLibraryPath(path)) {
          knownPaths.add(path);
          continue;
        }
"""
if new_virtual_guard not in sqlite_db:
    if old_virtual_guard not in sqlite_db:
        raise SystemExit('External-library cleanup guard not found')
    sqlite_db = sqlite_db.replace(old_virtual_guard, new_virtual_guard, 1)
sqlite_db_path.write_text(sqlite_db, encoding='utf-8')


# ---------------------------------------------------------------------------
# 2. Validate every downloaded ScreenScraper payload before caching it.
# ---------------------------------------------------------------------------
media_downloader = r"""import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as path;
import 'package:neostation/services/logger_service.dart';
import 'region_config.dart';
import 'rom_hasher.dart';
import 'media_resolver.dart';
import 'screenscraper_client.dart';

/// Media asset downloader for ScreenScraper.
///
/// ScreenScraper can legitimately return HTTP 200 with a small textual status
/// such as `NOMEDIA`, `CRCOK`, `MD5OK` or `SHA1OK`. Those responses must never
/// be written as PNG/MP4/PDF files. Every payload is therefore signature-checked
/// before it replaces an existing media file.
class ScreenscraperMediaDownloader {
  ScreenscraperMediaDownloader._();

  static final _log = LoggerService.instance;

  static Future<void> _removeCompetingImageVariants(String fullPath) async {
    final targetExt = path.extension(fullPath).replaceFirst('.', '').toLowerCase();
    if (!const {'png', 'jpg', 'jpeg', 'webp'}.contains(targetExt)) return;

    final base = path.withoutExtension(fullPath);
    for (final ext in const ['png', 'jpg', 'jpeg', 'webp']) {
      if (ext == targetExt) continue;
      final sibling = File('$base.$ext');
      try {
        if (await sibling.exists()) await sibling.delete();
      } catch (_) {
        // A stale sibling that cannot be removed must not abort a scrape.
      }
    }
  }

  static Future<({bool success, bool wasExisting})> _downloadMediaFileSmart(
    String url,
    String relativePath,
    String userDataDir, {
    required String mediaType,
    bool forceOverwrite = false,
    int? maxDailyRequests,
  }) async {
    final fullPath = path.join(userDataDir, relativePath);
    final file = File(fullPath);

    try {
      final existed = await file.exists();
      if (existed) {
        final validExisting = await isValidMediaFile(file, mediaType);
        if (validExisting && !forceOverwrite) {
          await _removeCompetingImageVariants(fullPath);
          return (success: true, wasExisting: true);
        }
        if (!validExisting) {
          try {
            await file.delete();
          } catch (_) {}
        }
      }

      final response = await ScreenscraperClient.httpGetWithRetry(
        Uri.parse(url),
        timeout: const Duration(seconds: 60),
        maxRetries: 2,
        maxDailyRequests: maxDailyRequests,
      );
      if (response.statusCode != 200) {
        _log.e('Error downloading media (${response.statusCode}): $url');
        return (success: false, wasExisting: false);
      }

      final contentType = response.headers['content-type'] ?? '';
      if (!isValidMediaPayload(
        response.bodyBytes,
        mediaType: mediaType,
        contentType: contentType,
      )) {
        _log.w(
          'Rejected invalid ScreenScraper $mediaType payload '
          '(${response.bodyBytes.length} bytes, $contentType): '
          '${_safeBodyPrefix(response.bodyBytes)}',
        );
        return (success: false, wasExisting: false);
      }

      await file.parent.create(recursive: true);
      final temp = File('$fullPath.part');
      try {
        if (await temp.exists()) await temp.delete();
        await temp.writeAsBytes(response.bodyBytes, flush: true);
        if (await file.exists()) await file.delete();
        await temp.rename(fullPath);
      } finally {
        if (await temp.exists()) {
          try {
            await temp.delete();
          } catch (_) {}
        }
      }

      await _removeCompetingImageVariants(fullPath);
      return (success: true, wasExisting: false);
    } catch (e) {
      _log.e('Error downloading media: $e');
      return (success: false, wasExisting: false);
    }
  }

  /// Returns whether an on-disk media file matches the expected media type.
  static Future<bool> isValidMediaFile(File file, String mediaType) async {
    try {
      if (!await file.exists()) return false;
      final bytes = await file.readAsBytes();
      return isValidMediaPayload(bytes, mediaType: mediaType);
    } catch (_) {
      return false;
    }
  }

  /// Signature validation shared by the normal downloader, game-id fallback
  /// and unit tests.
  @visibleForTesting
  static bool isValidMediaPayload(
    List<int> bytes, {
    required String mediaType,
    String contentType = '',
  }) {
    if (bytes.length < 4) return false;
    if (_isTextStatus(bytes)) return false;

    switch (mediaType) {
      case 'video':
        return _looksLikeMp4(bytes);
      case 'manuel':
        return bytes.length >= 5 &&
            bytes[0] == 0x25 &&
            bytes[1] == 0x50 &&
            bytes[2] == 0x44 &&
            bytes[3] == 0x46 &&
            bytes[4] == 0x2d;
      default:
        return _looksLikeImage(bytes);
    }
  }

  static bool _isTextStatus(List<int> bytes) {
    final prefix = _safeBodyPrefix(bytes).toUpperCase();
    return prefix.startsWith('NOMEDIA') ||
        prefix.startsWith('CRCOK') ||
        prefix.startsWith('MD5OK') ||
        prefix.startsWith('SHA1OK') ||
        prefix.startsWith('<!DOCTYPE') ||
        prefix.startsWith('<HTML') ||
        prefix.startsWith('{"ERROR"') ||
        prefix.startsWith('{"HEADER"');
  }

  static bool _looksLikeImage(List<int> bytes) {
    final isPng = bytes.length >= 8 &&
        bytes[0] == 0x89 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x4e &&
        bytes[3] == 0x47 &&
        bytes[4] == 0x0d &&
        bytes[5] == 0x0a &&
        bytes[6] == 0x1a &&
        bytes[7] == 0x0a;
    if (isPng) return true;

    final isJpeg =
        bytes.length >= 3 && bytes[0] == 0xff && bytes[1] == 0xd8 && bytes[2] == 0xff;
    if (isJpeg) return true;

    final isGif = bytes.length >= 6 &&
        ascii.decode(bytes.sublist(0, 6), allowInvalid: true).startsWith('GIF8');
    if (isGif) return true;

    return bytes.length >= 12 &&
        ascii.decode(bytes.sublist(0, 4), allowInvalid: true) == 'RIFF' &&
        ascii.decode(bytes.sublist(8, 12), allowInvalid: true) == 'WEBP';
  }

  static bool _looksLikeMp4(List<int> bytes) {
    if (bytes.length < 12) return false;
    final limit = bytes.length < 96 ? bytes.length - 4 : 92;
    for (var index = 4; index <= limit; index++) {
      if (bytes[index] == 0x66 &&
          bytes[index + 1] == 0x74 &&
          bytes[index + 2] == 0x79 &&
          bytes[index + 3] == 0x70) {
        return true;
      }
    }
    return false;
  }

  static String _safeBodyPrefix(List<int> bytes) {
    if (bytes.isEmpty) return '<empty>';
    final take = bytes.length > 48 ? 48 : bytes.length;
    return utf8
        .decode(bytes.sublist(0, take), allowMalformed: true)
        .replaceAll(RegExp(r'[\r\n\t]+'), ' ')
        .trim();
  }

  static Future<Map<String, dynamic>> downloadGameMedia(
    String systemFolder,
    String romName,
    List<dynamic> medias,
    int maxThreads, {
    String? appSystemId,
    String? preferredLanguage,
    bool Function()? shouldCancel,
    Function(double progress)? onProgress,
    List<String>? allowedMediaTypes,
    bool forceOverwrite = false,
    int? maxDailyRequests,
  }) async {
    if (medias.isEmpty) {
      return {
        'success': true,
        'downloadedTypes': <String>[],
        'existingTypes': <String>[],
        'cancelled': false,
      };
    }

    final userDataDir = await ScreenscraperMediaResolver.getMediaDirectory();
    final regionPriority = await ScreenscraperRegionConfig.getRegionPriority();
    final mediaTypes =
        allowedMediaTypes ?? ['fanart', 'ss', 'video', 'wheel', 'box2D'];

    final downloadTasks = <Map<String, dynamic>>[];
    for (final mediaType in mediaTypes) {
      final bestMedia = ScreenscraperMediaResolver.selectBestMedia(
        medias,
        mediaType,
        preferredLanguage: preferredLanguage,
        regionPriority: regionPriority,
      );
      if (bestMedia == null) continue;

      final folderName = ScreenscraperMediaResolver.mapMediaTypeToFolder(mediaType);
      final romBaseName = await ScreenscraperRomHasher.getCleanRomName(
        romName,
        appSystemId,
      );
      final rawFormat = bestMedia['format']?.toString().toLowerCase();
      final fileFormat = switch (mediaType) {
        'video' => 'mp4',
        'manuel' => 'pdf',
        _ => (rawFormat == null || rawFormat.isEmpty) ? 'png' : rawFormat,
      };
      downloadTasks.add({
        'url': bestMedia['url'].toString(),
        'relativePath': '$systemFolder/$folderName/$romBaseName.$fileFormat',
        'mediaType': mediaType,
      });
    }

    if (downloadTasks.isEmpty) {
      return {
        'success': true,
        'downloadedTypes': <String>[],
        'existingTypes': <String>[],
        'cancelled': false,
      };
    }

    final batches = <List<Map<String, dynamic>>>[];
    for (var i = 0; i < downloadTasks.length; i += maxThreads) {
      final end = (i + maxThreads < downloadTasks.length)
          ? i + maxThreads
          : downloadTasks.length;
      batches.add(downloadTasks.sublist(i, end));
    }

    final downloadedTypes = <String>[];
    final existingTypes = <String>[];
    var wasCancelled = false;
    var completedTasks = 0;

    for (final batch in batches) {
      if (shouldCancel != null && shouldCancel()) {
        wasCancelled = true;
        break;
      }

      final results = await Future.wait(
        batch.map((task) async {
          final outcome = await _downloadMediaFileSmart(
            task['url'] as String,
            task['relativePath'] as String,
            userDataDir,
            mediaType: task['mediaType'] as String,
            forceOverwrite: forceOverwrite,
            maxDailyRequests: maxDailyRequests,
          );
          return {
            'mediaType': task['mediaType'],
            'success': outcome.success,
            'wasExisting': outcome.wasExisting,
          };
        }),
      );

      for (final result in results) {
        if (result['success'] != true) continue;
        final mediaType = result['mediaType'] as String;
        if (result['wasExisting'] == true) {
          existingTypes.add(mediaType);
        } else {
          downloadedTypes.add(mediaType);
        }
      }

      completedTasks += batch.length;
      onProgress?.call(completedTasks / downloadTasks.length);
      if (batches.length > 1) {
        await Future.delayed(const Duration(milliseconds: 100));
      }
    }

    final totalAvailable = downloadedTypes.length + existingTypes.length;
    return {
      'success': totalAvailable == downloadTasks.length && !wasCancelled,
      'downloadedTypes': downloadedTypes,
      'existingTypes': existingTypes,
      'cancelled': wasCancelled,
    };
  }
}
"""
Path('lib/services/screenscraper/media_downloader.dart').write_text(
    media_downloader,
    encoding='utf-8',
)


# ---------------------------------------------------------------------------
# 3. Direct game-id fallback for images AND videos in virtual libraries.
# ---------------------------------------------------------------------------
game_id_fallback = r"""import 'dart:io';

import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import '../logger_service.dart';
import 'media_downloader.dart';
import 'media_resolver.dart';
import 'rom_hasher.dart';
import 'screenscraper_client.dart';

/// Targeted ScreenScraper media fallback for URI-backed emulator libraries.
///
/// Once `jeuInfos.php` identifies a title, this helper uses the authoritative
/// ScreenScraper game id with `mediaJeu.php` / `mediaVideoJeu.php`. This avoids
/// relying solely on embedded media URLs and rejects textual HTTP-200 statuses.
class ScreenscraperGameIdMediaFallback {
  ScreenscraperGameIdMediaFallback._();

  static final _log = LoggerService.instance;
  static const String _baseUrl = 'https://api.screenscraper.fr/api2';
  static const Set<String> _supportedTypes = {
    'fanart',
    'ss',
    'wheel',
    'box2D',
    'video',
  };

  static Future<Map<String, dynamic>> ensureMediaByGameId({
    required String gameId,
    required String systemId,
    required String systemFolder,
    required String romName,
    required String appSystemId,
    required String devId,
    required String devPassword,
    required String softname,
    required String username,
    required String password,
    required List<String> allowedMediaTypes,
    required List<String> alreadyDownloadedTypes,
    required List<dynamic> sourceMedias,
    required String debugFileName,
    int? maxDailyRequests,
  }) async {
    final successful = <String>{...alreadyDownloadedTypes};
    final attempted = <String>[];
    final failures = <String>[];
    final requestedTypes = allowedMediaTypes
        .where(_supportedTypes.contains)
        .toList(growable: false);

    final sourceRegionsByType = <String, List<String>>{};
    for (final raw in sourceMedias) {
      if (raw is! Map) continue;
      final type = raw['type']?.toString() ?? '';
      final region = raw['region']?.toString() ?? '';
      if (type.isEmpty || region.isEmpty) continue;
      sourceRegionsByType.putIfAbsent(type, () => <String>[]);
      if (!sourceRegionsByType[type]!.contains(region)) {
        sourceRegionsByType[type]!.add(region);
      }
    }

    final mediaRoot = await ScreenscraperMediaResolver.getMediaDirectory();
    final mediaKey = await ScreenscraperRomHasher.getCleanRomName(
      romName,
      appSystemId,
    );

    await _writeDebug(
      debugFileName,
      'STATE: START\n'
      'Game ID: $gameId\n'
      'System ID: $systemId\n'
      'ROM key: $romName\n'
      'Media key: $mediaKey\n'
      'Requested media: ${requestedTypes.join(', ')}\n'
      'Normal downloader succeeded: ${alreadyDownloadedTypes.join(', ')}\n',
    );

    for (final mediaType in requestedTypes) {
      final folder = ScreenscraperMediaResolver.mapMediaTypeToFolder(mediaType);
      final extension = mediaType == 'video' ? 'mp4' : 'png';
      final target = File(
        path.join(mediaRoot, systemFolder, folder, '$mediaKey.$extension'),
      );
      await target.parent.create(recursive: true);

      final validExisting = await _findValidLocalMedia(
        mediaRoot,
        systemFolder,
        folder,
        mediaKey,
        mediaType,
      );
      if (successful.contains(mediaType) && validExisting != null) {
        await _appendDebug(
          debugFileName,
          '\nSKIP $mediaType: valid media already present '
          '(${validExisting.path}).\n',
        );
        continue;
      }
      if (mediaType == 'video' && validExisting != null) {
        successful.add(mediaType);
        await _appendDebug(
          debugFileName,
          '\nSKIP video: existing MP4 is valid (${validExisting.path}).\n',
        );
        continue;
      }

      successful.remove(mediaType);
      await _deleteInvalidLocalMedia(
        mediaRoot,
        systemFolder,
        folder,
        mediaKey,
        mediaType,
      );

      var downloaded = false;
      for (final token in _candidateMediaTokens(mediaType, sourceRegionsByType)) {
        attempted.add('$mediaType:$token');
        final isVideo = mediaType == 'video';
        final query = <String, String>{
          'devid': devId,
          'devpassword': devPassword,
          'softname': softname,
          'ssid': username,
          'sspassword': password,
          'crc': '',
          'md5': '',
          'sha1': '',
          'systemeid': systemId,
          'jeuid': gameId,
          'media': token,
          if (isVideo) 'mediaformat': 'mp4' else 'outputformat': 'png',
        };
        final endpoint = isVideo ? 'mediaVideoJeu.php' : 'mediaJeu.php';
        final uri = Uri.parse('$_baseUrl/$endpoint').replace(
          queryParameters: query,
        );

        try {
          final response = await ScreenscraperClient.httpGetWithRetry(
            uri,
            timeout: const Duration(seconds: 60),
            maxRetries: 1,
            maxDailyRequests: maxDailyRequests,
          );
          final contentType = response.headers['content-type'] ?? '';
          final valid = response.statusCode == 200 &&
              ScreenscraperMediaDownloader.isValidMediaPayload(
                response.bodyBytes,
                mediaType: mediaType,
                contentType: contentType,
              );
          await _appendDebug(
            debugFileName,
            '\nTRY $mediaType -> $endpoint/$token\n'
            'HTTP: ${response.statusCode}\n'
            'Content-Type: $contentType\n'
            'Bytes: ${response.bodyBytes.length}\n'
            'Valid payload: $valid\n',
          );
          if (!valid) continue;

          final temp = File('${target.path}.part');
          if (await temp.exists()) await temp.delete();
          await temp.writeAsBytes(response.bodyBytes, flush: true);
          if (await target.exists()) await target.delete();
          await temp.rename(target.path);
          if (!isVideo) {
            await _removeCompetingImageVariants(target.path);
          }
          successful.add(mediaType);
          downloaded = true;
          await _appendDebug(debugFileName, 'Saved: ${target.path}\n');
          break;
        } catch (e) {
          failures.add('$mediaType/$token: $e');
          await _appendDebug(
            debugFileName,
            '\nERROR $mediaType -> $token: $e\n',
          );
        }
      }

      if (!downloaded && !successful.contains(mediaType)) {
        failures.add('$mediaType: no valid ScreenScraper media found');
        await _appendDebug(
          debugFileName,
          '\nFAILED $mediaType: no candidate returned valid media.\n',
        );
      }
    }

    await _appendDebug(
      debugFileName,
      '\nSTATE: DONE\n'
      'Successful types: ${successful.toList()..sort()}\n'
      'Attempts: ${attempted.length}\n'
      'Failures: ${failures.length}\n',
    );
    return {
      'successfulTypes': successful.toList(),
      'attempted': attempted,
      'failures': failures,
    };
  }

  static List<String> _candidateMediaTokens(
    String mediaType,
    Map<String, List<String>> sourceRegionsByType,
  ) {
    if (mediaType == 'video') return const ['video'];

    final regions = <String>[];
    void addRegion(String value) {
      final normalized = value.trim();
      if (normalized.isEmpty || regions.contains(normalized)) return;
      regions.add(normalized);
    }

    final relevantSourceTypes = switch (mediaType) {
      'wheel' => ['wheel-hd', 'wheel'],
      'ss' => ['ss-hd', 'ss'],
      'box2D' => ['box-2D'],
      'fanart' => ['fanart'],
      _ => [mediaType],
    };
    for (final sourceType in relevantSourceTypes) {
      for (final region in sourceRegionsByType[sourceType] ?? const <String>[]) {
        addRegion(region);
      }
    }
    for (final region in const ['wor', 'us', 'eu', 'jp', 'cus']) {
      addRegion(region);
    }

    return switch (mediaType) {
      'fanart' => ['fanart', ...regions.map((r) => 'fanart($r)')],
      'ss' => [
          ...regions.map((r) => 'ss-hd($r)'),
          ...regions.map((r) => 'ss($r)'),
          'ss',
        ],
      'wheel' => [
          ...regions.map((r) => 'wheel-hd($r)'),
          ...regions.map((r) => 'wheel($r)'),
          'wheel-hd',
          'wheel',
        ],
      'box2D' => [...regions.map((r) => 'box-2D($r)'), 'box-2D'],
      _ => [mediaType],
    };
  }

  static Future<File?> _findValidLocalMedia(
    String mediaRoot,
    String systemFolder,
    String folder,
    String mediaKey,
    String mediaType,
  ) async {
    final extensions = mediaType == 'video'
        ? const ['mp4']
        : const ['png', 'jpg', 'jpeg', 'webp'];
    for (final extension in extensions) {
      final file = File(
        path.join(mediaRoot, systemFolder, folder, '$mediaKey.$extension'),
      );
      if (await ScreenscraperMediaDownloader.isValidMediaFile(file, mediaType)) {
        return file;
      }
    }
    return null;
  }

  static Future<void> _deleteInvalidLocalMedia(
    String mediaRoot,
    String systemFolder,
    String folder,
    String mediaKey,
    String mediaType,
  ) async {
    final extensions = mediaType == 'video'
        ? const ['mp4']
        : const ['png', 'jpg', 'jpeg', 'webp'];
    for (final extension in extensions) {
      final file = File(
        path.join(mediaRoot, systemFolder, folder, '$mediaKey.$extension'),
      );
      if (!await file.exists()) continue;
      if (await ScreenscraperMediaDownloader.isValidMediaFile(file, mediaType)) {
        continue;
      }
      try {
        await file.delete();
      } catch (_) {}
    }
  }

  static Future<void> _removeCompetingImageVariants(String targetPath) async {
    final base = path.withoutExtension(targetPath);
    final targetExtension = path.extension(targetPath).toLowerCase();
    for (final extension in const ['.png', '.jpg', '.jpeg', '.webp']) {
      if (extension == targetExtension) continue;
      final sibling = File('$base$extension');
      try {
        if (await sibling.exists()) await sibling.delete();
      } catch (_) {}
    }
  }

  static Future<void> _writeDebug(String fileName, String content) async {
    try {
      final docs = await getApplicationDocumentsDirectory();
      await File(path.join(docs.path, fileName)).writeAsString(
        '--- ${DateTime.now()} ---\n$content',
      );
    } catch (e) {
      _log.e('Game-id media fallback: failed writing debug file: $e');
    }
  }

  static Future<void> _appendDebug(String fileName, String content) async {
    try {
      final docs = await getApplicationDocumentsDirectory();
      await File(path.join(docs.path, fileName)).writeAsString(
        content,
        mode: FileMode.append,
      );
    } catch (e) {
      _log.e('Game-id media fallback: failed appending debug file: $e');
    }
  }
}
"""
Path('lib/services/screenscraper/game_id_media_fallback.dart').write_text(
    game_id_fallback,
    encoding='utf-8',
)
Path('lib/services/screenscraper/melonx_media_fallback.dart').unlink(
    missing_ok=True,
)


# ---------------------------------------------------------------------------
# 4. Use the direct game-id fallback for both MeloNX and RPCS3.
# ---------------------------------------------------------------------------
scraper_path = Path('lib/services/screenscraper_service.dart')
scraper = scraper_path.read_text(encoding='utf-8')
scraper = scraper.replace(
    "import 'screenscraper/melonx_media_fallback.dart';",
    "import 'screenscraper/game_id_media_fallback.dart';",
)

helper_marker = "  /// Scrapes a single game by its filename and updates its local state.\n"
virtual_helper = r"""  static Future<Set<String>> _ensureVirtualMediaByGameId({
    required bool isMeloNxVirtual,
    required bool isRpcs3Virtual,
    required Map<String, dynamic> gameInfo,
    required int screenScraperSystemId,
    required String systemFolder,
    required String romName,
    required String appSystemId,
    required List<String> allowedMediaTypes,
    required Map<String, dynamic> downloadResult,
    required List<dynamic> sourceMedias,
    int? maxDailyRequests,
  }) async {
    final successfulTypes = <String>{
      ...(downloadResult['downloadedTypes'] as List<dynamic>? ?? const [])
          .map((value) => value.toString()),
      ...(downloadResult['existingTypes'] as List<dynamic>? ?? const [])
          .map((value) => value.toString()),
    };
    if (!isMeloNxVirtual && !isRpcs3Virtual) return successfulTypes;

    final credentials = await getSavedCredentials();
    final gameId = gameInfo['id']?.toString() ?? '';
    if (credentials == null || gameId.isEmpty) return successfulTypes;

    final softname = await ScreenscraperClient.getSoftname();
    final fallbackResult =
        await ScreenscraperGameIdMediaFallback.ensureMediaByGameId(
          gameId: gameId,
          systemId: screenScraperSystemId.toString(),
          systemFolder: systemFolder,
          romName: romName,
          appSystemId: appSystemId,
          devId: _devId,
          devPassword: _devPassword,
          softname: softname,
          username: credentials['username']?.toString() ?? '',
          password: credentials['password']?.toString() ?? '',
          allowedMediaTypes: allowedMediaTypes,
          alreadyDownloadedTypes: successfulTypes.toList(),
          sourceMedias: sourceMedias,
          debugFileName: isRpcs3Virtual
              ? 'rpcs3_scraper_media_debug.txt'
              : 'melonx_scraper_media_debug.txt',
          maxDailyRequests: maxDailyRequests,
        );
    return (fallbackResult['successfulTypes'] as List<dynamic>? ?? const [])
        .map((value) => value.toString())
        .toSet();
  }

  static bool _hasUsefulVirtualMedia(
    List<String> allowedMediaTypes,
    Set<String> successfulTypes,
  ) {
    const visualTypes = {'fanart', 'ss', 'wheel', 'box2D', 'video'};
    final requested = allowedMediaTypes.where(visualTypes.contains).toSet();
    return requested.isEmpty || requested.any(successfulTypes.contains);
  }

"""
if virtual_helper not in scraper:
    if helper_marker not in scraper:
        raise SystemExit('ScreenScraper helper insertion marker not found')
    scraper = scraper.replace(helper_marker, virtual_helper + helper_marker, 1)

single_start = scraper.index("      var mediaSuccess = downloadResult['success'] == true;")
single_end = scraper.index("\n\n      return {", single_start)
single_block = r"""      var mediaSuccess = downloadResult['success'] == true;
      if (isMeloNxVirtual || isRpcs3Virtual) {
        final successfulTypes = await _ensureVirtualMediaByGameId(
          isMeloNxVirtual: isMeloNxVirtual,
          isRpcs3Virtual: isRpcs3Virtual,
          gameInfo: gameInfo,
          screenScraperSystemId: screenScraperSystemId,
          systemFolder: systemFolder,
          romName: romName,
          appSystemId: appSystemId,
          allowedMediaTypes: allowedMediaTypes,
          downloadResult: downloadResult,
          sourceMedias: medias,
          maxDailyRequests: null,
        );
        mediaSuccess = _hasUsefulVirtualMedia(
          allowedMediaTypes,
          successfulTypes,
        );
      }"""
scraper = scraper[:single_start] + single_block + scraper[single_end:]

batch_start = scraper.index("          var mediaSucceeded = res['success'] == true;")
batch_end = scraper.index("\n\n          if (mediaSucceeded) {", batch_start)
batch_block = r"""          var mediaSucceeded = res['success'] == true;
          if (isMeloNxVirtual || isRpcs3Virtual) {
            final successfulTypes = await _ensureVirtualMediaByGameId(
              isMeloNxVirtual: isMeloNxVirtual,
              isRpcs3Virtual: isRpcs3Virtual,
              gameInfo: Map<String, dynamic>.from(gameInfo as Map),
              screenScraperSystemId: screenscraperSystemId,
              systemFolder: systemFolder,
              romName: filename,
              appSystemId: appSystemId,
              allowedMediaTypes: allowedTypes,
              downloadResult: res,
              sourceMedias: sourceMedias,
              maxDailyRequests: maxDailyRequests,
            );
            mediaSucceeded = _hasUsefulVirtualMedia(
              allowedTypes,
              successfulTypes,
            );
          }"""
scraper = scraper[:batch_start] + batch_block + scraper[batch_end:]
scraper_path.write_text(scraper, encoding='utf-8')


# ---------------------------------------------------------------------------
# 5. Natural pluralization and shared theme typography for emulator cards.
# ---------------------------------------------------------------------------
locale_path = Path('lib/l10n/rpcs3_library_locale.dart')
locale = locale_path.read_text(encoding='utf-8')
if "package:flutter/foundation.dart" not in locale:
    locale = locale.replace(
        "import 'package:flutter/widgets.dart';",
        "import 'package:flutter/foundation.dart';\n"
        "import 'package:flutter/widgets.dart';",
        1,
    )
plural_maps_start = locale.index("  static const Map<String, String> _synced = {")
plural_maps_end = locale.index("  static const Map<String, String> _noGames = {")
locale = locale[:plural_maps_start] + locale[plural_maps_end:]
methods_start = locale.index("  static String statusSynced(BuildContext context, int count) =>")
methods_end = locale.index("  static String noGames(BuildContext context)", methods_start)
plural_methods = r"""  static String statusSynced(BuildContext context, int count) =>
      statusSyncedForLocale(_localeKey(Localizations.localeOf(context)), count);

  @visibleForTesting
  static String statusSyncedForLocale(String localeKey, int count) {
    return switch (localeKey) {
      'de' => count == 1
          ? 'RPCS3 synchronisiert — 1 PS3-Spiel.'
          : 'RPCS3 synchronisiert — $count PS3-Spiele.',
      'es' => count == 1
          ? 'RPCS3 sincronizado — 1 juego de PS3.'
          : 'RPCS3 sincronizado — $count juegos de PS3.',
      'fr' => count == 1
          ? 'RPCS3 synchronisé — 1 jeu PS3.'
          : 'RPCS3 synchronisé — $count jeux PS3.',
      'id' => 'RPCS3 tersinkron — $count game PS3.',
      'it' => count == 1
          ? 'RPCS3 sincronizzato — 1 gioco PS3.'
          : 'RPCS3 sincronizzato — $count giochi PS3.',
      'ja' => 'RPCS3 同期済み — PS3 ゲーム $count 本。',
      'ko' => 'RPCS3 동기화됨 — PS3 게임 $count개.',
      'pt' => count == 1
          ? 'RPCS3 sincronizado — 1 jogo de PS3.'
          : 'RPCS3 sincronizado — $count jogos de PS3.',
      'ru' => 'RPCS3 синхронизирован. Игр PS3: $count.',
      'zh' => 'RPCS3 已同步 — $count 个 PS3 游戏。',
      'zh_Hant' => 'RPCS3 已同步 — $count 個 PS3 遊戲。',
      _ => count == 1
          ? 'RPCS3 synced — 1 PS3 game.'
          : 'RPCS3 synced — $count PS3 games.',
    };
  }

  static String syncComplete(BuildContext context, int count) =>
      syncCompleteForLocale(_localeKey(Localizations.localeOf(context)), count);

  @visibleForTesting
  static String syncCompleteForLocale(String localeKey, int count) {
    return switch (localeKey) {
      'de' => count == 1
          ? 'RPCS3-Bibliothek synchronisiert: 1 Spiel.'
          : 'RPCS3-Bibliothek synchronisiert: $count Spiele.',
      'es' => count == 1
          ? 'Biblioteca RPCS3 sincronizada: 1 juego.'
          : 'Biblioteca RPCS3 sincronizada: $count juegos.',
      'fr' => count == 1
          ? 'Bibliothèque RPCS3 synchronisée : 1 jeu.'
          : 'Bibliothèque RPCS3 synchronisée : $count jeux.',
      'id' => 'Pustaka RPCS3 disinkronkan: $count game.',
      'it' => count == 1
          ? 'Libreria RPCS3 sincronizzata: 1 gioco.'
          : 'Libreria RPCS3 sincronizzata: $count giochi.',
      'ja' => 'RPCS3 ライブラリを同期しました：$count 本。',
      'ko' => 'RPCS3 라이브러리 동기화 완료: 게임 $count개.',
      'pt' => count == 1
          ? 'Biblioteca RPCS3 sincronizada: 1 jogo.'
          : 'Biblioteca RPCS3 sincronizada: $count jogos.',
      'ru' => 'Библиотека RPCS3 синхронизирована. Игр: $count.',
      'zh' => 'RPCS3 游戏库同步完成：$count 个游戏。',
      'zh_Hant' => 'RPCS3 遊戲庫同步完成：$count 個遊戲。',
      _ => count == 1
          ? 'RPCS3 library synced: 1 game.'
          : 'RPCS3 library synced: $count games.',
    };
  }

"""
locale = locale[:methods_start] + plural_methods + locale[methods_end:]
locale_path.write_text(locale, encoding='utf-8')

settings_path = Path(
    'lib/screens/settings_screen/new_settings_options/'
    'directories_settings_content.dart'
)
settings = settings_path.read_text(encoding='utf-8')
settings = settings.replace(
    """                  style: TextStyle(fontSize: 16.r, fontWeight: FontWeight.bold),
""",
    """                  style: theme.textTheme.titleMedium?.copyWith(
                    fontSize: 16.r,
                    fontWeight: FontWeight.bold,
                  ),
""",
    1,
)
settings = settings.replace(
    """              style: TextStyle(
                fontSize: 13.r,
                color: theme.colorScheme.onSurfaceVariant,
              ),
""",
    """              style: theme.textTheme.bodyMedium?.copyWith(
                fontSize: 13.r,
                color: theme.colorScheme.onSurfaceVariant,
              ),
""",
    1,
)
settings_path.write_text(settings, encoding='utf-8')


# ---------------------------------------------------------------------------
# 6. Keep StikDebug attached through RPCS3's Start gate, then auto-boot title.
# ---------------------------------------------------------------------------
rpcs3_script = r"""// NeoStation RPCS3 title launcher.
// Derived from StikDebug Universal JIT Script (GPL-3.0):
// https://github.com/StikDebug/StikDebug/blob/main/StikDebug/Scripts/universal.js
//
// RPCS3 iOS 0.1 (1) presents a native Start gate before libRPCS3Core.dylib is
// loaded. The first JIT detach request therefore cannot boot a title. This
// script keeps the debug session attached, lets the user press Start, waits for
// the fingerprinted core to become ready, then boots the title selected in
// NeoStation without requiring a second selection inside RPCS3.

const CMD_DETACH = 0;
const CMD_PREPARE_REGION = 1;
const CMD_NEW_BREAKPOINTS = 2;
const commands = {
    [CMD_DETACH]: JIT26Detach,
    [CMD_PREPARE_REGION]: JIT26PrepareRegion,
    [CMD_NEW_BREAKPOINTS]: JIT26NewBreakpoints
};
const legacyCommands = {
    [0x68]: JIT26NewBreakpoints,
    [0x69]: JIT26HandleBrk0x69,
    [0xf00d]: JIT26HandleBrk0xf00d
};
const LOG_VERBOSE = 2;
let logLevel = LOG_VERBOSE;
function log_verbose(msg) { if (logLevel >= LOG_VERBOSE) log(msg); }

const neoTitleId = __NEOSTATION_TITLE_ID_JSON__;
const neoExpectedCoreUuid = __NEOSTATION_CORE_UUID_JSON__;
const neoBootGameOffset = 0x__NEOSTATION_BOOT_OFFSET_HEX__n;
const neoReturnTrapInstruction = 'c0013ed4'; // brk #0xf00e, little endian
const neoRequiredCoreObservations = 2;
const neoMaximumBootAttempts = 3;

let tid, x0, x1, x16, pc;
let detached = false;
let continuesWithSignal = true;
let neoWaitingForStart = false;
let neoBootCompleted = false;
let neoCoreObservations = 0;
let neoBootAttempts = 0;
let pid = get_pid();
let attachResponse = send_command(`vAttach;${pid.toString(16)}`);
log(`pid = ${pid}`);
log(`attach_response = ${attachResponse}`);
log(`NEOSTATION_RPC_SELECTED_TITLE: ${neoTitleId}`);

let totalBreakpoints = 0;
while (!detached) {
    totalBreakpoints++;
    let brkResponse = send_command('c');
    log_verbose(`Handling signal ${totalBreakpoints}: ${brkResponse}`);

    let tmpMatch = /T[0-9a-f]+thread:(?<tid>[0-9a-f]+);/.exec(brkResponse);
    tid = tmpMatch ? tmpMatch.groups['tid'] : null;
    tmpMatch = /20:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
    pc = tmpMatch ? tmpMatch.groups['reg'] : null;
    tmpMatch = /10:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
    x16 = tmpMatch ? tmpMatch.groups['reg'] : null;
    if (!tid || !pc || !x16) {
        log(`Failed to extract registers: tid=${tid}, pc=${pc}, x16=${x16}`);
        continue;
    }
    pc = littleEndianHexStringToNumber(pc);
    x16 = littleEndianHexStringToNumber(x16);

    const instructionResponse = send_command(`m${pc.toString(16)},4`);
    const instrU32 = littleEndianHexToU32(instructionResponse);
    if ((instrU32 & 0xFFE0001F) >>> 0 != 0xD4200000) {
        if (continuesWithSignal) {
            let signum = /^T(?<sig>[a-z0-9;]{2})/.exec(brkResponse);
            signum = signum ? signum.groups['sig'] : null;
            if (signum) send_command(`vCont;S${signum}:${tid}`);
        }
        continue;
    }

    const brkImmediate = extractBrkImmediate(instrU32);
    const handler = legacyCommands[brkImmediate];
    if (handler === undefined) continue;

    tmpMatch = /00:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
    x0 = tmpMatch ? tmpMatch.groups['reg'] : null;
    tmpMatch = /01:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
    x1 = tmpMatch ? tmpMatch.groups['reg'] : null;
    if (!x0 || !x1) continue;
    x0 = littleEndianHexStringToNumber(x0);
    x1 = littleEndianHexStringToNumber(x1);

    send_command(`P20=${numberToLittleEndianHexString(pc + 4n)};thread:${tid};`);
    handler(brkResponse);

    // The first detach occurs on RPCS3's JIT-ready screen before its core is
    // loaded. Once Start is pressed, the core emits preparation breakpoints.
    // Two matching observations avoid calling into a half-loaded dylib.
    if (!detached && neoWaitingForStart && x16 !== 0n) {
        neoStationObserveCoreAndMaybeBoot();
    }
}

function JIT26Detach() {
    const outcome = neoStationTryBootRpcs3Title('detach');
    if (outcome === 'waiting') {
        if (!neoWaitingForStart) {
            neoWaitingForStart = true;
            log('NEOSTATION_RPC_WAITING_FOR_START: press Start in RPCS3; the selected title will launch automatically afterwards.');
        }
        return;
    }
    neoStationDetach(outcome === 'booted' ? 'BOOT_COMPLETED' : 'FATAL');
}

function neoStationObserveCoreAndMaybeBoot() {
    const discovery = neoStationFindCore();
    if (discovery.state === 'missing') {
        neoCoreObservations = 0;
        return;
    }
    if (discovery.state === 'mismatch') {
        log(`NEOSTATION_RPC_FATAL: ${discovery.detail}`);
        neoStationDetach('CORE_UUID_MISMATCH');
        return;
    }

    neoCoreObservations++;
    log(`NEOSTATION_RPC_CORE_DISCOVERED: observation ${neoCoreObservations}/${neoRequiredCoreObservations}`);
    if (neoCoreObservations < neoRequiredCoreObservations) return;

    const outcome = neoStationTryBootRpcs3Title('post-start');
    if (outcome === 'booted') {
        neoStationDetach('BOOT_COMPLETED');
    } else if (outcome === 'fatal') {
        neoStationDetach('BOOT_FAILED');
    }
}

function neoStationTryBootRpcs3Title(reason) {
    if (neoBootCompleted) return 'booted';
    const discovery = neoStationFindCore();
    if (discovery.state === 'missing') return 'waiting';
    if (discovery.state === 'mismatch') {
        log(`NEOSTATION_RPC_FATAL: ${discovery.detail}`);
        return 'fatal';
    }

    neoBootAttempts++;
    log(`NEOSTATION_RPC_BOOT_ATTEMPT: ${neoBootAttempts}/${neoMaximumBootAttempts} reason=${reason} title=${neoTitleId}`);
    try {
        neoStationCallBoot(discovery.core);
        neoBootCompleted = true;
        log(`NEOSTATION_RPC_BOOT_COMPLETED: ${neoTitleId}`);
        return 'booted';
    } catch (error) {
        log(`NEOSTATION_RPC_BOOT_ERROR: ${error && error.stack ? error.stack : error}`);
        return neoBootAttempts >= neoMaximumBootAttempts ? 'fatal' : 'waiting';
    }
}

function neoStationFindCore() {
    const command = 'jGetLoadedDynamicLibrariesInfos:{"fetch_all_solibs":true,"information-level":"address-name-uuid"}';
    const rawLibraries = send_command(command);
    const jsonStart = rawLibraries ? rawLibraries.indexOf('{') : -1;
    if (jsonStart < 0) {
        return { state: 'missing', detail: `No loaded-image JSON: ${rawLibraries}` };
    }

    let payload;
    try {
        payload = JSON.parse(rawLibraries.substring(jsonStart));
    } catch (error) {
        return { state: 'missing', detail: `Invalid loaded-image JSON: ${error}` };
    }
    const images = Array.isArray(payload.images) ? payload.images : [];
    const core = images.find((image) => String(image.pathname || '').includes('libRPCS3Core.dylib'));
    if (!core) return { state: 'missing', detail: 'libRPCS3Core.dylib is not loaded' };

    const actualUuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const expectedUuid = neoExpectedCoreUuid.replace(/-/g, '').toUpperCase();
    if (actualUuid !== expectedUuid) {
        return {
            state: 'mismatch',
            detail: `RPCS3 core UUID mismatch: ${actualUuid} != ${expectedUuid}`,
        };
    }
    return { state: 'match', core: core };
}

function neoStationCallBoot(core) {
    const loadAddress = parseRemoteAddress(core.load_address);
    const bootAddress = loadAddress + neoBootGameOffset;
    log(`NEOSTATION_RPC_CORE: load=0x${loadAddress.toString(16)} boot=0x${bootAddress.toString(16)}`);

    const saveId = send_command(`QSaveRegisterState;thread:${tid};`);
    if (!saveId || !/^[0-9]+$/.test(saveId)) {
        throw new Error(`Could not save registers: ${saveId}`);
    }

    let scratchResponse = send_command('_M4000,rwx');
    if (!scratchResponse || scratchResponse.startsWith('E')) {
        scratchResponse = send_command('_M4000,rw');
    }
    if (!scratchResponse || scratchResponse.startsWith('E')) {
        throw new Error(`Could not allocate remote scratch memory: ${scratchResponse}`);
    }
    const scratch = BigInt(`0x${scratchResponse}`);
    const prepared = prepare_memory_region(scratch, 0x4000n);
    log(`NEOSTATION_RPC_SCRATCH: 0x${scratch.toString(16)} prepare=${prepared}`);

    const titleHex = asciiToHex(neoTitleId + '\0');
    const titleWrite = send_command(`M${scratch.toString(16)},${(titleHex.length / 2).toString(16)}:${titleHex}`);
    if (titleWrite !== 'OK') throw new Error(`Could not write title ID: ${titleWrite}`);

    const trap = scratch + 0x100n;
    const trapWrite = send_command(`M${trap.toString(16)},4:${neoReturnTrapInstruction}`);
    if (trapWrite !== 'OK') throw new Error(`Could not write return trap: ${trapWrite}`);

    const x0Write = send_command(`P0=${numberToLittleEndianHexString(scratch)};thread:${tid};`);
    const lrWrite = send_command(`P1e=${numberToLittleEndianHexString(trap)};thread:${tid};`);
    const pcWrite = send_command(`P20=${numberToLittleEndianHexString(bootAddress)};thread:${tid};`);
    if (x0Write !== 'OK' || lrWrite !== 'OK' || pcWrite !== 'OK') {
        throw new Error(`Register write failed: x0=${x0Write} lr=${lrWrite} pc=${pcWrite}`);
    }

    const callStop = send_command(`vCont;c:${tid}`);
    log(`NEOSTATION_RPC_BOOT_RETURN: ${callStop}`);
    const restore = send_command(`QRestoreRegisterState:${saveId};thread:${tid};`);
    log(`NEOSTATION_RPC_RESTORE: ${restore}`);
    send_command(`_m${scratch.toString(16)}`);
    if (restore !== 'OK') throw new Error(`Could not restore registers: ${restore}`);
}

function neoStationDetach(reason) {
    const response = send_command('D');
    log(`NEOSTATION_RPC_DETACH: reason=${reason} response=${response}`);
    detached = true;
}

function JIT26NewBreakpoints(brkResponse) {
    const memResponse = send_command(`m${x0.toString(16)},${x1}`);
    const scriptText = hexToAscii(memResponse);
    try { eval(scriptText); } catch (error) { log(`Dynamic script failed: ${error}`); }
}

function JIT26HandleBrk0x69(brkResponse) {
    send_command(`P0=E0000069;thread:${tid};`);
}

function JIT26HandleBrk0xf00d(brkResponse) {
    const command = commands[x16];
    if (command !== undefined) command(brkResponse);
}

function JIT26PrepareRegion(brkResponse) {
    if (x0 == 0n && x1 == 0n) return;
    let jitPageAddress = x0;
    if (x0 == 0n) {
        const response = send_command(`_M${x1.toString(16)},rx`);
        if (!response) return;
        jitPageAddress = BigInt(`0x${response}`);
    }
    prepare_memory_region(jitPageAddress, x1);
    send_command(`P0=${numberToLittleEndianHexString(jitPageAddress)};thread:${tid};`);
}

function parseRemoteAddress(value) {
    if (typeof value === 'number') return BigInt(Math.trunc(value));
    const text = String(value || '').trim();
    if (!text) throw new Error('Missing remote load address');
    return BigInt(text);
}

function asciiToHex(text) {
    let result = '';
    for (let i = 0; i < text.length; i++) {
        result += text.charCodeAt(i).toString(16).padStart(2, '0');
    }
    return result;
}

function littleEndianHexStringToNumber(hexStr) {
    const bytes = [];
    for (let i = 0; i < hexStr.length; i += 2) bytes.push(parseInt(hexStr.substr(i, 2), 16));
    let num = 0n;
    for (let i = Math.min(bytes.length, 8) - 1; i >= 0; i--) num = (num << 8n) | BigInt(bytes[i]);
    return num;
}

function numberToLittleEndianHexString(num) {
    const bytes = [];
    for (let i = 0; i < 8; i++) {
        bytes.push(Number(num & 0xFFn));
        num >>= 8n;
    }
    return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function littleEndianHexToU32(hexStr) {
    return parseInt(hexStr.match(/../g).reverse().join(''), 16);
}

function extractBrkImmediate(u32) { return (u32 >> 5) & 0xFFFF; }

function hexToAscii(hexStr) {
    let text = '';
    for (let i = 0; i < hexStr.length; i += 2) {
        const byte = parseInt(hexStr.substr(i, 2), 16);
        if (byte === 0) break;
        text += String.fromCharCode(byte);
    }
    return text;
}
"""
Path('assets/data/rpcs3_stikdebug_launch.js').write_text(
    rpcs3_script,
    encoding='utf-8',
)

launch_path = Path('lib/services/rpcs3_launch_service.dart')
launch = launch_path.read_text(encoding='utf-8')
launch = launch.replace(
    """/// StikDebug to run a derivative of its Universal script. At RPCS3's normal JIT
/// detach breakpoint, the script verifies the loaded core UUID, calls the
/// exported `rpcs3_ios_boot_game(title_id)` function, restores the stopped
/// thread's register state, detaches, and then StikDebug foregrounds RPCS3.
""",
    """/// StikDebug to run a derivative of its Universal script. The script remains
/// attached across RPCS3's native Start gate, waits for the fingerprinted core
/// to load, then calls `rpcs3_ios_boot_game(title_id)`, restores the stopped
/// thread's register state and detaches. The user may still need to press Start,
/// but no second game selection should be required.
""",
)
launch_path.write_text(launch, encoding='utf-8')


# ---------------------------------------------------------------------------
# 7. Regression tests, documentation and build number.
# ---------------------------------------------------------------------------
tests = r"""import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_database_service.dart';
import 'package:neostation/l10n/rpcs3_library_locale.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';
import 'package:neostation/services/screenscraper/media_downloader.dart';
import 'package:neostation/services/screenscraper_service.dart';

void main() {
  group('RPCS3 persistence, media and launch', () {
    test('ScreenScraper lookup carries the PS3 serial number', () {
      final params = ScreenScraperService.buildGameLookupParametersForTesting(
        systemId: '59',
        romName: 'BLES00113',
        serialNumber: ' BLES00113 ',
      );
      expect(params['systemeid'], '59');
      expect(params['romnom'], 'BLES00113');
      expect(params['serialnum'], 'BLES00113');
    });

    test('all URI-backed emulator rows survive physical scans', () {
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath(
          'rpcs3-library://game?title-id=BLES00113',
        ),
        isTrue,
      );
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath('melonx://game'),
        isTrue,
      );
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath('armsx2://game'),
        isTrue,
      );
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath('/roms/game.iso'),
        isFalse,
      );
    });

    test('ScreenScraper text statuses are rejected as media', () {
      for (final status in ['NOMEDIA', 'CRCOK', 'MD5OK', 'SHA1OK']) {
        expect(
          ScreenscraperMediaDownloader.isValidMediaPayload(
            utf8.encode(status),
            mediaType: 'video',
          ),
          isFalse,
        );
      }
    });

    test('MP4 and PNG signatures are accepted', () {
      expect(
        ScreenscraperMediaDownloader.isValidMediaPayload(
          const [0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d],
          mediaType: 'video',
        ),
        isTrue,
      );
      expect(
        ScreenscraperMediaDownloader.isValidMediaPayload(
          const [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
          mediaType: 'box2D',
        ),
        isTrue,
      );
    });

    test('RPCS3 launch script waits through the native Start gate', () {
      final template = File(
        'assets/data/rpcs3_stikdebug_launch.js',
      ).readAsStringSync();
      final script = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00113',
      );
      expect(script, contains('"BLES00113"'));
      expect(script, contains(Rpcs3LaunchService.expectedCoreUuid));
      expect(script, contains('NEOSTATION_RPC_WAITING_FOR_START'));
      expect(script, contains('NEOSTATION_RPC_CORE_DISCOVERED'));
      expect(script, contains('NEOSTATION_RPC_BOOT_COMPLETED'));
      expect(script, isNot(contains('__NEOSTATION_')));
    });

    test('invalid RPCS3 title IDs are rejected', () {
      expect(Rpcs3LaunchService.normalizeTitleId('../bad'), isNull);
      expect(Rpcs3LaunchService.normalizeTitleId('BLES00113'), 'BLES00113');
    });

    test('scraped RPCS3 name replaces the raw Title ID', () {
      final game = GameModel.fromDatabaseModel(
        DatabaseGameModel(
          filename: 'BLES00113',
          romPath: 'rpcs3-library://game?title-id=BLES00113',
          titleId: 'BLES00113',
          titleName: 'BLES00113',
          screenscraperRealName: 'Bladestorm: The Hundred Years’ War',
        ),
      );
      expect(game.name, 'Bladestorm: The Hundred Years’ War');
      expect(game.realname, 'Bladestorm: The Hundred Years’ War');
      expect(game.titleId, 'BLES00113');
    });

    test('French RPCS3 status uses natural singular and plural', () {
      expect(
        Rpcs3LibraryLocale.statusSyncedForLocale('fr', 1),
        'RPCS3 synchronisé — 1 jeu PS3.',
      );
      expect(
        Rpcs3LibraryLocale.statusSyncedForLocale('fr', 2),
        'RPCS3 synchronisé — 2 jeux PS3.',
      );
    });
  });
}
"""
Path('test/rpcs3_stage3_test.dart').write_text(tests, encoding='utf-8')

pubspec_path = Path('pubspec.yaml')
pubspec = pubspec_path.read_text(encoding='utf-8')
if 'version: 0.9.9+132' not in pubspec:
    if 'version: 0.9.9+131' not in pubspec:
        raise SystemExit('Unexpected NeoStation version')
    pubspec = pubspec.replace('version: 0.9.9+131', 'version: 0.9.9+132', 1)
pubspec_path.write_text(pubspec, encoding='utf-8')

readme_path = Path('README.md')
readme = readme_path.read_text(encoding='utf-8')
readme = readme.replace(
    '**RPCS3 iOS** Data-folder library import, Title-ID ScreenScraper lookup and experimental StikDebug-assisted direct launch for the fingerprinted RPCS3 iOS 0.1 (1) build.',
    '**RPCS3 iOS** persistent Data-folder library import, Title-ID ScreenScraper lookup, validated image/video downloads and experimental StikDebug-assisted title launch after RPCS3’s Start gate for the fingerprinted RPCS3 iOS 0.1 (1) build.',
)
readme_path.write_text(readme, encoding='utf-8')

print('RPCS3 stage 4 source patch applied.')
