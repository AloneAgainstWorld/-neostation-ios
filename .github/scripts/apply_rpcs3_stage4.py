from __future__ import annotations

from pathlib import Path
import re

ROOT = Path('.')


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')


def insert_import(path: str, import_line: str) -> None:
    text = read(path)
    if import_line in text:
        return
    lines = text.splitlines()
    import_indexes = [i for i, line in enumerate(lines) if line.startswith('import ')]
    if not import_indexes:
        raise SystemExit(f'No imports found in {path}')
    lines.insert(import_indexes[-1] + 1, import_line)
    write(path, '\n'.join(lines) + ('\n' if text.endswith('\n') else ''))


# ---------------------------------------------------------------------------
# Build number
# ---------------------------------------------------------------------------
pubspec = read('pubspec.yaml')
pubspec, count = re.subn(
    r'^version:\s*0\.9\.9\+\d+\s*$',
    'version: 0.9.9+132',
    pubspec,
    count=1,
    flags=re.MULTILINE,
)
if count != 1:
    raise SystemExit('Could not update pubspec build number')
write('pubspec.yaml', pubspec)


# ---------------------------------------------------------------------------
# 1. Preserve URI-backed RPCS3 rows during normal filesystem cleanup.
# ---------------------------------------------------------------------------
sqlite_path = 'lib/data/datasources/sqlite_service.dart'
sqlite = read(sqlite_path)
if "lowerPath.startsWith('rpcs3-library://')" not in sqlite:
    persistence_pattern = re.compile(
        r"(lowerPath\.startsWith\('armsx2://'\)\s*\|\|\s*"
        r"lowerPath\.startsWith\('melonx://'\))"
    )
    sqlite, count = persistence_pattern.subn(
        r"\1 ||\n          lowerPath.startsWith('rpcs3-library://')",
        sqlite,
        count=1,
    )
    if count != 1:
        raise SystemExit(
            'Could not locate the ARMSX2/MeloNX virtual-path preservation block'
        )
write(sqlite_path, sqlite)


