import 'dart:convert';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:neostation/services/logger_service.dart';

/// Talks to RetroArch's real, confirmed URL-scheme protocol for library
/// export and direct game launching, on the TestFlight build.
///
/// Protocol (provided directly by the developer of a third-party app that
/// already uses it successfully):
///
///   1. NeoStation opens `retroarch://library?scheme=neostation` to ask
///      RetroArch to export its whole game library.
///   2. RetroArch calls back `neostation://retroarch?games=<base64url>` —
///      a base64url (no padding), JSON-encoded array of every game it
///      knows about, each with `titleId`/`filename`/`titleName`/`gameId`/
///      `system`/`coreName`. `filename` (== `titleId`) is the exact value
///      RetroArch's own `retroarch://game/<filename>` scheme expects.
///   3. To launch a specific game with no menu, no import step, and no
///      picker: `retroarch://game/<filename>`.
///
/// This replaces the earlier "Resume Last Game" playlist-rewriting
/// approach (kept as a fallback in GameLaunchService) — that one relied on
/// an assumption about RetroArch re-reading content_history.lpl on launch
/// that testing didn't bear out. This scheme is directly documented by
/// RetroArch's own TestFlight-side code, not inferred.
class RetroArchLibraryService {
  RetroArchLibraryService._();

  static final _log = LoggerService.instance;

  static const String _callbackScheme = 'neostation';
  static const String _prefsKey = 'retroarch_library_cache_v1';

  /// filename -> the raw exported entry (titleId/filename/titleName/
  /// gameId/system/coreName), cached in memory after the first sync or
  /// load from disk this session.
  static Map<String, Map<String, dynamic>>? _cache;

  /// Opens RetroArch and asks it to export its library. The actual data
  /// arrives asynchronously via the `neostation://retroarch?games=...`
  /// callback — see [handleIncomingUri], wired up in main.dart through the
  /// app_links package. Returns whether the request URL was opened at all
  /// (not whether RetroArch actually responded).
  static Future<bool> requestLibrarySync() async {
    return launchUrl(
      Uri.parse('retroarch://library?scheme=$_callbackScheme'),
    );
  }

  /// Call this with every incoming URI the app receives (from
  /// app_links' uriLinkStream / getInitialAppLink). Returns `true` if the
  /// URI was RetroArch's library callback and was handled.
  static Future<bool> handleIncomingUri(Uri uri) async {
    if (uri.scheme != _callbackScheme || uri.host != 'retroarch') {
      return false;
    }

    final gamesParam = uri.queryParameters['games'];
    if (gamesParam == null) {
      _log.w('RetroArchLibraryService: callback with no "games" param');
      return false;
    }

    try {
      final normalized = base64Url.normalize(gamesParam);
      final jsonBytes = base64Url.decode(normalized);
      final decoded = jsonDecode(utf8.decode(jsonBytes));
      if (decoded is! List) {
        _log.e('RetroArchLibraryService: decoded payload is not a list');
        return false;
      }

      final byFilename = <String, Map<String, dynamic>>{};
      for (final entry in decoded) {
        if (entry is! Map) continue;
        final map = Map<String, dynamic>.from(entry);
        final filename = (map['filename'] ?? map['titleId'])?.toString();
        if (filename == null || filename.isEmpty) continue;
        byFilename[filename] = map;
        // Also index by bare basename, in case RetroArch's "filename"
        // field turns out to be a relative/full path rather than a bare
        // filename in practice — cheap to keep both keys.
        byFilename[path.basename(filename)] = map;
      }

      _cache = byFilename;
      await _persist(byFilename);
      _log.i(
        'RetroArchLibraryService: synced ${decoded.length} games from RetroArch',
      );
      return true;
    } catch (e) {
      _log.e('RetroArchLibraryService: failed to parse library callback: $e');
      return false;
    }
  }

  /// Loads the last-synced library from disk into memory, if not already
  /// loaded this session. Call once at startup so [launchGameByRomPath]
  /// works without needing a fresh sync every cold launch.
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
      _log.e('RetroArchLibraryService: failed loading cached library: $e');
      _cache = {};
    }
  }

  static Future<void> _persist(Map<String, Map<String, dynamic>> data) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefsKey, jsonEncode(data));
    } catch (e) {
      _log.e('RetroArchLibraryService: failed persisting library cache: $e');
    }
  }

  /// Whether a library sync has ever completed (so the UI can prompt the
  /// user to sync if not).
  static bool get hasSyncedLibrary => (_cache?.isNotEmpty ?? false);

  /// Attempts a genuine one-tap launch for [romPath] via RetroArch's
  /// `retroarch://game/<filename>` scheme, matching against the
  /// last-synced library by filename. Returns `true` only if a match was
  /// found AND the URL was opened — callers should fall back to another
  /// launch path otherwise (see GameLaunchService).
  static Future<bool> launchGameByRomPath(String romPath) async {
    final cache = _cache;
    if (cache == null || cache.isEmpty) return false;

    final basename = path.basename(romPath);
    final entry = cache[basename] ?? cache[romPath];
    if (entry == null) return false;

    final filename = (entry['filename'] ?? entry['titleId'])?.toString();
    if (filename == null || filename.isEmpty) return false;

    final uri = Uri(
      scheme: 'retroarch',
      host: 'game',
      pathSegments: [filename],
    );

    try {
      return await launchUrl(uri);
    } catch (e) {
      _log.e('RetroArchLibraryService: failed to launch $uri: $e');
      return false;
    }
  }
}
