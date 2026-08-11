import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:neostation/main.dart' show rootNavigatorKey;
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

/// Integrates NeoStation with ARMSX2 iOS's URL-scheme library export and
/// direct-launch protocol.
///
/// ARMSX2 accepts a library request such as:
///   armsx2://library?callback=neostation://armsx2
///
/// It calls NeoStation back with:
///   neostation://armsx2?source=armsx2-ios&payload=<base64url>
///
/// The decoded payload is a JSON object whose `games` array contains entries
/// including `fileName` and `launchURL`. NeoStation caches those entries by
/// filename so a PS2 ROM can later be opened directly in ARMSX2 without the
/// iOS Open In / Share Sheet fallback.
class Armsx2LibraryService {
  Armsx2LibraryService._();

  static final _log = LoggerService.instance;

  static const String _callbackScheme = 'neostation';
  static const String _callbackHost = 'armsx2';
  static const String _prefsKey = 'armsx2_library_cache_v1';

  /// Lookup keys (filename / basename / extensionless stem) -> raw ARMSX2
  /// exported game entry.
  static Map<String, Map<String, dynamic>>? _cache;

  /// Opens ARMSX2 and requests a fresh export of its game library.
  ///
  /// Completion is asynchronous: ARMSX2 switches back to NeoStation through
  /// the callback URL, which is processed by [handleIncomingUri].
  static Future<bool> requestLibrarySync() async {
    final callback = Uri(
      scheme: _callbackScheme,
      host: _callbackHost,
    ).toString();

    final uri = Uri(
      scheme: 'armsx2',
      host: 'library',
      queryParameters: {'callback': callback},
    );

    try {
      return await launchUrl(uri);
    } catch (e) {
      _log.e('Armsx2LibraryService: failed to request library sync: $e');
      return false;
    }
  }

  /// Handles ARMSX2's `neostation://armsx2?...&payload=...` callback.
  /// Returns true only when the URI belongs to this service and was parsed.
  static Future<bool> handleIncomingUri(Uri uri) async {
    if (uri.scheme.toLowerCase() != _callbackScheme ||
        uri.host.toLowerCase() != _callbackHost) {
      return false;
    }

    final payloadParam = uri.queryParameters['payload'];
    if (payloadParam == null || payloadParam.isEmpty) {
      _log.w('Armsx2LibraryService: callback with no "payload" param');
      return false;
    }

    try {
      final normalized = base64Url.normalize(payloadParam);
      final jsonBytes = base64Url.decode(normalized);
      final decoded = jsonDecode(utf8.decode(jsonBytes));

      if (decoded is! Map) {
        _log.e('Armsx2LibraryService: decoded payload is not an object');
        return false;
      }

      final payload = Map<String, dynamic>.from(decoded);
      final gamesRaw = payload['games'];
      if (gamesRaw is! List) {
        _log.e('Armsx2LibraryService: payload has no games array');
        return false;
      }

      final byFilename = <String, Map<String, dynamic>>{};
      for (final entry in gamesRaw) {
        if (entry is! Map) continue;

        final map = Map<String, dynamic>.from(entry);
        final fileName = map['fileName']?.toString();
        if (fileName == null || fileName.isEmpty) continue;

        _index(byFilename, fileName, map);
        _index(byFilename, path.basename(fileName), map);
        _index(byFilename, path.basenameWithoutExtension(fileName), map);
      }

      _cache = byFilename;
      await _persist(byFilename);

      _log.i(
        'Armsx2LibraryService: synced ${gamesRaw.length} games from ARMSX2',
      );

      await _writeDebugFile(
        'armsx2_sync_debug.txt',
        'Schema: ${payload['schema'] ?? 'unknown'}\n'
            'App: ${payload['app'] ?? 'unknown'}\n'
            'Version: ${payload['version'] ?? 'unknown'}\n'
            'Games: ${gamesRaw.length}\n\n'
            'Payload:\n${const JsonEncoder.withIndent('  ').convert(payload)}',
      );

      // A linked ARMSX2 folder is already registered as a NeoStation ROM
      // folder. Rescan after every successful export so newly-added PS2 games
      // appear in NeoStation immediately after ARMSX2 returns the callback.
      try {
        final context = rootNavigatorKey.currentContext;
        if (context != null) {
          await Provider.of<SqliteConfigProvider>(
            context,
            listen: false,
          ).scanSystems();
        }
      } catch (e) {
        _log.e('Armsx2LibraryService: post-sync rescan failed: $e');
      }

      return true;
    } catch (e) {
      _log.e('Armsx2LibraryService: failed to parse library callback: $e');
      await _writeDebugFile(
        'armsx2_sync_debug.txt',
        'Failed to parse callback.\nURI: $uri\nError: $e',
      );
      return false;
    }
  }