# ---------------------------------------------------------------------------
# Media payload validation used by both the normal and fallback downloaders.
# ---------------------------------------------------------------------------
validator_path = 'lib/services/screenscraper/media_payload_validator.dart'
validator = r'''import 'dart:convert';
import 'dart:io';

/// Rejects ScreenScraper text/error payloads that were returned with HTTP 200.
///
/// ScreenScraper can answer `NOMEDIA`, checksum status text, JSON or an HTML
/// error page while the transport status is still successful. Saving those
/// bytes with a `.mp4`/`.png` extension makes the UI believe media exists and
/// produces a permanent image fallback or an empty video player.
abstract final class ScreenscraperMediaPayloadValidator {
  static const Set<String> _knownTextErrors = <String>{
    'NOMEDIA',
    'CRCOK',
    'MD5OK',
    'SHA1OK',
    'NO MEDIA',
    'NOT FOUND',
  };

  static bool isValidBytes(
    List<int> bytes, {
    String? extension,
    String? contentType,
  }) {
    if (bytes.length < 4) return false;

    final probeLength = bytes.length < 256 ? bytes.length : 256;
    final probe = utf8
        .decode(bytes.sublist(0, probeLength), allowMalformed: true)
        .trimLeft();
    final upperProbe = probe.toUpperCase();

    if (_knownTextErrors.any(upperProbe.startsWith) ||
        upperProbe.startsWith('<!DOCTYPE') ||
        upperProbe.startsWith('<HTML') ||
        upperProbe.startsWith('{"ERROR"') ||
        upperProbe.startsWith('{"HEADER"') ||
        upperProbe.startsWith('ERROR:')) {
      return false;
    }

    final normalizedExtension = extension
        ?.trim()
        .toLowerCase()
        .replaceFirst('.', '');
    final normalizedContentType = contentType
        ?.split(';')
        .first
        .trim()
        .toLowerCase();

    final isPng = _startsWith(bytes, const <int>[0x89, 0x50, 0x4e, 0x47]);
    final isJpeg = _startsWith(bytes, const <int>[0xff, 0xd8, 0xff]);
    final isGif = _startsWithAscii(bytes, 'GIF87a') ||
        _startsWithAscii(bytes, 'GIF89a');
    final isWebp = bytes.length >= 12 &&
        _startsWithAscii(bytes, 'RIFF') &&
        String.fromCharCodes(bytes.sublist(8, 12)) == 'WEBP';
    final isBmp = _startsWithAscii(bytes, 'BM');
    final isPdf = _startsWithAscii(bytes, '%PDF');
    final isMp4Family = bytes.length >= 12 &&
        String.fromCharCodes(bytes.sublist(4, 8)) == 'ftyp';
    final isWebm = _startsWith(bytes, const <int>[0x1a, 0x45, 0xdf, 0xa3]);
    final isSvg = probe.toLowerCase().startsWith('<svg') ||
        probe.toLowerCase().startsWith('<?xml') &&
            probe.toLowerCase().contains('<svg');

    switch (normalizedExtension) {
      case 'png':
        return isPng;
      case 'jpg':
      case 'jpeg':
        return isJpeg;
      case 'gif':
        return isGif;
      case 'webp':
        return isWebp;
      case 'bmp':
        return isBmp;
      case 'svg':
        return isSvg;
      case 'pdf':
        return isPdf;
      case 'mp4':
      case 'm4v':
      case 'mov':
        return isMp4Family;
      case 'webm':
        return isWebm;
    }

    if (isPng ||
        isJpeg ||
        isGif ||
        isWebp ||
        isBmp ||
        isPdf ||
        isMp4Family ||
        isWebm ||
        isSvg) {
      return true;
    }

    if (normalizedContentType?.startsWith('image/') == true) {
      return bytes.length > 128;
    }
    if (normalizedContentType?.startsWith('video/') == true) {
      return bytes.length > 1024;
    }
    if (normalizedContentType == 'application/pdf') return isPdf;

    return false;
  }

  static Future<bool> isValidFile(File file) async {
    if (!await file.exists()) return false;
    final extension = file.path.split('.').last;
    try {
      return isValidBytes(await file.readAsBytes(), extension: extension);
    } on FileSystemException {
      return false;
    }
  }

  static bool _startsWith(List<int> bytes, List<int> signature) {
    if (bytes.length < signature.length) return false;
    for (var index = 0; index < signature.length; index++) {
      if (bytes[index] != signature[index]) return false;
    }
    return true;
  }

  static bool _startsWithAscii(List<int> bytes, String signature) {
    return _startsWith(bytes, ascii.encode(signature));
  }
}
'''
write(validator_path, validator)


def harden_downloader(path: str) -> None:
    insert_import(
        path,
        "import 'package:neostation/services/screenscraper/media_payload_validator.dart';",
    )
    text = read(path)
    if 'ScreenscraperMediaPayloadValidator.isValidBytes' in text:
        return
    pattern = re.compile(r'response\.statusCode\s*==\s*200')
    replacement = (
        'response.statusCode == 200 &&\n'
        '          ScreenscraperMediaPayloadValidator.isValidBytes(\n'
        '            response.bodyBytes,\n'
        "            contentType: response.headers['content-type'],\n"
        '          )'
    )
    text, count = pattern.subn(replacement, text)
    if count < 1:
        raise SystemExit(f'No HTTP 200 media response block found in {path}')
    write(path, text)


harden_downloader('lib/services/screenscraper/media_downloader.dart')
harden_downloader('lib/services/screenscraper/melonx_media_fallback.dart')


# ---------------------------------------------------------------------------
# 2. Use the generic game-ID fallback for RPCS3 too and clean old bogus files.
# ---------------------------------------------------------------------------
scraper_path = 'lib/services/screenscraper_service.dart'
insert_import(
    scraper_path,
    "import 'screenscraper/media_payload_validator.dart';",
)
scraper = read(scraper_path)

# The fallback helper is generic despite its historical MeloNX name.
occurrences = [m.start() for m in re.finditer(r'if \(isMeloNxVirtual\) \{', scraper)]
replacements = 0
for position in reversed(occurrences):
    nearby = scraper[max(0, position - 3000):position]
    if 'isRpcs3Virtual' not in nearby:
        continue
    scraper = (
        scraper[:position]
        + 'if (isMeloNxVirtual || isRpcs3Virtual) {'
        + scraper[position + len('if (isMeloNxVirtual) {'):]
    )
    replacements += 1
