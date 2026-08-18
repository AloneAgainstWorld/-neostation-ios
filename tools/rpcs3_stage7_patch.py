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
        raise SystemExit(f'Marker not found in {path}: {old[:180]!r}')
    write(path, text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1. RPCS3 0.2 fingerprint and direct-title boot support.
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

/// Experimental RPCS3 iOS launcher for the exact inspected RPCS3 builds.
///
/// Supported core fingerprints:
///
/// - RPCS3 iOS 0.1 (1): CFE15492-152B-331E-8395-9A3CF9AC8A9F,
///   `rpcs3_ios_boot_game` at 0x2FA18.
/// - RPCS3 iOS 0.2 (1): 5C4D64FF-B799-30AD-879C-13009838F136,
///   `rpcs3_ios_boot_game` at 0x36224.
///
/// iOS suspends long timers once NeoStation leaves the foreground, so the
/// handoff uses a real lifecycle event:
///
/// 1. NeoStation enables Universal JIT and opens RPCS3.
/// 2. The user presses RPCS3's native Start button.
/// 3. The user returns once to NeoStation.
/// 4. NeoStation's `resumed` event launches the fingerprinted direct-title
///    StikDebug pass and returns to RPCS3.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';

  /// UUID -> exported `rpcs3_ios_boot_game` offset from the dylib load address.
  static const Map<String, int> supportedCoreBootOffsets = <String, int>{
    'CFE15492152B331E83959A3CF9AC8A9F': 0x2fa18,
    '5C4D64FFB79930AD879C13009838F136': 0x36224,
  };

  static const String currentCoreUuid =
      '5C4D64FF-B799-30AD-879C-13009838F136';
  static const int currentBootGameOffset = 0x36224;

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
          '__NEOSTATION_SUPPORTED_CORES_JSON__',
          jsonEncode(supportedCoreBootOffsets),
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
    _log.i(
      'RPCS3 launch state: $state'
      '${titleId == null ? '' : ' title=$titleId'}'
      '${extra == null ? '' : ' $extra'}',
    );
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

rpcs3_js = r'''// NeoStation RPCS3 direct title launcher (second StikDebug pass).
// Derived from StikDebug Universal JIT Script (GPL-3.0):
// https://github.com/StikDebug/StikDebug/blob/main/StikDebug/Scripts/universal.js
//
// Pass one has already enabled JIT and the user has pressed RPCS3's native
// Start button. This script attaches to the running process, fingerprints the
// loaded RPCS3 core, chooses the matching exported boot-function offset, calls
// rpcs3_ios_boot_game(title_id), restores registers and detaches. Unknown cores
// fail closed instead of jumping to an unverified address.

const neoTitleId = __NEOSTATION_TITLE_ID_JSON__;
const neoSupportedCoreOffsets = __NEOSTATION_SUPPORTED_CORES_JSON__;
const neoReturnTrapInstruction = 'c0013ed4'; // brk #0xf00e, little endian

let pid = get_pid();
let attachResponse = send_command(`vAttach;${pid.toString(16)}`);
log(`NEOSTATION_RPC_DIRECT_PID: ${pid}`);
log(`NEOSTATION_RPC_DIRECT_ATTACH: ${attachResponse}`);

try {
    const tid = resolveStoppedThread(attachResponse);
    if (!tid) throw new Error('Could not determine a stopped RPCS3 thread');

    const fingerprint = findFingerprintCore();
    if (!fingerprint) {
        log('NEOSTATION_RPC_DIRECT_CORE_NOT_READY');
        throw new Error('libRPCS3Core.dylib is not loaded yet');
    }

    callBootGame(fingerprint.core, fingerprint.bootOffset, tid);
    log(`NEOSTATION_RPC_DIRECT_BOOT_COMPLETED: ${neoTitleId}`);
} catch (error) {
    log(`NEOSTATION_RPC_DIRECT_ERROR: ${error && error.stack ? error.stack : error}`);
} finally {
    const detachResponse = send_command('D');
    log(`NEOSTATION_RPC_DIRECT_DETACH: ${detachResponse}`);
}

function resolveStoppedThread(initialPacket) {
    let packet = initialPacket || '';
    let match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups['tid'];

    packet = send_command('?') || '';
    log(`NEOSTATION_RPC_DIRECT_STOP_PACKET: ${packet}`);
    match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups['tid'];

    const current = send_command('qC') || '';
    log(`NEOSTATION_RPC_DIRECT_CURRENT_THREAD: ${current}`);
    match = /^QC(?<tid>[0-9a-f]+)$/i.exec(current);
    return match ? match.groups['tid'] : null;
}

function findFingerprintCore() {
    const command = 'jGetLoadedDynamicLibrariesInfos:{"fetch_all_solibs":true,"information-level":"address-name-uuid"}';
    const raw = send_command(command);
    const jsonStart = raw ? raw.indexOf('{') : -1;
    if (jsonStart < 0) throw new Error(`No loaded-image JSON: ${raw}`);

    const payload = JSON.parse(raw.substring(jsonStart));
    const images = Array.isArray(payload.images) ? payload.images : [];
    const core = images.find((image) =>
        String(image.pathname || '').includes('libRPCS3Core.dylib'));
    if (!core) return null;

    const actualUuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const rawOffset = neoSupportedCoreOffsets[actualUuid];
    if (rawOffset === undefined || rawOffset === null) {
        throw new Error(
            `Unsupported RPCS3 core UUID: ${actualUuid}; supported=${Object.keys(neoSupportedCoreOffsets).join(',')}`);
    }

    const bootOffset = BigInt(rawOffset);
    log(`NEOSTATION_RPC_DIRECT_FINGERPRINT: uuid=${actualUuid} offset=0x${bootOffset.toString(16)}`);
    return { core: core, bootOffset: bootOffset };
}

function callBootGame(core, bootOffset, tid) {
    const loadAddress = parseRemoteAddress(core.load_address);
    const bootAddress = loadAddress + bootOffset;
    log(`NEOSTATION_RPC_DIRECT_CORE: load=0x${loadAddress.toString(16)} boot=0x${bootAddress.toString(16)}`);

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
    log(`NEOSTATION_RPC_DIRECT_SCRATCH: 0x${scratch.toString(16)} prepare=${prepared}`);

    try {
        const titleHex = asciiToHex(neoTitleId + '\0');
        const titleWrite = send_command(
            `M${scratch.toString(16)},${(titleHex.length / 2).toString(16)}:${titleHex}`);
        if (titleWrite !== 'OK') throw new Error(`Could not write title ID: ${titleWrite}`);

        const trap = scratch + 0x100n;
        const trapWrite = send_command(
            `M${trap.toString(16)},4:${neoReturnTrapInstruction}`);
        if (trapWrite !== 'OK') throw new Error(`Could not write return trap: ${trapWrite}`);

        const x0Write = send_command(
            `P0=${numberToLittleEndianHexString(scratch)};thread:${tid};`);
        const lrWrite = send_command(
            `P1e=${numberToLittleEndianHexString(trap)};thread:${tid};`);
        const pcWrite = send_command(
            `P20=${numberToLittleEndianHexString(bootAddress)};thread:${tid};`);
        if (x0Write !== 'OK' || lrWrite !== 'OK' || pcWrite !== 'OK') {
            throw new Error(`Register write failed: x0=${x0Write} lr=${lrWrite} pc=${pcWrite}`);
        }

        const stop = send_command(`vCont;c:${tid}`);
        log(`NEOSTATION_RPC_DIRECT_BOOT_RETURN: ${stop}`);
        const restore = send_command(`QRestoreRegisterState:${saveId};thread:${tid};`);
        log(`NEOSTATION_RPC_DIRECT_RESTORE: ${restore}`);
        if (restore !== 'OK') throw new Error(`Could not restore registers: ${restore}`);
    } finally {
        send_command(`_m${scratch.toString(16)}`);
    }
}

function parseRemoteAddress(value) {
    if (typeof value === 'number') return BigInt(Math.trunc(value));
    const text = String(value || '').trim();
    if (!text) throw new Error('Missing remote load address');
    return BigInt(text);
}

function asciiToHex(text) {
    let result = '';
    for (let index = 0; index < text.length; index++) {
        result += text.charCodeAt(index).toString(16).padStart(2, '0');
    }
    return result;
}

function numberToLittleEndianHexString(number) {
    const bytes = [];
    let value = number;
    for (let index = 0; index < 8; index++) {
        bytes.push(Number(value & 0xffn));
        value >>= 8n;
    }
    return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
'''
write('assets/data/rpcs3_stikdebug_launch.js', rpcs3_js)


# ---------------------------------------------------------------------------
# 2. Make physical RPCS3 directories authoritative; games.yml is history only.
# ---------------------------------------------------------------------------
lib_path = 'lib/services/rpcs3_library_service.dart'
lib = read(lib_path)
lib = lib.replace(
    "/// RPCS3's `games.yml` map is also read so registered ISO/disc-image entries can\n"
    "/// still appear when their PARAM.SFO is not directly visible to Dart.\n",
    "/// `Data/games/DiscImages`, `Data/games/DiscImgs` (legacy alias),\n"
    "/// `Data/games/ExtractedGames` and `Data/dev_hdd0/game` are authoritative.\n"
    "/// RPCS3's `games.yml` is deliberately not used to create rows because it\n"
    "/// can retain stale or cross-linked registrations after a game is removed.\n",
)

scan_start = lib.index("    await scan(\n      path.join('games', 'DiscImages'),")
scan_end = lib.index("\n    final games = byTitleId.values.toList()", scan_start)
scan_replacement = r'''    for (final discDirectoryName in const <String>[
      'DiscImages',
      'DiscImgs',
    ]) {
      await scan(
        path.join('games', discDirectoryName),
        sourceKind: 'disc-image',
        maxDepth: 5,
        hddRules: false,
      );
      await _addDiscImageFolderFallbacks(
        dataRoot: root.path,
        directoryName: discDirectoryName,
        target: byTitleId,
      );
    }

    // Do not create entries from games.yml. RPCS3 can leave a historical
    // TITLE_ID mapped to another still-existing disc path, which previously
    // resurrected deleted titles such as BLES01484. Physical folders/files are
    // now the sole source of truth for disc-image presence.
'''
lib = lib[:scan_start] + scan_replacement + lib[scan_end:]

helper_marker = "  static Future<String?> _resolveLinkedDataRoot() async {\n"
helper = r'''  static Future<void> _addDiscImageFolderFallbacks({
    required String dataRoot,
    required String directoryName,
    required Map<String, Rpcs3LibraryGame> target,
  }) async {
    final directory = Directory(
      path.join(dataRoot, 'games', directoryName),
    );
    if (!await directory.exists()) return;

    try {
      await for (final entity in directory.list(followLinks: false)) {
        String titleId = '';
        if (entity is Directory) {
          titleId = _cleanTitleId(path.basename(entity.path));
        } else if (entity is File) {
          titleId = _cleanTitleId(path.basenameWithoutExtension(entity.path));
        }
        if (titleId.isEmpty || target.containsKey(titleId.toLowerCase())) {
          continue;
        }

        final iconPath = entity is Directory
            ? await _findFileCaseInsensitive(entity, 'ICON0.PNG') ??
                  await _findCachedIcon(dataRoot, titleId)
            : await _findCachedIcon(dataRoot, titleId);
        _putPreferred(
          target,
          Rpcs3LibraryGame(
            titleId: titleId,
            title: titleId,
            version: '',
            category: '',
            sourcePath: entity.path,
            sourceKind: 'disc-image-folder',
            iconPath: iconPath,
          ),
        );
      }
    } catch (error) {
      _log.w(
        'Rpcs3LibraryService: could not enumerate $directoryName: $error',
      );
    }
  }

'''
if helper not in lib:
    if helper_marker not in lib:
        raise SystemExit('RPCS3 helper insertion marker missing')
    lib = lib.replace(helper_marker, helper + helper_marker, 1)
write(lib_path, lib)


# ---------------------------------------------------------------------------
# 3. Ignore synthetic ScreenScraper names that are only the PS3 serial.
# ---------------------------------------------------------------------------
game_model_path = 'lib/models/game_model.dart'
game_model = read(game_model_path)
old_factory_prefix = r'''  factory GameModel.fromDatabaseModel(DatabaseGameModel db) {
    final scrapedName = db.screenscraperRealName?.trim();
    final isRpcs3Virtual = db.romPath.toLowerCase().startsWith(
      'rpcs3-library://',
    );
    final hasScrapedRpcs3Name =
        isRpcs3Virtual && scrapedName != null && scrapedName.isNotEmpty;
    final displayName = hasScrapedRpcs3Name
        ? scrapedName
        : db.titleName ?? db.realName ?? db.filename;
    final resolvedRealName = hasScrapedRpcs3Name
        ? scrapedName
        : db.realName ?? db.filename;

'''
new_factory_prefix = r'''  static bool isMeaningfulRpcs3MetadataNameForTesting(
    String? value, {
    required String? titleId,
    required String filename,
  }) {
    final name = value?.trim() ?? '';
    if (name.isEmpty) return false;

    String normalize(String candidate) => candidate
        .trim()
        .replaceAll(RegExp(r'\s+'), ' ')
        .toUpperCase();

    final normalized = normalize(name);
    final syntheticNames = <String>{
      if (titleId != null && titleId.trim().isNotEmpty) normalize(titleId),
      normalize(filename),
      normalize(FileProvider.stripRomExtension(filename)),
    };
    return !syntheticNames.contains(normalized);
  }

  factory GameModel.fromDatabaseModel(DatabaseGameModel db) {
    final scrapedName = db.screenscraperRealName?.trim();
    final isRpcs3Virtual = db.romPath.toLowerCase().startsWith(
      'rpcs3-library://',
    );

    final meaningfulScrapedName =
        isRpcs3Virtual &&
            isMeaningfulRpcs3MetadataNameForTesting(
              scrapedName,
              titleId: db.titleId,
              filename: db.filename,
            )
        ? scrapedName
        : null;
    final meaningfulRealName =
        isRpcs3Virtual &&
            isMeaningfulRpcs3MetadataNameForTesting(
              db.realName,
              titleId: db.titleId,
              filename: db.filename,
            )
        ? db.realName?.trim()
        : null;
    final localTitle = db.titleName?.trim();

    final displayName = isRpcs3Virtual
        ? meaningfulScrapedName ??
              meaningfulRealName ??
              ((localTitle?.isNotEmpty ?? false) ? localTitle : null) ??
              db.filename
        : db.titleName ?? db.realName ?? db.filename;
    final resolvedRealName = isRpcs3Virtual
        ? meaningfulRealName ??
              ((localTitle?.isNotEmpty ?? false) ? localTitle : null) ??
              db.filename
        : db.realName ?? db.filename;

'''
if new_factory_prefix not in game_model:
    if old_factory_prefix not in game_model:
        raise SystemExit('GameModel RPCS3 display marker missing')
    game_model = game_model.replace(old_factory_prefix, new_factory_prefix, 1)
write(game_model_path, game_model)


# ---------------------------------------------------------------------------
# 4. Keep iOS Ring/Silent behavior stable when entering Theme/menu music code.
# ---------------------------------------------------------------------------
home_music_path = 'lib/services/home_music_service.dart'
home_music = read(home_music_path)
if "package:external_folder_access/external_folder_access.dart" not in home_music:
    home_music = home_music.replace(
        "import 'package:file_picker/file_picker.dart';\n",
        "import 'package:external_folder_access/external_folder_access.dart';\n"
        "import 'package:file_picker/file_picker.dart';\n",
        1,
    )

old_set_active = r'''  Future<void> setMainMenuActive(bool value) async {
    if (!_initialized) await init();
    if (_mainMenuActive == value) return;

    _mainMenuActive = value;
    await _syncPlayback();
  }
'''
new_set_active = r'''  Future<void> setMainMenuActive(bool value) async {
    final changed = _mainMenuActive != value;
    // Assign before initialization. Theme settings can be created while the
    // Systems widget is being disposed; initializing first used the stale true
    // value and briefly restarted menu music under SoLoud's audio category.
    _mainMenuActive = value;

    if (!_initialized) {
      await init();
      return;
    }
    if (!changed) return;
    await _syncPlayback();
  }

  bool get mainMenuActiveForTesting => _mainMenuActive;
'''
if new_set_active not in home_music:
    if old_set_active not in home_music:
        raise SystemExit('HomeMusic setMainMenuActive marker missing')
    home_music = home_music.replace(old_set_active, new_set_active, 1)

old_start = r'''      // SFX owns the shared engine's normal initialization path and is already
      // concurrency-safe, so using it here avoids two callers racing SoLoud.
      await SfxService().init();
      if (!_shouldPlay || _musicPath == null) return;

      final source = await SoLoud.instance.loadFile(_musicPath!);
      if (!_shouldPlay) {
        await SoLoud.instance.disposeSource(source);
        return;
      }

      _source = source;
      _handle = SoLoud.instance.play(
        source,
        volume: _volume,
        looping: true,
      );
      _log.i('[HomeMusic] Main-menu music started.');
'''
new_start = r'''      // SFX owns the shared engine's normal initialization path and is already
      // concurrency-safe, so using it here avoids two callers racing SoLoud.
      await SfxService().init();
      await _restoreSilentModeAudioSession();
      if (!_shouldPlay || _musicPath == null) return;

      final source = await SoLoud.instance.loadFile(_musicPath!);
      // SoLoud may reactivate its own iOS category while loading/starting a
      // streamed file. Re-apply `.ambient` after each operation so the hardware
      // Ring/Silent switch remains authoritative, including inside Theme.
      await _restoreSilentModeAudioSession();
      if (!_shouldPlay) {
        await SoLoud.instance.disposeSource(source);
        return;
      }

      _source = source;
      _handle = SoLoud.instance.play(
        source,
        volume: _volume,
        looping: true,
      );
      await _restoreSilentModeAudioSession();
      _log.i('[HomeMusic] Main-menu music started.');
'''
if new_start not in home_music:
    if old_start not in home_music:
        raise SystemExit('HomeMusic start marker missing')
    home_music = home_music.replace(old_start, new_start, 1)

sync_marker = r'''  Future<void> _syncPlayback() async {
    if (_shouldPlay) {
      await _startPlayback();
    } else {
      await _stopPlayback();
    }
  }

'''
sync_replacement = sync_marker + r'''  Future<void> _restoreSilentModeAudioSession() async {
    try {
      await ExternalFolderAccess.configureAudioSessionForSilentMode();
    } catch (error) {
      _log.w('[HomeMusic] Could not restore iOS silent-mode session: $error');
    }
  }

  Future<void> _restoreSilentModeAndSync() async {
    await _restoreSilentModeAudioSession();
    await _syncPlayback();
  }

'''
if '_restoreSilentModeAndSync' not in home_music:
    if sync_marker not in home_music:
        raise SystemExit('HomeMusic sync marker missing')
    home_music = home_music.replace(sync_marker, sync_replacement, 1)

home_music = home_music.replace(
    "      unawaited(_syncPlayback());\n",
    "      unawaited(_restoreSilentModeAndSync());\n",
    1,
)
write(home_music_path, home_music)

sfx_path = 'lib/services/sfx_service.dart'
sfx = read(sfx_path)
sfx = sfx.replace(
    "      await ExternalFolderAccess.configureAudioSessionForSilentMode();\n",
    "      await _restoreSilentModeAudioSession();\n",
    1,
)
ready_marker = r'''      _isInitialized = true;
      _log.i(
        '[SfxService] Ready. ${_sources.length}/${allPaths.length} sounds loaded.',
      );
'''
ready_replacement = r'''      // Asset loading can make the backend reactivate a non-ambient category.
      await _restoreSilentModeAudioSession();
      _isInitialized = true;
      _log.i(
        '[SfxService] Ready. ${_sources.length}/${allPaths.length} sounds loaded.',
      );
'''
if ready_replacement not in sfx:
    if ready_marker not in sfx:
        raise SystemExit('Sfx ready marker missing')
    sfx = sfx.replace(ready_marker, ready_replacement, 1)

play_marker = r'''  Future<void> _play(String path) async {
    final source = _sources[path];
    if (source == null) {
      _log.w('[SfxService] Source not found for: $path');
      return;
    }
    try {
      SoLoud.instance.play(source, volume: _volume);
    } catch (e) {
      _log.w('[SfxService] Playback error for $path: $e');
    }
  }

'''
play_replacement = r'''  Future<void> _play(String path) async {
    final source = _sources[path];
    if (source == null) {
      _log.w('[SfxService] Source not found for: $path');
      return;
    }
    try {
      // Another shared-engine client may have changed AVAudioSession since SFX
      // initialization. Reassert `.ambient` immediately before every UI sound.
      await _restoreSilentModeAudioSession();
      SoLoud.instance.play(source, volume: _volume);
    } catch (e) {
      _log.w('[SfxService] Playback error for $path: $e');
    }
  }

  Future<void> _restoreSilentModeAudioSession() async {
    try {
      await ExternalFolderAccess.configureAudioSessionForSilentMode();
    } catch (error) {
      _log.w('[SfxService] Could not restore iOS silent-mode session: $error');
    }
  }

'''
if play_replacement not in sfx:
    if play_marker not in sfx:
        raise SystemExit('Sfx play marker missing')
    sfx = sfx.replace(play_marker, play_replacement, 1)
write(sfx_path, sfx)

themes_path = 'lib/screens/settings_screen/new_settings_options/themes_settings_content.dart'
themes = read(themes_path)
old_theme_init = r'''    HomeMusicService().addListener(_onHomeMusicChanged);
    HomeMusicService().init().then((_) {
      if (mounted) setState(() {});
    });
'''
new_theme_init = r'''    final homeMusic = HomeMusicService();
    homeMusic.addListener(_onHomeMusicChanged);
    // Theme is never the Systems main menu. Set the visibility state before
    // initialization so entering this panel cannot restart menu music.
    homeMusic.setMainMenuActive(false).then((_) {
      if (mounted) setState(() {});
    });
'''
if new_theme_init not in themes:
    if old_theme_init not in themes:
        raise SystemExit('Theme HomeMusic init marker missing')
    themes = themes.replace(old_theme_init, new_theme_init, 1)
write(themes_path, themes)

app_screen_path = 'lib/screens/app_screen.dart'
app_screen = read(app_screen_path)
if "services/home_music_service.dart" not in app_screen:
    app_screen = app_screen.replace(
        "import 'package:neostation/services/game_service.dart';\n",
        "import 'package:neostation/services/game_service.dart';\n"
        "import 'package:neostation/services/home_music_service.dart';\n",
        1,
    )
old_tab = r'''  void _onTabSelected(int index) {
    setState(() {
      _selectedTabIndex = index;
      _selectedSystemIndex = 0;
    });
'''
new_tab = r'''  void _onTabSelected(int index) {
    if (index != AppTabs.systems) {
      // Stop ambience immediately, before the outgoing Systems widget's
      // asynchronous dispose/post-frame callbacks can race the destination tab.
      unawaited(HomeMusicService().setMainMenuActive(false));
    }

    setState(() {
      _selectedTabIndex = index;
      _selectedSystemIndex = 0;
    });
'''
if new_tab not in app_screen:
    if old_tab not in app_screen:
        raise SystemExit('AppScreen tab marker missing')
    app_screen = app_screen.replace(old_tab, new_tab, 1)
write(app_screen_path, app_screen)


# ---------------------------------------------------------------------------
# 5. Regression tests and build number.
# ---------------------------------------------------------------------------
rpcs3_test_path = 'test/rpcs3_stage3_test.dart'
rpcs3_test = read(rpcs3_test_path)
rpcs3_test = rpcs3_test.replace(
    "      expect(script, contains(Rpcs3LaunchService.expectedCoreUuid));\n",
    "      expect(script, contains('5C4D64FFB79930AD879C13009838F136'));\n"
    "      expect(script, contains('221732'));\n"
    "      expect(script, contains('CFE15492152B331E83959A3CF9AC8A9F'));\n",
)
name_test_marker = r'''    test('scraped RPCS3 name replaces the local fallback title', () {
'''
name_test = r'''    test('synthetic ScreenScraper serial falls back to PARAM.SFO title', () {
      final game = GameModel.fromDatabaseModel(
        DatabaseGameModel(
          filename: 'BLES00412',
          romPath: 'rpcs3-library://game?title-id=BLES00412',
          titleId: 'BLES00412',
          titleName: 'The Lord of the Rings: Conquest™',
          realName: 'BLES00412',
          screenscraperRealName: 'BLES00412',
        ),
      );
      expect(game.name, 'The Lord of the Rings: Conquest™');
      expect(game.realname, 'The Lord of the Rings: Conquest™');
    });

'''
if name_test not in rpcs3_test:
    if name_test_marker not in rpcs3_test:
        raise SystemExit('RPCS3 name test insertion marker missing')
    rpcs3_test = rpcs3_test.replace(name_test_marker, name_test + name_test_marker, 1)
write(rpcs3_test_path, rpcs3_test)

library_test_path = 'test/rpcs3_library_service_test.dart'
library_test = read(library_test_path)
block_start = library_test.index(
    "    test('discovers HDD, extracted and games.yml ISO entries', () async {"
)
block_end = library_test.index(
    "    test('ignores stale games.yml registrations whose target is gone'",
    block_start,
)
new_library_test = r'''    test('uses physical folders and ignores cross-linked games.yml history', () async {
      final temp = await Directory.systemTemp.createTemp('rpcs3-library-test');
      addTearDown(() => temp.delete(recursive: true));
      final dataRoot = Directory(path.join(temp.path, 'Data'));
      await dataRoot.create(recursive: true);

      final hddGame = Directory(
        path.join(dataRoot.path, 'dev_hdd0', 'game', 'NPUB12345'),
      );
      await hddGame.create(recursive: true);
      await File(path.join(hddGame.path, 'PARAM.SFO')).writeAsBytes(
        _buildSfo(<String, Object>{
          'TITLE_ID': 'NPUB12345',
          'TITLE': 'Installed HDD Game',
          'CATEGORY': 'HG',
          'APP_VER': '01.00',
        }),
      );

      final extractedMetadata = Directory(
        path.join(
          dataRoot.path,
          'games',
          'ExtractedGames',
          'Disc Folder',
          'PS3_GAME',
        ),
      );
      await extractedMetadata.create(recursive: true);
      await File(path.join(extractedMetadata.path, 'PARAM.SFO')).writeAsBytes(
        _buildSfo(<String, Object>{
          'TITLE_ID': 'BLES54321',
          'TITLE': 'Extracted Disc Game',
          'CATEGORY': 'DG',
          'APP_VER': '01.01',
        }),
      );

      final realDiscMetadata = Directory(
        path.join(
          dataRoot.path,
          'games',
          'DiscImages',
          'BLES00540',
          'PS3_GAME',
        ),
      );
      await realDiscMetadata.create(recursive: true);
      await File(path.join(realDiscMetadata.path, 'PARAM.SFO')).writeAsBytes(
        _buildSfo(<String, Object>{
          'TITLE_ID': 'BLES00540',
          'TITLE': 'Dynasty Warriors 6 Empires',
          'CATEGORY': 'DG',
          'APP_VER': '01.00',
        }),
      );
      await File(
        path.join(realDiscMetadata.parent.path, 'disc.iso'),
      ).writeAsBytes(const <int>[]);

      final fallbackFolder = Directory(
        path.join(dataRoot.path, 'games', 'DiscImages', 'BLES77777'),
      );
      await fallbackFolder.create(recursive: true);

      // Historical corruption observed on-device: deleted BLES01484 points to
      // the still-existing BLES00540 ISO. The physical folder must win and the
      // stale ID must never be recreated.
      await File(path.join(dataRoot.path, 'games.yml')).writeAsString(
        'BLES01484: "${path.join(realDiscMetadata.parent.path, 'disc.iso')}"\n',
      );

      final games = await Rpcs3LibraryService.discoverLibrary(dataRoot.path);
      final byId = <String, Rpcs3LibraryGame>{
        for (final game in games) game.titleId: game,
      };

      expect(
        byId.keys,
        containsAll(<String>[
          'NPUB12345',
          'BLES54321',
          'BLES00540',
          'BLES77777',
        ]),
      );
      expect(byId.containsKey('BLES01484'), isFalse);
      expect(byId['BLES00540']!.title, 'Dynasty Warriors 6 Empires');
      expect(byId['BLES77777']!.sourceKind, 'disc-image-folder');
    });

'''
library_test = library_test[:block_start] + new_library_test + library_test[block_end:]
write(library_test_path, library_test)

home_test = r'''import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/home_music_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Theme visibility is committed before HomeMusic initialization', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final service = HomeMusicService();

    await service.setMainMenuActive(true);
    expect(service.mainMenuActiveForTesting, isTrue);

    await service.setMainMenuActive(false);
    expect(service.mainMenuActiveForTesting, isFalse);
  });
}
'''
write('test/home_music_silent_mode_test.dart', home_test)

pubspec_path = 'pubspec.yaml'
pubspec = read(pubspec_path)
if 'version: 0.9.9+136' not in pubspec:
    if 'version: 0.9.9+135' not in pubspec:
        raise SystemExit('Unexpected NeoStation version')
    pubspec = pubspec.replace('version: 0.9.9+135', 'version: 0.9.9+136', 1)
write(pubspec_path, pubspec)

print('RPCS3 Stage 7 and silent-mode patch applied.')