  static void _index(
    Map<String, Map<String, dynamic>> target,
    String key,
    Map<String, dynamic> entry,
  ) {
    if (key.isEmpty) return;
    target[key] = entry;
    target.putIfAbsent(key.toLowerCase(), () => entry);
  }

  /// Loads the last ARMSX2 export from SharedPreferences at app startup.
  static Future<void> loadCachedLibrary() async {
    if (_cache != null) return;

    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_prefsKey);
      if (raw == null) {
        _cache = {};
        return;
      }

      final decoded = jsonDecode(raw);
      if (decoded is Map) {
        _cache = decoded.map(
          (key, value) => MapEntry(
            key.toString(),
            Map<String, dynamic>.from(value as Map),
          ),
        );
      } else {
        _cache = {};
      }
    } catch (e) {
      _log.e('Armsx2LibraryService: failed loading cached library: $e');
      _cache = {};
    }
  }

  static Future<void> _persist(Map<String, Map<String, dynamic>> data) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefsKey, jsonEncode(data));
    } catch (e) {
      _log.e('Armsx2LibraryService: failed persisting library cache: $e');
    }
  }

  /// Whether a non-empty ARMSX2 library has been received at least once.
  static bool get hasSyncedLibrary => (_cache?.isNotEmpty ?? false);

  /// Launches a ROM directly in ARMSX2 when its filename matches the most
  /// recently exported ARMSX2 library. Returns false when no match exists or
  /// when iOS refuses to open the ARMSX2 URL, allowing the caller to fall back
  /// to RetroArch / Open In / Share Sheet behavior.
  static Future<bool> launchGameByRomPath(String romPath) async {
    final cache = _cache;
    if (cache == null || cache.isEmpty) {
      await _writeDebugFile(
        'armsx2_launch_debug.txt',
        'romPath: $romPath\ncache is null or empty (sync ARMSX2 first)',
      );
      return false;
    }

    final basename = path.basename(romPath);
    final stem = path.basenameWithoutExtension(romPath);
    final entry =
        cache[basename] ??
        cache[basename.toLowerCase()] ??
        cache[romPath] ??
        cache[romPath.toLowerCase()] ??
        cache[stem] ??
        cache[stem.toLowerCase()];

    await _writeDebugFile(
      'armsx2_launch_debug.txt',
      'romPath: $romPath\n'
          'basename: $basename\n'
          'stem: $stem\n'
          'match found: ${entry != null}\n'
          'matched entry: ${entry != null ? jsonEncode(entry) : 'none'}\n'
          'cache keys (${cache.length}):\n${cache.keys.join('\n')}',
    );

    if (entry == null) return false;

    final fileName = entry['fileName']?.toString();
    if (fileName == null || fileName.isEmpty) return false;

    final exportedLaunchUrl = entry['launchURL']?.toString();
    final exportedUri = exportedLaunchUrl == null
        ? null
        : Uri.tryParse(exportedLaunchUrl);

    final uri = exportedUri ??
        Uri(
          scheme: 'armsx2',
          host: 'launch',
          queryParameters: {'game': fileName},
        );

    try {
      return await launchUrl(uri);
    } catch (e) {
      _log.e('Armsx2LibraryService: failed to launch $uri: $e');
      return false;
    }
  }

  /// Device-readable diagnostics for CI-only iOS development where an Xcode
  /// console is not available.
  static Future<void> _writeDebugFile(String name, String content) async {
    try {
      final docsDir = await getApplicationDocumentsDirectory();
      final file = File(path.join(docsDir.path, name));
      await file.writeAsString('--- ${DateTime.now()} ---\n$content');
    } catch (e) {
      _log.e('Armsx2LibraryService: failed writing debug file $name: $e');
    }
  }
}