if replacements < 2 and 'if (isMeloNxVirtual || isRpcs3Virtual) {' not in scraper:
    raise SystemExit('Could not enable RPCS3 game-ID media fallback')
write(scraper_path, scraper)


# RPCS3 service: authoritative startup restore and invalid-media cleanup.
rpcs3_path = 'lib/services/rpcs3_library_service.dart'
insert_import(
    rpcs3_path,
    "import 'package:neostation/services/screenscraper/media_payload_validator.dart';",
)
rpcs3 = read(rpcs3_path)

if 'static bool _startupRestoreRunning = false;' not in rpcs3:
    marker = '  static bool _syncCompleted = false;'
    if marker not in rpcs3:
        raise SystemExit('RPCS3 service state marker not found')
    rpcs3 = rpcs3.replace(
        marker,
        marker + '\n  static bool _startupRestoreRunning = false;',
        1,
    )

restore_pattern = re.compile(
    r"  /// Restores cached virtual PS3 rows after SQLite providers are ready\..*?"
    r"^  /// Lets the user select RPCS3's folder, bookmarks it, then performs a sync\.",
    flags=re.MULTILINE | re.DOTALL,
)
restore_replacement = r'''  /// Restores RPCS3 rows only after SQLite providers are ready.
  ///
  /// A security-scoped bookmark is resolved early during startup. The normal
  /// ROM scan, however, runs later and used to remove URI-backed rows before
  /// the UI was refreshed. This method performs an authoritative lightweight
  /// refresh from the linked Data folder when available, otherwise it restores
  /// the last cached metadata set.
  static Future<void> restoreAfterDatabaseReady({
    required SqliteConfigProvider configProvider,
    required SqliteDatabaseProvider databaseProvider,
  }) async {
    if (_startupRestoreRunning) return;
    _startupRestoreRunning = true;

    try {
      await loadCachedLibrary();
      var games = (_cache?.values ?? const <Rpcs3LibraryGame>[]).toList();

      final dataRoot = linkedDataPath;
      if (dataRoot != null) {
        final discovered = await discoverLibrary(dataRoot);
        if (discovered.isNotEmpty || games.isEmpty) games = discovered;
      }

      if (games.isEmpty) {
        _log.i('Rpcs3LibraryService: no cached or linked games to restore.');
        return;
      }

      final result = await _importIntoNeoStation(games);
      final cache = <String, Rpcs3LibraryGame>{
        for (final game in games) game.titleId.toLowerCase(): game,
      };
      _cache = cache;
      _syncCompleted = true;
      await _persistCache();
      await _purgeInvalidCachedMedia(cache.values);

      await databaseProvider.loadGamesForSystem('ps3');
      await configProvider.refreshDetectedSystems();
      _log.i(
        'Rpcs3LibraryService: restored ${games.length} PS3 game(s) after '
        'database initialization (${result.totalPs3Rows} rows).',
      );
    } catch (e, stack) {
      _log.e(
        'Rpcs3LibraryService: startup restore failed',
        error: e,
        stackTrace: stack,
      );
    } finally {
      _startupRestoreRunning = false;
    }
  }

  /// Lets the user select RPCS3's folder, bookmarks it, then performs a sync.'''
rpcs3, count = restore_pattern.subn(restore_replacement, rpcs3, count=1)
if count != 1:
    raise SystemExit('Could not replace RPCS3 startup restore method')

