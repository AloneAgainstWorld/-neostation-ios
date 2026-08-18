from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    Path(path).write_text(content, encoding='utf-8')


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'Marker not found in {path}: {old[:160]!r}')
    write(path, text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1. Refresh stale iOS security-scoped bookmarks after an IPA update/re-sign.
# ---------------------------------------------------------------------------
swift_path = 'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift'
swift = read(swift_path)
old_resolve = '''            guard url.startAccessingSecurityScopedResource() else {
                result(
                    FlutterError(
                        code: "ACCESS_DENIED",
                        message: "startAccessingSecurityScopedResource returned false",
                        details: nil
                    )
                )
                return
            }
            result(url.path)
'''
new_resolve = '''            guard url.startAccessingSecurityScopedResource() else {
                result(
                    FlutterError(
                        code: "ACCESS_DENIED",
                        message: "startAccessingSecurityScopedResource returned false",
                        details: nil
                    )
                )
                return
            }

            // Sideload updates/re-signing can make an otherwise resolvable
            // bookmark stale. Refresh it immediately while the security scope
            // is active so subsequent cold launches keep the same folder grant.
            if isStale {
                do {
                    let refreshedBookmark = try url.bookmarkData(
                        options: [],
                        includingResourceValuesForKeys: nil,
                        relativeTo: nil
                    )
                    UserDefaults.standard.set(
                        refreshedBookmark,
                        forKey: Self.bookmarkDefaultsKey(for: key)
                    )
                } catch {
                    // The currently resolved URL is still usable for this
                    // process. Keep it rather than failing the whole launch;
                    // the next relink can replace the bookmark if necessary.
                    print("ExternalFolderAccess: failed refreshing stale bookmark for \\(key): \\(error)")
                }
            }
            result(url.path)
'''
if new_resolve not in swift:
    if old_resolve not in swift:
        raise SystemExit('Bookmark resolve marker missing')
    swift = swift.replace(old_resolve, new_resolve, 1)
write(swift_path, swift)


# ---------------------------------------------------------------------------
# 2. Make RPCS3 cold-start reconciliation observable and cache-independent.
# ---------------------------------------------------------------------------
lib_path = 'lib/services/rpcs3_library_service.dart'
lib = read(lib_path)
old_restore = '''  static Future<void> restoreAfterDatabaseReady({
    required SqliteConfigProvider configProvider,
    required SqliteDatabaseProvider databaseProvider,
  }) async {
    await loadCachedLibrary();
    if (!Platform.isIOS) return;

    final dataRoot = await _resolveLinkedDataRoot();
    if (dataRoot != null) {
      try {
        final discovered = await discoverLibrary(dataRoot);
        final games = await _applyTitleFallbacks(
          discovered,
          allowNetwork: false,
        );
        final result = await _importIntoNeoStation(games);
        await _replaceCache(games);
        await _writeDebugFile(dataRoot: dataRoot, games: games, result: result);
        await databaseProvider.loadGamesForSystem('ps3');
        await configProvider.refreshDetectedSystems();
        _log.i(
          'Rpcs3LibraryService: reconciled ${games.length} live PS3 game(s) '
          'after database initialization; removed ${result.removedRows} stale '
          'row(s).',
        );

        // Keep startup fast by using the disk/seed title catalog first. A
        // background refresh can enrich unresolved serials without delaying
        // the first usable frame.
        unawaited(
          _refreshCatalogAfterStartup(
            dataRoot: dataRoot,
            games: games,
            configProvider: configProvider,
            databaseProvider: databaseProvider,
          ),
        );
        return;
      } catch (error) {
        _log.w(
          'Rpcs3LibraryService: live startup reconciliation failed; '
          'falling back to cache: $error',
        );
      }
    }

    final cache = _cache;
    if (!_syncCompleted || cache == null || cache.isEmpty) return;
    try {
      await _importIntoNeoStation(cache.values.toList());
      await databaseProvider.loadGamesForSystem('ps3');
      await configProvider.refreshDetectedSystems();
      _log.i(
        'Rpcs3LibraryService: restored ${cache.length} cached PS3 game(s) '
        'because the linked Data folder was unavailable.',
      );
    } catch (error) {
      _log.e('Rpcs3LibraryService: startup cache restore failed: $error');
    }
  }
'''
new_restore = '''  static Future<void> restoreAfterDatabaseReady({
    required SqliteConfigProvider configProvider,
    required SqliteDatabaseProvider databaseProvider,
  }) async {
    await loadCachedLibrary();
    if (!Platform.isIOS) return;

    final dataRoot = await _resolveLinkedDataRoot();
    final dataRootReadable =
        dataRoot != null && await _canReadDataRoot(dataRoot);

    if (dataRootReadable) {
      try {
        final discovered = await discoverLibrary(dataRoot);
        final games = await _applyTitleFallbacks(
          discovered,
          allowNetwork: false,
        );
        final result = await _importIntoNeoStation(games);
        await _replaceCache(games);
        await _writeDebugFile(dataRoot: dataRoot, games: games, result: result);
        await _writeStartupDebugFile(
          mode: 'LIVE_RECONCILE',
          dataRoot: dataRoot,
          readable: true,
          gameCount: games.length,
          removedRows: result.removedRows,
        );
        await databaseProvider.loadGamesForSystem('ps3');
        await configProvider.refreshDetectedSystems();
        _log.i(
          'Rpcs3LibraryService: reconciled ${games.length} live PS3 game(s) '
          'after database initialization; removed ${result.removedRows} stale '
          'row(s).',
        );

        unawaited(
          _refreshCatalogAfterStartup(
            dataRoot: dataRoot,
            games: games,
            configProvider: configProvider,
            databaseProvider: databaseProvider,
          ),
        );
        return;
      } catch (error) {
        _log.w(
          'Rpcs3LibraryService: live startup reconciliation failed; '
          'falling back to cache: $error',
        );
        await _writeStartupDebugFile(
          mode: 'LIVE_RECONCILE_FAILED',
          dataRoot: dataRoot,
          readable: true,
          error: error.toString(),
        );
      }
    } else {
      await _writeStartupDebugFile(
        mode: 'BOOKMARK_UNAVAILABLE',
        dataRoot: dataRoot,
        readable: false,
      );
    }

    final cache = _cache;
    if (!_syncCompleted || cache == null || cache.isEmpty) return;
    try {
      // Build 133 only enriched names on the live-folder path. When an IPA
      // update invalidated the folder bookmark, the old cache therefore kept
      // raw serials such as BLES00412 forever. Apply the disk/seed catalog to
      // cached rows as well, independently of folder access.
      final cachedGames = await _applyTitleFallbacks(
        cache.values.toList(),
        allowNetwork: false,
      );
      await _importIntoNeoStation(cachedGames);
      await _replaceCache(cachedGames);
      await _writeStartupDebugFile(
        mode: 'CACHE_FALLBACK',
        dataRoot: dataRoot,
        readable: false,
        gameCount: cachedGames.length,
      );
      await databaseProvider.loadGamesForSystem('ps3');
      await configProvider.refreshDetectedSystems();
      _log.i(
        'Rpcs3LibraryService: restored ${cachedGames.length} cached PS3 game(s) '
        'because the linked Data folder was unavailable.',
      );

      // Retry live access after the rest of the app has reached a stable
      // foreground state. This catches security-scope timing issues without
      // blocking startup and, when successful, removes stale rows immediately.
      unawaited(
        _retryLiveReconcileAfterStartup(
          configProvider: configProvider,
          databaseProvider: databaseProvider,
        ),
      );
      unawaited(
        _refreshCachedCatalogAfterStartup(
          games: cachedGames,
          configProvider: configProvider,
          databaseProvider: databaseProvider,
        ),
      );
    } catch (error) {
      _log.e('Rpcs3LibraryService: startup cache restore failed: $error');
    }
  }
'''
if new_restore not in lib:
    if old_restore not in lib:
        raise SystemExit('restoreAfterDatabaseReady marker missing')
    lib = lib.replace(old_restore, new_restore, 1)

# Insert helpers immediately before _normalizeDataRoot.
marker = '''  static Future<String?> _normalizeDataRoot(String selectedPath) async {
'''
helpers = '''  static Future<bool> _canReadDataRoot(String dataRoot) async {
    try {
      final directory = Directory(dataRoot);
      if (!await directory.exists()) return false;
      // Listing zero entries is still a successful access probe. The point is
      // to distinguish an empty RPCS3 library from a sandbox/bookmark failure.
      await directory.list(followLinks: false).take(1).toList();
      return true;
    } catch (error) {
      _log.w('Rpcs3LibraryService: Data-root read probe failed: $error');
      return false;
    }
  }

  static Future<void> _retryLiveReconcileAfterStartup({
    required SqliteConfigProvider configProvider,
    required SqliteDatabaseProvider databaseProvider,
  }) async {
    await Future<void>.delayed(const Duration(seconds: 3));
    final dataRoot = await _resolveLinkedDataRoot();
    if (dataRoot == null || !await _canReadDataRoot(dataRoot)) {
      await _writeStartupDebugFile(
        mode: 'DELAYED_RECONCILE_UNAVAILABLE',
        dataRoot: dataRoot,
        readable: false,
      );
      return;
    }

    try {
      final discovered = await discoverLibrary(dataRoot);
      final games = await _applyTitleFallbacks(
        discovered,
        allowNetwork: false,
      );
      final result = await _importIntoNeoStation(games);
      await _replaceCache(games);
      await _writeDebugFile(dataRoot: dataRoot, games: games, result: result);
      await _writeStartupDebugFile(
        mode: 'DELAYED_LIVE_RECONCILE',
        dataRoot: dataRoot,
        readable: true,
        gameCount: games.length,
        removedRows: result.removedRows,
      );
      await databaseProvider.loadGamesForSystem('ps3');
      await configProvider.refreshDetectedSystems();
    } catch (error) {
      await _writeStartupDebugFile(
        mode: 'DELAYED_RECONCILE_FAILED',
        dataRoot: dataRoot,
        readable: true,
        error: error.toString(),
      );
    }
  }

  static Future<void> _refreshCachedCatalogAfterStartup({
    required List<Rpcs3LibraryGame> games,
    required SqliteConfigProvider configProvider,
    required SqliteDatabaseProvider databaseProvider,
  }) async {
    try {
      final enriched = await _applyTitleFallbacks(games, allowNetwork: true);
      var changed = enriched.length != games.length;
      if (!changed) {
        for (var index = 0; index < games.length; index++) {
          if (games[index].title != enriched[index].title) {
            changed = true;
            break;
          }
        }
      }
      if (!changed) return;

      await _importIntoNeoStation(enriched);
      await _replaceCache(enriched);
      await databaseProvider.loadGamesForSystem('ps3');
      await configProvider.refreshDetectedSystems();
      _log.i('Rpcs3LibraryService: enriched cached PS3 titles in background.');
    } catch (error) {
      _log.w('Rpcs3LibraryService: cached title enrichment failed: $error');
    }
  }

  static Future<void> _writeStartupDebugFile({
    required String mode,
    required String? dataRoot,
    required bool readable,
    int? gameCount,
    int? removedRows,
    String? error,
  }) async {
    try {
      final docs = await getApplicationDocumentsDirectory();
      final file = File(path.join(docs.path, 'rpcs3_startup_debug.txt'));
      await file.writeAsString(
        'Timestamp: ${DateTime.now().toIso8601String()}\\n'
        'Mode: $mode\\n'
        'Data root: ${dataRoot ?? '<none>'}\\n'
        'Readable: $readable\\n'
        'Cache count: ${_cache?.length ?? 0}\\n'
        'Game count: ${gameCount ?? -1}\\n'
        'Removed rows: ${removedRows ?? -1}\\n'
        'Error: ${error ?? '<none>'}\\n',
        flush: true,
      );
    } catch (_) {}
  }

'''
if helpers not in lib:
    if marker not in lib:
        raise SystemExit('library helper insertion marker missing')
    lib = lib.replace(marker, helpers + marker, 1)
write(lib_path, lib)


# ---------------------------------------------------------------------------
# 3. Resolve RPCS3 names from the catalog inside ScreenScraper itself too.
# ---------------------------------------------------------------------------
scraper_path = 'lib/services/screenscraper_service.dart'
scraper = read(scraper_path)
if "rpcs3_title_catalog_service.dart" not in scraper:
    scraper = scraper.replace(
        "import 'package:neostation/services/logger_service.dart';\n",
        "import 'package:neostation/services/logger_service.dart';\n"
        "import 'package:neostation/services/rpcs3_title_catalog_service.dart';\n",
        1,
    )

single_marker = '''      final lowerRomPath = romPath.toLowerCase();
      final isMeloNxVirtual = lowerRomPath.startsWith('melonx://');
      final isRpcs3Virtual = lowerRomPath.startsWith('rpcs3-library://');

      Map<String, dynamic>? gameInfoResult;
'''
single_replacement = '''      final lowerRomPath = romPath.toLowerCase();
      final isMeloNxVirtual = lowerRomPath.startsWith('melonx://');
      final isRpcs3Virtual = lowerRomPath.startsWith('rpcs3-library://');
      var effectiveGameName = gameName;
      if (isRpcs3Virtual &&
          !shouldRetryRpcs3ByNameForTesting(effectiveGameName, serialNumber) &&
          (serialNumber?.trim().isNotEmpty ?? false)) {
        effectiveGameName =
            await Rpcs3TitleCatalogService.resolveTitle(serialNumber!) ??
            effectiveGameName;
      }

      Map<String, dynamic>? gameInfoResult;
'''
if single_replacement not in scraper:
    if single_marker not in scraper:
        raise SystemExit('single scrape RPCS3 marker missing')
    scraper = scraper.replace(single_marker, single_replacement, 1)

# Only within scrapeSingleGame section, replace gameName uses before manual section.
single_section_start = scraper.index('  static Future<Map<String, dynamic>> scrapeSingleGame({')
single_section_end = scraper.index('  /// Downloads only the PDF manual', single_section_start)
single_section = scraper[single_section_start:single_section_end]
single_section = single_section.replace('? gameName\n              : null,', '? effectiveGameName\n              : null,')
single_section = single_section.replace('shouldRetryRpcs3ByNameForTesting(gameName, serialNumber)', 'shouldRetryRpcs3ByNameForTesting(effectiveGameName, serialNumber)')
single_section = single_section.replace('gameName: gameName,\n          serialNumber: null,', 'gameName: effectiveGameName,\n          serialNumber: null,')
scraper = scraper[:single_section_start] + single_section + scraper[single_section_end:]

# Batch worker: enrich titleName before the first lookup.
batch_marker = '''      final titleName = rom['title_name']?.toString();
      final titleId = rom['title_id']?.toString().trim();
      final lowerRomPath = romPath.toLowerCase();
      final isMeloNxVirtual = lowerRomPath.startsWith('melonx://');
      final isRpcs3Virtual = lowerRomPath.startsWith('rpcs3-library://');
      final displayName =
'''
batch_replacement = '''      final titleName = rom['title_name']?.toString();
      final titleId = rom['title_id']?.toString().trim();
      final lowerRomPath = romPath.toLowerCase();
      final isMeloNxVirtual = lowerRomPath.startsWith('melonx://');
      final isRpcs3Virtual = lowerRomPath.startsWith('rpcs3-library://');
      var effectiveTitleName = titleName;
      if (isRpcs3Virtual &&
          !shouldRetryRpcs3ByNameForTesting(effectiveTitleName, titleId) &&
          (titleId?.isNotEmpty ?? false)) {
        effectiveTitleName =
            await Rpcs3TitleCatalogService.resolveTitle(titleId!) ??
            effectiveTitleName;
      }
      final displayName =
'''
if batch_replacement not in scraper:
    if batch_marker not in scraper:
        raise SystemExit('batch scrape RPCS3 marker missing')
    scraper = scraper.replace(batch_marker, batch_replacement, 1)

# Batch lookup and retry should use effective title.
worker_start = scraper.index('  static Future<Map<String, dynamic>> _processSingleRomThread({')
worker_end = scraper.index('\n  static Future<void> _saveGameMetadata', worker_start)
worker = scraper[worker_start:worker_end]
worker = worker.replace('(titleName?.trim().isNotEmpty ?? false)', '(effectiveTitleName?.trim().isNotEmpty ?? false)')
worker = worker.replace('? titleName!.trim()\n          : filename;', '? effectiveTitleName!.trim()\n          : filename;')
worker = worker.replace('? titleName\n            : null,', '? effectiveTitleName\n            : null,')
worker = worker.replace('shouldRetryRpcs3ByNameForTesting(titleName, titleId)', 'shouldRetryRpcs3ByNameForTesting(effectiveTitleName, titleId)')
worker = worker.replace('gameName: titleName,\n          serialNumber: null,', 'gameName: effectiveTitleName,\n          serialNumber: null,')
scraper = scraper[:worker_start] + worker + scraper[worker_end:]
write(scraper_path, scraper)


# ---------------------------------------------------------------------------
# 4. Replace background-timer two-pass launch with a deterministic resume pass.
# ---------------------------------------------------------------------------
launch_service = r'''import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Experimental RPCS3 iOS launcher for the exact RPCS3 build inspected by the
/// NeoStation project.
///
/// iOS suspends long timers once NeoStation leaves the foreground, so the old
/// timed two-pass sequence could never reliably reach its second StikDebug
/// request. Stage 6 makes the handoff deterministic:
///
/// 1. NeoStation enables Universal JIT and opens RPCS3.
/// 2. The user presses RPCS3's native Start button.
/// 3. The user returns once to NeoStation.
/// 4. NeoStation's real `resumed` lifecycle event immediately launches the
///    fingerprinted direct-title StikDebug pass and then returns to RPCS3.
///
/// This intentionally adds one app-switch while proving the private boot call
/// reliably before a future Shortcut is allowed to automate the same resume.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';
  static const String expectedCoreUuid = 'CFE15492-152B-331E-8395-9A3CF9AC8A9F';
  static const int bootGameOffset = 0x2fa18;
  static const String _assetPath = 'assets/data/rpcs3_stikdebug_launch.js';
  static const String _pendingTitleKey = 'rpcs3_pending_launch_title';
  static const String _pendingStartedKey = 'rpcs3_pending_launch_started_ms';
  static const Duration _minimumReturnDelay = Duration(seconds: 8);
  static const Duration _pendingLifetime = Duration(minutes: 10);

  static final _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');
  static _Rpcs3ResumeObserver? _observer;
  static bool _continuationInFlight = false;
  static bool _launchWasBackgrounded = false;

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  static Future<void> initialize() async {
    if (!Platform.isIOS || _observer != null) return;
    _observer = _Rpcs3ResumeObserver();
    WidgetsBinding.instance.addObserver(_observer!);
    await _discardExpiredPendingLaunch();
  }

  @visibleForTesting
  static String buildScriptForTesting(String template, String titleId) {
    final normalized = normalizeTitleId(titleId);
    if (normalized == null) {
      throw const FormatException('Invalid RPCS3 title ID.');
    }
    return template
        .replaceAll('__NEOSTATION_TITLE_ID_JSON__', jsonEncode(normalized))
        .replaceAll(
          '__NEOSTATION_CORE_UUID_JSON__',
          jsonEncode(expectedCoreUuid),
        )
        .replaceAll(
          '__NEOSTATION_BOOT_OFFSET_HEX__',
          bootGameOffset.toRadixString(16),
        );
  }

  @visibleForTesting
  static bool shouldContinuePendingForTesting({
    required DateTime now,
    required DateTime startedAt,
    required bool launchWasBackgrounded,
  }) {
    final age = now.difference(startedAt);
    return launchWasBackgrounded &&
        age >= _minimumReturnDelay &&
        age <= _pendingLifetime;
  }

  static Future<bool> launchTitle(String? rawTitleId) async {
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null || !Platform.isIOS) return false;
    await initialize();

    try {
      final prefs = await SharedPreferences.getInstance();
      final now = DateTime.now();
      await prefs.setString(_pendingTitleKey, titleId);
      await prefs.setInt(_pendingStartedKey, now.millisecondsSinceEpoch);
      _launchWasBackgrounded = false;
      _continuationInFlight = false;
      await _writeLaunchState(
        'FIRST_PASS_REQUESTED',
        titleId: titleId,
        extra: 'Return to NeoStation once after pressing Start in RPCS3.',
      );

      // This first-pass path is already proven on-device: StikDebug Universal
      // prepares JIT, and the native helper opens RPCS3 after the warm-up.
      final opened = await ExternalFolderAccess.openAppAfterJitPreflight(
        targetBaseBundleId: targetBundleId,
        warmupDelay: const Duration(seconds: 11),
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      if (opened == true) return true;

      await _clearPendingLaunch(reason: 'FIRST_PASS_FAILED');
      return false;
    } catch (e, stack) {
      await _clearPendingLaunch(reason: 'FIRST_PASS_EXCEPTION');
      _log.e(
        'Rpcs3LaunchService: could not start title $titleId',
        error: e,
        stackTrace: stack,
      );
      return false;
    }
  }

  static void handleLifecycleState(AppLifecycleState state) {
    if (!Platform.isIOS) return;
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.inactive) {
      _launchWasBackgrounded = true;
      return;
    }
    if (state == AppLifecycleState.resumed) {
      unawaited(_continuePendingLaunchOnResume());
    }
  }

  static Future<void> _continuePendingLaunchOnResume() async {
    if (_continuationInFlight || !_launchWasBackgrounded) return;

    final prefs = await SharedPreferences.getInstance();
    final titleId = normalizeTitleId(prefs.getString(_pendingTitleKey));
    final startedMs = prefs.getInt(_pendingStartedKey);
    if (titleId == null || startedMs == null) return;

    final startedAt = DateTime.fromMillisecondsSinceEpoch(startedMs);
    final now = DateTime.now();
    if (!shouldContinuePendingForTesting(
      now: now,
      startedAt: startedAt,
      launchWasBackgrounded: _launchWasBackgrounded,
    )) {
      if (now.difference(startedAt) > _pendingLifetime) {
        await _clearPendingLaunch(reason: 'PENDING_EXPIRED');
      }
      return;
    }

    _continuationInFlight = true;
    _launchWasBackgrounded = false;
    try {
      final template = await rootBundle.loadString(_assetPath);
      final script = buildScriptForTesting(template, titleId);
      final scriptData = base64Url
          .encode(utf8.encode(script))
          .replaceAll('=', '');
      await _writeLaunchState(
        'SECOND_PASS_REQUESTED',
        titleId: titleId,
        extra: 'NeoStation resumed after RPCS3 Start.',
      );

      // One short background return is much more reliable than the old chain
      // of 10+10+6 second timers. The second StikDebug request is initiated
      // while NeoStation is actually foregrounded.
      final opened = await ExternalFolderAccess.openAppAfterJitPreflight(
        targetBaseBundleId: targetBundleId,
        warmupDelay: const Duration(seconds: 5),
        scriptName: 'neostation-rpcs3-direct.js',
        scriptDataBase64Url: scriptData,
        debugFileName: 'rpcs3_launch_second_pass_debug.txt',
      );
      await _writeLaunchState(
        opened == true ? 'SECOND_PASS_OPENED' : 'SECOND_PASS_FAILED',
        titleId: titleId,
      );
    } catch (e, stack) {
      _log.e(
        'Rpcs3LaunchService: second pass failed for $titleId',
        error: e,
        stackTrace: stack,
      );
      await _writeLaunchState(
        'SECOND_PASS_EXCEPTION',
        titleId: titleId,
        extra: e.toString(),
      );
    } finally {
      await _clearPendingLaunch(reason: 'SECOND_PASS_FINISHED');
      _continuationInFlight = false;
    }
  }

  static Future<void> _discardExpiredPendingLaunch() async {
    final prefs = await SharedPreferences.getInstance();
    final startedMs = prefs.getInt(_pendingStartedKey);
    if (startedMs == null) return;
    final age = DateTime.now().difference(
      DateTime.fromMillisecondsSinceEpoch(startedMs),
    );
    if (age > _pendingLifetime) {
      await _clearPendingLaunch(reason: 'STARTUP_PENDING_EXPIRED');
    }
  }

  static Future<void> _clearPendingLaunch({required String reason}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_pendingTitleKey);
      await prefs.remove(_pendingStartedKey);
      await _writeLaunchState(reason);
    } catch (_) {}
  }

  static Future<void> _writeLaunchState(
    String state, {
    String? titleId,
    String? extra,
  }) async {
    try {
      final directory = await Directory.systemTemp.createTemp();
      // The native JIT helper writes the detailed user-visible file in
      // Documents. Dart logging here deliberately stays lightweight.
      await directory.delete(recursive: true);
      _log.i(
        'RPCS3 launch state: $state'
        '${titleId == null ? '' : ' title=$titleId'}'
        '${extra == null ? '' : ' $extra'}',
      );
    } catch (_) {}
  }
}

final class _Rpcs3ResumeObserver with WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    Rpcs3LaunchService.handleLifecycleState(state);
  }
}
'''
write('lib/services/rpcs3_launch_service.dart', launch_service)

# Main startup needs to install the lifecycle observer before a launch occurs.
main_path = 'lib/main.dart'
main = read(main_path)
if "package:neostation/services/rpcs3_launch_service.dart" not in main:
    main = main.replace(
        "import 'package:neostation/services/rpcs3_library_service.dart';\n",
        "import 'package:neostation/services/rpcs3_library_service.dart';\n"
        "import 'package:neostation/services/rpcs3_launch_service.dart';\n",
        1,
    )
main = main.replace(
    '    await Rpcs3LibraryService.initialize();\n',
    '    await Rpcs3LibraryService.initialize();\n'
    '    await Rpcs3LaunchService.initialize();\n',
    1,
)
write(main_path, main)


# ---------------------------------------------------------------------------
# 5. Tests and build number.
# ---------------------------------------------------------------------------
test_path = 'test/rpcs3_stage6_test.dart'
write(test_path, r'''import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:neostation/services/rpcs3_title_catalog_service.dart';

void main() {
  group('RPCS3 Stage 6 reliability', () {
    test('cached raw serial receives GameDB title even without live folder', () async {
      final enriched = await Rpcs3LibraryService.applyTitleCatalogForTesting(
        const <Rpcs3LibraryGame>[
          Rpcs3LibraryGame(
            titleId: 'BLES00412',
            title: 'BLES00412',
            version: '',
            category: '',
            sourcePath: '/unavailable/RPCS3/Data/game.iso',
            sourceKind: 'games.yml',
          ),
        ],
        const <String, String>{
          'BLES00412': 'The Lord of the Rings: Conquest',
        },
      );
      expect(enriched.single.title, 'The Lord of the Rings: Conquest');
    });

    test('GameDB normalization accepts dashed PS3 serials', () {
      expect(
        Rpcs3TitleCatalogService.normalizeTitleId('BLES-00412'),
        'BLES00412',
      );
    });

    test('resume pass only arms after a real background interval', () {
      final started = DateTime.utc(2026, 8, 18, 12);
      expect(
        Rpcs3LaunchService.shouldContinuePendingForTesting(
          now: started.add(const Duration(seconds: 3)),
          startedAt: started,
          launchWasBackgrounded: true,
        ),
        isFalse,
      );
      expect(
        Rpcs3LaunchService.shouldContinuePendingForTesting(
          now: started.add(const Duration(seconds: 12)),
          startedAt: started,
          launchWasBackgrounded: true,
        ),
        isTrue,
      );
      expect(
        Rpcs3LaunchService.shouldContinuePendingForTesting(
          now: started.add(const Duration(seconds: 12)),
          startedAt: started,
          launchWasBackgrounded: false,
        ),
        isFalse,
      );
    });

    test('direct-launch template still receives exact title and fingerprint', () {
      const template = 'title=__NEOSTATION_TITLE_ID_JSON__ '
          'uuid=__NEOSTATION_CORE_UUID_JSON__ '
          'offset=__NEOSTATION_BOOT_OFFSET_HEX__';
      final rendered = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00412',
      );
      expect(rendered, contains(jsonEncode('BLES00412')));
      expect(rendered, contains(Rpcs3LaunchService.expectedCoreUuid));
      expect(rendered, isNot(contains('__NEOSTATION_')));
    });
  });
}
''')

pubspec_path = 'pubspec.yaml'
pubspec = read(pubspec_path)
if 'version: 0.9.9+135' not in pubspec:
    if 'version: 0.9.9+134' not in pubspec:
        raise SystemExit('Unexpected NeoStation version')
    pubspec = pubspec.replace('version: 0.9.9+134', 'version: 0.9.9+135', 1)
write(pubspec_path, pubspec)

print('RPCS3 Stage 6 patch applied.')