purge_helper = r'''
  static Future<int> _purgeInvalidCachedMedia(
    Iterable<Rpcs3LibraryGame> games,
  ) async {
    final keys = games
        .map((game) => game.titleId.trim().toLowerCase())
        .where((titleId) => titleId.isNotEmpty)
        .toSet();
    if (keys.isEmpty) return 0;

    final mediaRoot = Directory(path.join(await ConfigService.getMediaPath(), 'ps3'));
    if (!await mediaRoot.exists()) return 0;

    const checkedExtensions = <String>{
      'png',
      'jpg',
      'jpeg',
      'gif',
      'webp',
      'bmp',
      'svg',
      'mp4',
      'm4v',
      'mov',
      'webm',
      'pdf',
    };

    var removed = 0;
    try {
      await for (final entity in mediaRoot.list(recursive: true, followLinks: false)) {
        if (entity is! File) continue;
        final extension = path.extension(entity.path).replaceFirst('.', '').toLowerCase();
        if (!checkedExtensions.contains(extension)) continue;
        final mediaKey = path.basenameWithoutExtension(entity.path).toLowerCase();
        if (!keys.contains(mediaKey)) continue;

        final valid = ScreenscraperMediaPayloadValidator.isValidBytes(
          await entity.readAsBytes(),
          extension: extension,
        );
        if (!valid) {
          await entity.delete();
          removed++;
          _log.w('Rpcs3LibraryService: removed invalid media ${entity.path}');
        }
      }
    } catch (e) {
      _log.w('Rpcs3LibraryService: invalid-media cleanup failed: $e');
    }
    return removed;
  }
'''
if '_purgeInvalidCachedMedia(' not in rpcs3:
    marker = '  static Future<void> _writeDebugFile({' 
    if marker not in rpcs3:
        raise SystemExit('RPCS3 debug-file method marker not found')
    rpcs3 = rpcs3.replace(marker, purge_helper + '\n' + marker, 1)

# Clean old HTTP-200 text payloads after each successful full sync as well.
sync_marker = '    await _persistCache();\n\n    await _writeDebugFile('
if sync_marker in rpcs3:
    rpcs3 = rpcs3.replace(
        sync_marker,
        '    await _persistCache();\n    await _purgeInvalidCachedMedia(cache.values);\n\n    await _writeDebugFile(',
        1,
    )
elif 'await _purgeInvalidCachedMedia(cache.values);' not in rpcs3:
    raise SystemExit('RPCS3 sync cache marker not found')
write(rpcs3_path, rpcs3)


# ---------------------------------------------------------------------------
# 3. Natural, shorter synchronized status text in all supported locales.
# ---------------------------------------------------------------------------
locale_path = 'lib/l10n/rpcs3_library_locale.dart'
locale = read(locale_path)
plural_map = r'''  static const Map<String, String> _synced = {
    'de': '{count} PS3-Spiele mit RPCS3 synchronisiert.',
    'en': '{count} PS3 games synced from RPCS3.',
    'es': '{count} juegos de PS3 sincronizados desde RPCS3.',
    'fr': '{count} jeux PS3 synchronisés depuis RPCS3.',
    'id': '{count} game PS3 disinkronkan dari RPCS3.',
    'it': '{count} giochi PS3 sincronizzati da RPCS3.',
    'ja': 'RPCS3 から PS3 ゲーム {count} 本を同期しました。',
    'ko': 'RPCS3에서 PS3 게임 {count}개를 동기화했습니다.',
    'pt': '{count} jogos de PS3 sincronizados do RPCS3.',
    'ru': 'Синхронизировано игр PS3 из RPCS3: {count}.',
    'zh': '已从 RPCS3 同步 {count} 款 PS3 游戏。',
    'zh_Hant': '已從 RPCS3 同步 {count} 款 PS3 遊戲。',
  };

  static const Map<String, String> _syncedSingular = {
    'de': '1 PS3-Spiel mit RPCS3 synchronisiert.',
    'en': '1 PS3 game synced from RPCS3.',
    'es': '1 juego de PS3 sincronizado desde RPCS3.',
    'fr': '1 jeu PS3 synchronisé depuis RPCS3.',
    'id': '1 game PS3 disinkronkan dari RPCS3.',
    'it': '1 gioco PS3 sincronizzato da RPCS3.',
    'ja': 'RPCS3 から PS3 ゲーム 1 本を同期しました。',
    'ko': 'RPCS3에서 PS3 게임 1개를 동기화했습니다.',
    'pt': '1 jogo de PS3 sincronizado do RPCS3.',
    'ru': 'Синхронизирована 1 игра PS3 из RPCS3.',
    'zh': '已从 RPCS3 同步 1 款 PS3 游戏。',
    'zh_Hant': '已從 RPCS3 同步 1 款 PS3 遊戲。',
  };'''
locale_pattern = re.compile(
    r"  static const Map<String, String> _synced = \{.*?^  \};",
    flags=re.MULTILINE | re.DOTALL,
)
locale, count = locale_pattern.subn(plural_map, locale, count=1)
if count != 1:
    raise SystemExit('RPCS3 synchronized locale map not found')
status_pattern = re.compile(
    r"  static String statusSynced\(BuildContext context, int count\)\s*=>\s*"
    r"_lookup\(_synced, context\)\.replaceFirst\('\{count\}', '\$count'\);"
)
status_replacement = r'''  static String statusSynced(BuildContext context, int count) {
    final template = count == 1
        ? _lookup(_syncedSingular, context)
        : _lookup(_synced, context);
    return template.replaceFirst('{count}', '$count');
  }'''
locale, count = status_pattern.subn(status_replacement, locale, count=1)
if count != 1:
    raise SystemExit('RPCS3 statusSynced method not found')
write(locale_path, locale)


# ---------------------------------------------------------------------------
# 4. Keep StikDebug attached until RPCS3 loads its core after Start, then boot
#    the requested Title ID automatically. The explicit UUID guard remains.
# ---------------------------------------------------------------------------
script_path = 'assets/data/rpcs3_stikdebug_launch.js'
script = read(script_path)
if 'let neoInitialDetachSuppressed = false;' not in script:
    script = script.replace(
        'let detached = false;\n',
        'let detached = false;\n'
        'let neoInitialDetachSuppressed = false;\n'
        'let neoCoreBreakpoints = 0;\n'
        'let neoBootAttempted = false;\n',
        1,
    )

launch_block_pattern = re.compile(
    r"function JIT26Detach\(\) \{.*?\n\}\n\nfunction JIT26NewBreakpoints",
    flags=re.DOTALL,
)
launch_block = r'''function JIT26Detach() {
    const core = neoFindRpcs3Core();
    if (core) {
        neoPerformBootAndDetach('detach-with-core', core);
        return;
    }

    // RPCS3 iOS emits one detach request on the pre-core welcome screen. Do
    // not detach there: keep StikDebug attached while the user presses Start.
    // A later core detach (preferred) or a settled series of core JIT region
    // breakpoints will launch the Title ID automatically.
    neoInitialDetachSuppressed = true;
    log('NEOSTATION_RPC_WAITING_FOR_START: core is not loaded; detach suppressed');
}

function neoFindRpcs3Core() {
    const libraryCommand = 'jGetLoadedDynamicLibrariesInfos:{"fetch_all_solibs":true,"information-level":"address-name-uuid"}';
    const rawLibraries = send_command(libraryCommand);
    const jsonStart = rawLibraries ? rawLibraries.indexOf('{') : -1;
    if (jsonStart < 0) return null;
    try {
        const payload = JSON.parse(rawLibraries.substring(jsonStart));
        const images = Array.isArray(payload.images) ? payload.images : [];
        return images.find((image) => String(image.pathname || '').includes('libRPCS3Core.dylib')) || null;
    } catch (error) {
        log(`NEOSTATION_RPC_IMAGE_PARSE_ERROR: ${error}`);
        return null;
    }
}

function neoTryBootAtSafePoint(reason) {
    if (!neoInitialDetachSuppressed || neoBootAttempted || detached) return false;
    const core = neoFindRpcs3Core();
    if (!core) return false;

    // A real detach from the loaded core is the preferred ready signal. Some
    // builds do not emit a second detach, so use a conservative JIT-breakpoint
    // fallback after the core has prepared several executable regions.
    if (reason !== 'detach' && neoCoreBreakpoints < 12) {
        log(`NEOSTATION_RPC_CORE_SETTLING: ${neoCoreBreakpoints}/12 (${reason})`);
        return false;
    }

    neoPerformBootAndDetach(reason, core);
    return true;
}

function neoPerformBootAndDetach(reason, core) {
    if (neoBootAttempted || detached) return;
    neoBootAttempted = true;
    try {
        neoStationBootRpcs3Title(core);
        log(`NEOSTATION_RPC_BOOT_DISPATCHED: ${neoTitleId} (${reason})`);
    } catch (error) {
        log(`NEOSTATION_RPC_BOOT_ERROR: ${error && error.stack ? error.stack : error}`);
    }
    neoDetach(`boot-finished:${reason}`);
}

function neoDetach(reason) {
    const detachResponse = send_command('D');
    log(`NEOSTATION_RPC_DETACH: ${reason}: ${detachResponse}`);
    detached = true;
}

function neoStationBootRpcs3Title(coreOverride) {
    log(`NEOSTATION_RPC_BOOT_REQUEST: ${neoTitleId}`);
    const core = coreOverride || neoFindRpcs3Core();
    if (!core) throw new Error('libRPCS3Core.dylib is not loaded');

    const actualUuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const expectedUuid = neoExpectedCoreUuid.replace(/-/g, '').toUpperCase();
    if (actualUuid !== expectedUuid) {
        throw new Error(`RPCS3 core UUID mismatch: ${actualUuid} != ${expectedUuid}`);
    }

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
    const prep = prepare_memory_region(scratch, 0x4000n);
    log(`NEOSTATION_RPC_SCRATCH: 0x${scratch.toString(16)} prepare=${prep}`);

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

function JIT26NewBreakpoints'''
script, count = launch_block_pattern.subn(launch_block, script, count=1)
if count != 1:
    raise SystemExit('Could not replace RPCS3 StikDebug detach/boot block')

prepare_pattern = re.compile(
    r"(function JIT26PrepareRegion\(brkResponse\) \{.*?)(\n\}\n\nfunction parseRemoteAddress)",
    flags=re.DOTALL,
)
prepare_match = prepare_pattern.search(script)
if not prepare_match:
    raise SystemExit('Could not locate JIT26PrepareRegion')
prepare_body = prepare_match.group(1)
if 'neoCoreBreakpoints++' not in prepare_body:
    prepare_body += r'''
    neoCoreBreakpoints++;
    neoTryBootAtSafePoint('prepare-region');'''
script = (
    script[:prepare_match.start()]
    + prepare_body
    + prepare_match.group(2)
    + script[prepare_match.end():]
)
write(script_path, script)


# Keep the user-facing source docs honest about the remaining one-tap Start gate.
readme_path = 'README.md'
readme = read(readme_path)
readme = re.sub(
    r"- \*\*RPCS3 iOS\*\*[^\n]*",
    '- **RPCS3 iOS** Data-folder library import, persistent cold-start restore, '
    'Title-ID ScreenScraper lookup and an experimental StikDebug-assisted title '
    'launch after RPCS3 loads its core. The current private RPCS3 build still '
    'requires its Start button before the selected game can be dispatched.',
    readme,
    count=1,
)
write(readme_path, readme)


# ---------------------------------------------------------------------------
# Regression tests for payload validation, persistence protection and script.
# ---------------------------------------------------------------------------
test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/screenscraper/media_payload_validator.dart';

void main() {
  group('RPCS3 stage 4', () {
    test('rejects ScreenScraper HTTP-200 text sent as media', () {
      expect(
        ScreenscraperMediaPayloadValidator.isValidBytes(
          'NOMEDIA'.codeUnits,
          extension: 'mp4',
          contentType: 'text/plain',
        ),
        isFalse,
      );
      expect(
        ScreenscraperMediaPayloadValidator.isValidBytes(
          '<html>temporary error</html>'.codeUnits,
          extension: 'png',
          contentType: 'text/html',
        ),
        isFalse,
      );
    });

    test('accepts representative PNG and MP4 signatures', () {
      expect(
        ScreenscraperMediaPayloadValidator.isValidBytes(
          <int>[0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
          extension: 'png',
        ),
        isTrue,
      );
      expect(
        ScreenscraperMediaPayloadValidator.isValidBytes(
          <int>[0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d],
          extension: 'mp4',
        ),
        isTrue,
      );
    });

    test('normal ROM cleanup preserves RPCS3 virtual paths', () async {
      final source = await File(
        'lib/data/datasources/sqlite_service.dart',
      ).readAsString();
      expect(source, contains("lowerPath.startsWith('rpcs3-library://')"));
    });

    test('StikDebug script waits for Start and then dispatches the title', () async {
      final source = await File(
        'assets/data/rpcs3_stikdebug_launch.js',
      ).readAsString();
      expect(source, contains('NEOSTATION_RPC_WAITING_FOR_START'));
      expect(source, contains("neoTryBootAtSafePoint('prepare-region')"));
      expect(source, contains('NEOSTATION_RPC_BOOT_DISPATCHED'));
      expect(source, contains('neoExpectedCoreUuid'));
    });
  });
}
'''
write('test/rpcs3_stage4_test.dart', test)

print('RPCS3 stage 4 source patch applied successfully.')
