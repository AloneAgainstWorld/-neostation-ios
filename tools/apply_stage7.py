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


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'Marker not found in {path}: {old[:160]!r}')
    write(path, text.replace(old, new, 1))


def insert_after(path: str, marker: str, addition: str) -> None:
    text = read(path)
    if addition in text:
        return
    if marker not in text:
        raise SystemExit(f'Insertion marker not found in {path}: {marker!r}')
    write(path, text.replace(marker, marker + addition, 1))


def add_import(path: str, import_line: str, after: str | None = None) -> None:
    text = read(path)
    if import_line in text:
        return
    if after is not None:
        marker = after + '\n'
        if marker not in text:
            raise SystemExit(f'Import anchor not found in {path}: {after}')
        text = text.replace(marker, marker + import_line + '\n', 1)
    else:
        matches = list(re.finditer(r'^import .*?;\n', text, flags=re.MULTILINE))
        if not matches:
            raise SystemExit(f'No import block found in {path}')
        index = matches[-1].end()
        text = text[:index] + import_line + '\n' + text[index:]
    write(path, text)


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
pubspec = read('pubspec.yaml')
pubspec, count = re.subn(
    r'^version:\s*0\.9\.9\+\d+\s*$',
    'version: 0.9.9+137',
    pubspec,
    count=1,
    flags=re.MULTILINE,
)
if count != 1:
    raise SystemExit('Could not update NeoStation build number')
write('pubspec.yaml', pubspec)


# ---------------------------------------------------------------------------
# 1. Central iOS audio policy.
# ---------------------------------------------------------------------------
audio_policy = r'''import 'dart:async';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_soloud/flutter_soloud.dart';

import 'logger_service.dart';

/// Single source of truth for NeoStation's iOS audio-session policy.
///
/// iOS does not expose a supported API that reports the hardware Ring/Silent
/// switch state. The reliable contract is therefore to keep every NeoStation
/// audio backend under AVAudioSession's `.ambient` category, which iOS mutes
/// immediately while the switch is silent and restores automatically when it
/// is not. SoLoud and AVPlayer may reactivate their own category during
/// initialization or playback, so all callers reassert the policy through this
/// serialized service before and after backend-mutating operations.
class AudioPolicyService with WidgetsBindingObserver {
  AudioPolicyService._internal();

  static final AudioPolicyService _instance = AudioPolicyService._internal();
  factory AudioPolicyService() => _instance;

  final LoggerService _log = LoggerService.instance;
  Future<void> _serial = Future<void>.value();
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    WidgetsBinding.instance.addObserver(this);
    await ensureSilentCompatibleSession(reason: 'startup');
  }

  /// Reasserts the native `.ambient` session in call order.
  ///
  /// Failures are logged but never allowed to break navigation or playback.
  Future<void> ensureSilentCompatibleSession({required String reason}) {
    if (!Platform.isIOS) return Future<void>.value();

    final completion = Completer<void>();
    _serial = _serial.then((_) async {
      try {
        final configured =
            await ExternalFolderAccess.configureAudioSessionForSilentMode();
        if (configured != true) {
          _log.w('[AudioPolicy] Native ambient session was not confirmed ($reason).');
        }
      } catch (error) {
        _log.w('[AudioPolicy] Could not apply ambient session ($reason): $error');
      } finally {
        if (!completion.isCompleted) completion.complete();
      }
    });
    return completion.future;
  }

  /// Starts a SoLoud voice without allowing a category-reset sound leak.
  ///
  /// The voice begins at zero volume, the native session is reasserted after
  /// SoLoud's `play` call, then the user's configured volume is restored.
  Future<SoundHandle> playSoLoud(
    AudioSource source, {
    required double volume,
    bool looping = false,
    required String reason,
  }) async {
    await initialize();
    await ensureSilentCompatibleSession(reason: '$reason:before-play');
    final handle = SoLoud.instance.play(source, volume: 0.0, looping: looping);
    await ensureSilentCompatibleSession(reason: '$reason:after-play');
    if (SoLoud.instance.getIsValidVoiceHandle(handle)) {
      SoLoud.instance.setVolume(handle, volume.clamp(0.0, 1.0).toDouble());
    }
    return handle;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(ensureSilentCompatibleSession(reason: 'app-resumed'));
    }
  }
}
'''
write('lib/services/audio_policy_service.dart', audio_policy)

add_import(
    'lib/main.dart',
    "import 'package:neostation/services/audio_policy_service.dart';",
    after="import 'package:neostation/services/sfx_service.dart';",
)
replace_once(
    'lib/main.dart',
    """  final log = LoggerService.instance;
  await log.init();
  log.i('Starting NeoStation...');
""",
    """  final log = LoggerService.instance;
  await log.init();
  log.i('Starting NeoStation...');

  // Establish one iOS audio-session policy before SoLoud or AVPlayer can
  // create an output. The service is a no-op on other platforms.
  await AudioPolicyService().initialize();
""",
)

sfx_path = 'lib/services/sfx_service.dart'
sfx = read(sfx_path)
sfx = sfx.replace(
    "import 'package:external_folder_access/external_folder_access.dart';\n",
    "import 'package:neostation/services/audio_policy_service.dart';\n",
)
sfx = sfx.replace(
    "await _restoreSilentModeAudioSession();",
    "await AudioPolicyService().ensureSilentCompatibleSession(\n        reason: 'sfx-engine-or-assets',\n      );",
)
old_sfx_play = """      // Another shared-engine client may have changed AVAudioSession since SFX
      // initialization. Reassert `.ambient` immediately before every UI sound.
      await _restoreSilentModeAudioSession();
      SoLoud.instance.play(source, volume: _volume);
"""
new_sfx_play = """      await AudioPolicyService().playSoLoud(
        source,
        volume: _volume,
        reason: 'ui-sfx:$path',
      );
"""
if old_sfx_play not in sfx:
    pattern = re.compile(
        r"\s*// Another shared-engine client.*?\n"
        r"\s*await AudioPolicyService\(\)\.ensureSilentCompatibleSession\(.*?\);\n"
        r"\s*SoLoud\.instance\.play\(source, volume: _volume\);",
        flags=re.DOTALL,
    )
    sfx, replaced = pattern.subn('\n' + new_sfx_play.rstrip(), sfx, count=1)
    if replaced != 1:
        raise SystemExit('Could not replace SFX playback block')
else:
    sfx = sfx.replace(old_sfx_play, new_sfx_play, 1)
sfx = re.sub(
    r"\n  Future<void> _restoreSilentModeAudioSession\(\) async \{.*?\n  \}\n",
    '\n',
    sfx,
    count=1,
    flags=re.DOTALL,
)
write(sfx_path, sfx)

home_path = 'lib/services/home_music_service.dart'
home = read(home_path)
home = home.replace(
    "import 'package:external_folder_access/external_folder_access.dart';\n",
    "import 'package:neostation/services/audio_policy_service.dart';\n",
)
old_home_wrapper = r'''  Future<void> _restoreSilentModeAudioSession() async {
    try {
      await ExternalFolderAccess.configureAudioSessionForSilentMode();
    } catch (error) {
      _log.w('[HomeMusic] Could not restore iOS silent-mode session: $error');
    }
  }
'''
new_home_wrapper = r'''  Future<void> _restoreSilentModeAudioSession() => AudioPolicyService()
      .ensureSilentCompatibleSession(reason: 'home-music');
'''
if old_home_wrapper not in home:
    raise SystemExit('HomeMusic audio-session wrapper marker missing')
home = home.replace(old_home_wrapper, new_home_wrapper, 1)
old_home_play = """      _source = source;
      _handle = SoLoud.instance.play(source, volume: _volume, looping: true);
      await _restoreSilentModeAudioSession();
"""
new_home_play = """      _source = source;
      _handle = await AudioPolicyService().playSoLoud(
        source,
        volume: _volume,
        looping: true,
        reason: 'home-music-loop',
      );
"""
if old_home_play not in home:
    raise SystemExit('HomeMusic play block missing')
home = home.replace(old_home_play, new_home_play, 1)
write(home_path, home)

music_path = 'lib/services/music_player_service.dart'
music = read(music_path)
if "import 'package:neostation/services/audio_policy_service.dart';" not in music:
    music = music.replace(
        "import 'package:neostation/services/sfx_service.dart';\n",
        "import 'package:neostation/services/sfx_service.dart';\n"
        "import 'package:neostation/services/audio_policy_service.dart';\n",
        1,
    )
old_music_init = """      if (!_soloud!.isInitialized) {
        await _soloud!.init();
      }

      _soloud!.setVisualizationEnabled(true);
"""
new_music_init = """      if (!_soloud!.isInitialized) {
        await _soloud!.init();
      }
      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'music-player-init',
      );

      _soloud!.setVisualizationEnabled(true);
"""
if old_music_init not in music:
    raise SystemExit('MusicPlayer init marker missing')
music = music.replace(old_music_init, new_music_init, 1)
old_music_play = """            _logger.d(\"Playing audio source...\");
            _currentHandle = SoLoud.instance.play(
              _currentSource!,
              volume: _isDucked ? _volume * 0.5 : _volume,
            );
"""
new_music_play = """            _logger.d(\"Playing audio source...\");
            _currentHandle = await AudioPolicyService().playSoLoud(
              _currentSource!,
              volume: _isDucked ? _volume * 0.5 : _volume,
              reason: 'music-player-track',
            );
"""
if old_music_play not in music:
    raise SystemExit('MusicPlayer play marker missing')
music = music.replace(old_music_play, new_music_play, 1)
write(music_path, music)

swift_path = 'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift'
swift = read(swift_path)
observer_fields = r'''
    /// Reasserts `.ambient` whenever iOS or an audio backend resets the shared
    /// session. One observer set covers SoLoud, AVPlayer and every UI surface.
    private var audioPolicyObservers: [NSObjectProtocol] = []
    private var audioPolicyObserversInstalled = false
'''
field_marker = '    private var channel: FlutterMethodChannel?\n'
if observer_fields not in swift:
    if field_marker not in swift:
        raise SystemExit('Swift channel field marker missing')
    swift = swift.replace(field_marker, field_marker + observer_fields, 1)
swift = swift.replace(
    '        case "configureAudioSessionForSilentMode":\n            configureAudioSessionForSilentMode(result: result)\n',
    '        case "configureAudioSessionForSilentMode":\n            configureAudioSessionForSilentMode(result: result)\n'
    '        case "openJitRequest":\n            openJitRequest(call: call, result: result)\n',
    1,
)
old_audio_method = r'''    /// Uses the AVAudioSession category intended for non-primary app audio.
    /// `.ambient` is silenced by the iPhone Ring/Silent switch and mixes with
    /// audio from other apps. NeoStation reapplies this after SoLoud starts,
    /// because the audio backend may activate a different category during init.
    private func configureAudioSessionForSilentMode(result: @escaping FlutterResult) {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.ambient, mode: .default, options: [.mixWithOthers])
            try session.setActive(true)
            result(true)
        } catch {
            result(
                FlutterError(
                    code: "AUDIO_SESSION_FAILED",
                    message: error.localizedDescription,
                    details: nil
                )
            )
        }
    }
'''
new_audio_method = r'''    /// Uses the AVAudioSession category intended for non-primary app audio.
    /// `.ambient` is silenced by the iPhone Ring/Silent switch and mixes with
    /// audio from other apps. A single observer set reapplies it after route,
    /// media-service and lifecycle resets caused by SoLoud or AVPlayer.
    private func configureAudioSessionForSilentMode(result: @escaping FlutterResult) {
        installAudioPolicyObserversIfNeeded()
        do {
            try applyAmbientAudioSession(reason: "flutter-request")
            result(true)
        } catch {
            result(
                FlutterError(
                    code: "AUDIO_SESSION_FAILED",
                    message: error.localizedDescription,
                    details: nil
                )
            )
        }
    }

    private func applyAmbientAudioSession(reason: String) throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.ambient, mode: .default, options: [.mixWithOthers])
        try session.setActive(true)
    }

    private func installAudioPolicyObserversIfNeeded() {
        guard !audioPolicyObserversInstalled else { return }
        audioPolicyObserversInstalled = true
        let center = NotificationCenter.default

        func observe(_ name: Notification.Name, reason: String) {
            let token = center.addObserver(
                forName: name,
                object: nil,
                queue: .main
            ) { [weak self] _ in
                do {
                    try self?.applyAmbientAudioSession(reason: reason)
                } catch {
                    print("ExternalFolderAccess audio policy (\(reason)) failed: \(error)")
                }
            }
            self.audioPolicyObservers.append(token)
        }

        observe(UIApplication.didBecomeActiveNotification, reason: "app-active")
        observe(AVAudioSession.routeChangeNotification, reason: "route-change")
        observe(
            AVAudioSession.mediaServicesWereResetNotification,
            reason: "media-services-reset"
        )
        observe(AVAudioSession.interruptionNotification, reason: "interruption")
    }
'''
if old_audio_method not in swift:
    raise SystemExit('Swift audio method marker missing')
swift = swift.replace(old_audio_method, new_audio_method, 1)
open_jit_method = r'''
    // MARK: - Direct StikDebug request

    /// Opens one `stikjit://enable-jit` request and does nothing afterwards.
    /// StikDebug owns process launch/attach and resumption. NeoStation no longer
    /// schedules a UIApplication.open call while backgrounded, which iOS
    /// rejected in the previous RPCS3 flow.
    private func openJitRequest(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        guard let args = call.arguments as? [String: Any],
            let targetBaseBundleId = args["targetBaseBundleId"] as? String,
            !targetBaseBundleId.isEmpty
        else {
            result(
                FlutterError(
                    code: "INVALID_ARGS",
                    message: "openJitRequest requires targetBaseBundleId",
                    details: nil
                )
            )
            return
        }

        let currentBundleId = Bundle.main.bundleIdentifier ?? ""
        let sideloadSuffix = Self.currentSideloadBundleSuffix()
        let targetBundleId = sideloadSuffix.map {
            "\(targetBaseBundleId).\($0)"
        } ?? targetBaseBundleId
        let scriptName = ((args["scriptName"] as? String) ?? "universal.js")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let debugFileName = Self.safeDebugFileName(
            (args["debugFileName"] as? String) ?? "jit_request_debug.txt"
        )

        var components = URLComponents()
        components.scheme = "stikjit"
        components.host = "enable-jit"
        components.queryItems = [
            URLQueryItem(name: "bundle-id", value: targetBundleId),
            URLQueryItem(name: "script-name", value: scriptName),
        ]
        if let scriptData = args["scriptData"] as? String,
            !scriptData.isEmpty
        {
            components.queryItems?.append(
                URLQueryItem(name: "script-data", value: scriptData)
            )
        }

        guard let url = components.url else {
            result(
                FlutterError(
                    code: "INVALID_JIT_URL",
                    message: "Could not construct StikDebug request URL",
                    details: nil
                )
            )
            return
        }

        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: true,
            message: "STATE: JIT_REQUEST\n"
                + "NeoStation bundle: \(currentBundleId)\n"
                + "Target base bundle: \(targetBaseBundleId)\n"
                + "Target effective bundle: \(targetBundleId)\n"
                + "Application state: \(Self.applicationStateName())\n"
                + "Script: \(scriptName)\n"
                + "URL: \(url.absoluteString)"
        )

        UIApplication.shared.open(url, options: [:]) { opened in
            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: opened ? "STATE: JIT_REQUEST_OPENED" : "STATE: JIT_REQUEST_FAILED"
            )
            result(opened)
        }
    }
'''
preflight_marker = '    // MARK: - Explicit StikDebug JIT preflight\n'
if open_jit_method not in swift:
    if preflight_marker not in swift:
        raise SystemExit('Swift preflight marker missing')
    swift = swift.replace(preflight_marker, open_jit_method + '\n' + preflight_marker, 1)
write(swift_path, swift)

external_path = 'packages/external_folder_access/lib/external_folder_access.dart'
external = read(external_path)
open_jit_dart = r'''
  /// Opens one StikDebug JIT request without scheduling any later app launch.
  ///
  /// StikDebug launches or attaches to the target process itself. Avoiding a
  /// delayed `UIApplication.open` is essential because iOS rejects that call
  /// once NeoStation has moved to the background.
  static Future<bool?> openJitRequest({
    required String targetBaseBundleId,
    String scriptName = 'universal.js',
    String? scriptDataBase64Url,
    String debugFileName = 'jit_request_debug.txt',
  }) async {
    if (!Platform.isIOS) return null;
    try {
      return await _channel.invokeMethod<bool>('openJitRequest', {
        'targetBaseBundleId': targetBaseBundleId,
        'scriptName': scriptName,
        if (scriptDataBase64Url != null) 'scriptData': scriptDataBase64Url,
        'debugFileName': debugFileName,
      });
    } on PlatformException {
      return false;
    }
  }

'''
dart_marker = '  /// Starts StikDebug explicitly for [targetBaseBundleId], asking it to use\n'
if open_jit_dart not in external:
    if dart_marker not in external:
        raise SystemExit('Dart JIT wrapper insertion marker missing')
    external = external.replace(dart_marker, open_jit_dart + dart_marker, 1)
write(external_path, external)

list_path = 'lib/services/game/game_list_service.dart'
list_text = read(list_path)
old_resolver_open = r'''  static ({String name, bool showRomFileNameSubtitle}) _resolveListDisplayName({
    required DatabaseGameModel dbGame,
    required bool preferFileName,
    required bool hideExtension,
    required bool hideParentheses,
    required bool hideBrackets,
    required Set<String> validExtensionsSet,
  }) {
    final filename = dbGame.filename;
'''
new_resolver_open = r'''  static ({String name, bool showRomFileNameSubtitle}) _resolveListDisplayName({
    required DatabaseGameModel dbGame,
    required bool preferFileName,
    required bool hideExtension,
    required bool hideParentheses,
    required bool hideBrackets,
    required Set<String> validExtensionsSet,
  }) {
    final isRpcs3Virtual = dbGame.romPath.toLowerCase().startsWith(
      'rpcs3-library://',
    );
    if (isRpcs3Virtual) {
      final resolved = GameModel.fromDatabaseModel(dbGame);
      return (name: resolved.name, showRomFileNameSubtitle: false);
    }

    final filename = dbGame.filename;
'''
if old_resolver_open not in list_text:
    raise SystemExit('GameList display resolver marker missing')
list_text = list_text.replace(old_resolver_open, new_resolver_open, 1)
write(list_path, list_text)

library_path = 'lib/services/rpcs3_library_service.dart'
library = read(library_path)
cache_marker = r'''  static Future<void> _replaceCache(List<Rpcs3LibraryGame> games) async {
'''
lookup_helper = r'''  /// Returns the latest physical RPCS3 discovery record for a Title ID.
  static Rpcs3LibraryGame? gameForTitleId(String? rawTitleId) {
    final titleId = _cleanTitleId(rawTitleId ?? '');
    if (titleId.isEmpty) return null;
    return _cache?[titleId.toLowerCase()];
  }

'''
if lookup_helper not in library:
    if cache_marker not in library:
        raise SystemExit('RPCS3 cache marker missing')
    library = library.replace(cache_marker, lookup_helper + cache_marker, 1)
upsert_tail = r'''          <Object?>[
            systemId,
            syntheticFilename,
            virtualPath,
            game.titleId,
            game.title,
          ],
        );

        if (game.iconPath != null) {
'''
upsert_repair = r"""          <Object?>[
            systemId,
            syntheticFilename,
            virtualPath,
            game.titleId,
            game.title,
          ],
        );

        // Older builds could persist the raw serial as a ScreenScraper name.
        // Remove only that synthetic value; descriptive scraped metadata stays
        // intact and continues to outrank PARAM.SFO titles.
        await txn.rawUpdate(
          '''
          UPDATE user_screenscraper_metadata
          SET real_name = NULL,
              updated_at = datetime('now')
          WHERE app_system_id = ? AND filename = ?
            AND upper(trim(COALESCE(real_name, ''))) IN (?, ?)
          ''',
          <Object?>[
            systemId,
            syntheticFilename,
            game.titleId.toUpperCase(),
            '${game.titleId.toUpperCase()}.RPCS3',
          ],
        );

        if (game.iconPath != null) {
"""
if upsert_tail not in library:
    raise SystemExit('RPCS3 virtual upsert marker missing')
library = library.replace(upsert_tail, upsert_repair, 1)
write(library_path, library)

launch_game_path = 'lib/services/game/game_launch_service.dart'
launch_game = read(launch_game_path)
old_launch_call = r'''          await FavoritesService.recordGamePlayed(game);
          final launched = await Rpcs3LaunchService.launchTitle(titleId);
'''
new_launch_call = r'''          await FavoritesService.recordGamePlayed(game);
          final libraryGame = Rpcs3LibraryService.gameForTitleId(titleId);
          final launched = await Rpcs3LaunchService.launchTitle(
            titleId,
            displayTitle: game.name,
            sourcePath: libraryGame?.sourcePath,
            sourceKind: libraryGame?.sourceKind,
          );
'''
if old_launch_call not in launch_game:
    raise SystemExit('RPCS3 launch call marker missing')
launch_game = launch_game.replace(old_launch_call, new_launch_call, 1)
write(launch_game_path, launch_game)

rpcs3_launch_service = r'''import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Experimental RPCS3 iOS launcher for the exact inspected RPCS3 cores.
///
/// Pass one asks StikDebug to run Universal JIT. After RPCS3's Start screen has
/// initialized the core, returning once to NeoStation sends a second StikDebug
/// request containing the selected game and a fingerprinted state-aware script.
/// No delayed UIApplication.open call is used: those calls were rejected once
/// NeoStation entered the background on real devices.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';

  static const Map<String, Map<String, int>> supportedCoreFunctions =
      <String, Map<String, int>>{
        'CFE15492152B331E83959A3CF9AC8A9F': <String, int>{
          'boot': 0x2fa18,
          'state': 0x30254,
          'progress': 0x302c4,
          'lastError': 0x316b4,
        },
        '5C4D64FFB79930AD879C13009838F136': <String, int>{
          'boot': 0x36224,
          'state': 0x36a8c,
          'progress': 0x36afc,
          'lastError': 0x37f34,
        },
      };

  static const String _assetPath = 'assets/data/rpcs3_stikdebug_launch.js';
  static const String _pendingTitleKey = 'rpcs3_pending_launch_title';
  static const String _pendingDisplayTitleKey =
      'rpcs3_pending_launch_display_title';
  static const String _pendingSourcePathKey =
      'rpcs3_pending_launch_source_path';
  static const String _pendingSourceKindKey =
      'rpcs3_pending_launch_source_kind';
  static const String _pendingSessionKey = 'rpcs3_pending_launch_session';
  static const String _pendingStartedKey = 'rpcs3_pending_launch_started_ms';
  static const Duration _pendingLifetime = Duration(minutes: 10);

  static final LoggerService _log = LoggerService.instance;
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
  static String buildScriptForTesting(
    String template,
    String titleId, {
    String? displayTitle,
    String? sourcePath,
    String? sourceKind,
    String? sessionId,
  }) {
    final normalized = normalizeTitleId(titleId);
    if (normalized == null) {
      throw const FormatException('Invalid RPCS3 title ID.');
    }
    return template
        .replaceAll('__NEOSTATION_TITLE_ID_JSON__', jsonEncode(normalized))
        .replaceAll(
          '__NEOSTATION_DISPLAY_TITLE_JSON__',
          jsonEncode(displayTitle?.trim() ?? ''),
        )
        .replaceAll(
          '__NEOSTATION_SOURCE_PATH_JSON__',
          jsonEncode(sourcePath?.trim() ?? ''),
        )
        .replaceAll(
          '__NEOSTATION_SOURCE_KIND_JSON__',
          jsonEncode(sourceKind?.trim() ?? ''),
        )
        .replaceAll(
          '__NEOSTATION_SESSION_ID_JSON__',
          jsonEncode(sessionId?.trim() ?? ''),
        )
        .replaceAll(
          '__NEOSTATION_SUPPORTED_CORES_JSON__',
          jsonEncode(supportedCoreFunctions),
        );
  }

  static Future<bool> launchTitle(
    String? rawTitleId, {
    String? displayTitle,
    String? sourcePath,
    String? sourceKind,
  }) async {
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null || !Platform.isIOS) return false;
    await initialize();

    final now = DateTime.now();
    final sessionId = '${now.microsecondsSinceEpoch}-$titleId';
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_pendingTitleKey, titleId);
      await prefs.setString(_pendingDisplayTitleKey, displayTitle?.trim() ?? '');
      await prefs.setString(_pendingSourcePathKey, sourcePath?.trim() ?? '');
      await prefs.setString(_pendingSourceKindKey, sourceKind?.trim() ?? '');
      await prefs.setString(_pendingSessionKey, sessionId);
      await prefs.setInt(_pendingStartedKey, now.millisecondsSinceEpoch);
      _launchWasBackgrounded = false;
      _continuationInFlight = false;

      _log.i(
        'RPCS3 launch request session=$sessionId title=$titleId '
        'source=${sourcePath ?? '<unknown>'}',
      );
      final opened = await ExternalFolderAccess.openJitRequest(
        targetBaseBundleId: targetBundleId,
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      if (opened == true) return true;

      await _clearPendingLaunch(reason: 'FIRST_PASS_FAILED');
      return false;
    } catch (error, stack) {
      await _clearPendingLaunch(reason: 'FIRST_PASS_EXCEPTION');
      _log.e(
        'Rpcs3LaunchService: could not start title $titleId',
        error: error,
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
    if (DateTime.now().difference(startedAt) > _pendingLifetime) {
      await _clearPendingLaunch(reason: 'PENDING_EXPIRED');
      return;
    }

    _continuationInFlight = true;
    _launchWasBackgrounded = false;
    try {
      final displayTitle = prefs.getString(_pendingDisplayTitleKey);
      final sourcePath = prefs.getString(_pendingSourcePathKey);
      final sourceKind = prefs.getString(_pendingSourceKindKey);
      final sessionId = prefs.getString(_pendingSessionKey);
      final template = await rootBundle.loadString(_assetPath);
      final script = buildScriptForTesting(
        template,
        titleId,
        displayTitle: displayTitle,
        sourcePath: sourcePath,
        sourceKind: sourceKind,
        sessionId: sessionId,
      );
      final scriptData = base64Url
          .encode(utf8.encode(script))
          .replaceAll('=', '');

      _log.i(
        'RPCS3 direct attach session=${sessionId ?? '<none>'} title=$titleId '
        'source=${sourcePath ?? '<unknown>'}',
      );
      final opened = await ExternalFolderAccess.openJitRequest(
        targetBaseBundleId: targetBundleId,
        scriptName: 'neostation-rpcs3-stateful.js',
        scriptDataBase64Url: scriptData,
        debugFileName: 'rpcs3_launch_second_pass_debug.txt',
      );
      _log.i(
        opened == true
            ? 'RPCS3 direct StikDebug request opened for $titleId.'
            : 'RPCS3 direct StikDebug request failed for $titleId.',
      );
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: direct pass failed for $titleId',
        error: error,
        stackTrace: stack,
      );
    } finally {
      await _clearPendingLaunch(reason: 'SECOND_PASS_REQUESTED');
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
      await prefs.remove(_pendingDisplayTitleKey);
      await prefs.remove(_pendingSourcePathKey);
      await prefs.remove(_pendingSourceKindKey);
      await prefs.remove(_pendingSessionKey);
      await prefs.remove(_pendingStartedKey);
      _log.i('RPCS3 pending launch cleared: $reason');
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
write('lib/services/rpcs3_launch_service.dart', rpcs3_launch_service)

rpcs3_script = r'''// NeoStation RPCS3 state-aware direct title launcher.
// Derived from StikDebug Universal JIT Script (GPL-3.0):
// https://github.com/StikDebug/StikDebug/blob/main/StikDebug/Scripts/universal.js
//
// The user has already pressed RPCS3's native Start button. This script
// attaches to the active process, fingerprints the loaded core, records the
// exact ASLR-adjusted addresses, queries state/progress, calls the exported C
// boot function, reads its integer return value and last error, then detaches.

const neoTitleId = __NEOSTATION_TITLE_ID_JSON__;
const neoDisplayTitle = __NEOSTATION_DISPLAY_TITLE_JSON__;
const neoSourcePath = __NEOSTATION_SOURCE_PATH_JSON__;
const neoSourceKind = __NEOSTATION_SOURCE_KIND_JSON__;
const neoSessionId = __NEOSTATION_SESSION_ID_JSON__;
const neoSupportedCores = __NEOSTATION_SUPPORTED_CORES_JSON__;
const neoReturnTrapInstruction = 'c0013ed4';

let pid = get_pid();
let attachResponse = send_command(`vAttach;${pid.toString(16)}`);
log(`NEOSTATION_RPC_REQUEST: session=${neoSessionId} titleId=${neoTitleId} title=${neoDisplayTitle}`);
log(`NEOSTATION_RPC_SOURCE: kind=${neoSourceKind} path=${neoSourcePath}`);
log(`NEOSTATION_RPC_PROCESS: pid=${pid} attach=${attachResponse}`);

try {
    const tid = resolveStoppedThread(attachResponse);
    if (!tid) throw new Error('Could not determine a stopped RPCS3 thread');
    log(`NEOSTATION_RPC_THREAD: ${tid}`);

    const fingerprint = findFingerprintCore();
    if (!fingerprint) throw new Error('libRPCS3Core.dylib is not loaded');
    const { core, functions, uuid } = fingerprint;
    const base = parseRemoteAddress(core.load_address);
    const addresses = {
        boot: base + BigInt(functions.boot),
        state: base + BigInt(functions.state),
        progress: base + BigInt(functions.progress),
        lastError: base + BigInt(functions.lastError),
    };
    log(`NEOSTATION_RPC_CORE_UUID: ${uuid}`);
    log(`NEOSTATION_RPC_MODULE_BASE: 0x${base.toString(16)}`);
    log(`NEOSTATION_RPC_ADDRESSES: boot=0x${addresses.boot.toString(16)} state=0x${addresses.state.toString(16)} progress=0x${addresses.progress.toString(16)} lastError=0x${addresses.lastError.toString(16)}`);

    const scratch = allocateScratch();
    try {
        const layout = prepareScratch(scratch);
        const stateBefore = remoteCall(addresses.state, tid, layout.trap, []);
        log(`NEOSTATION_RPC_STATE_BEFORE: ${stateBefore}`);
        logBootProgress(addresses.progress, tid, layout, 'BEFORE');

        const titleHex = asciiToHex(neoTitleId + '\0');
        writeMemory(layout.title, titleHex, 'Title ID');
        log(`NEOSTATION_RPC_TITLE_POINTER: 0x${layout.title.toString(16)} value=${neoTitleId}`);

        const bootResult = remoteCall(
            addresses.boot,
            tid,
            layout.trap,
            [layout.title]);
        log(`NEOSTATION_RPC_BOOT_RESULT: ${bootResult}`);

        const errorPointer = remoteCall(addresses.lastError, tid, layout.trap, []);
        const lastError = errorPointer === 0n
            ? ''
            : readCString(errorPointer, 768);
        log(`NEOSTATION_RPC_LAST_ERROR: ${lastError || '<none>'}`);

        const stateAfter = remoteCall(addresses.state, tid, layout.trap, []);
        log(`NEOSTATION_RPC_STATE_AFTER: ${stateAfter}`);
        logBootProgress(addresses.progress, tid, layout, 'AFTER');

        if (bootResult === 0n) {
            log(`NEOSTATION_RPC_BOOT_ACCEPTED: ${neoTitleId}`);
        } else {
            throw new Error(`RPCS3 rejected ${neoTitleId} with code ${bootResult}: ${lastError || 'no error text'}`);
        }
    } finally {
        send_command(`_m${scratch.toString(16)}`);
    }
} catch (error) {
    log(`NEOSTATION_RPC_ERROR: ${error && error.stack ? error.stack : error}`);
} finally {
    const detachResponse = send_command('D');
    log(`NEOSTATION_RPC_DETACH: ${detachResponse}`);
}

function resolveStoppedThread(initialPacket) {
    let packet = initialPacket || '';
    let match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups.tid;
    packet = send_command('?') || '';
    log(`NEOSTATION_RPC_STOP_PACKET: ${packet}`);
    match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups.tid;
    const current = send_command('qC') || '';
    log(`NEOSTATION_RPC_CURRENT_THREAD: ${current}`);
    match = /^QC(?<tid>[0-9a-f]+)$/i.exec(current);
    return match ? match.groups.tid : null;
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
    const uuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const functions = neoSupportedCores[uuid];
    if (!functions) throw new Error(`Unsupported RPCS3 core UUID: ${uuid}`);
    return { core, functions, uuid };
}

function allocateScratch() {
    let response = send_command('_M4000,rwx');
    if (!response || response.startsWith('E')) response = send_command('_M4000,rw');
    if (!response || response.startsWith('E')) {
        throw new Error(`Could not allocate scratch memory: ${response}`);
    }
    const scratch = BigInt(`0x${response}`);
    const prepared = prepare_memory_region(scratch, 0x4000n);
    log(`NEOSTATION_RPC_SCRATCH: 0x${scratch.toString(16)} prepare=${prepared}`);
    return scratch;
}

function prepareScratch(scratch) {
    const layout = {
        title: scratch,
        completed: scratch + 0x100n,
        total: scratch + 0x108n,
        stage: scratch + 0x200n,
        trap: scratch + 0x800n,
    };
    writeMemory(layout.completed, '0000000000000000', 'completed counter');
    writeMemory(layout.total, '0000000000000000', 'total counter');
    writeMemory(layout.stage, '00'.repeat(512), 'progress stage');
    writeMemory(layout.trap, neoReturnTrapInstruction, 'return trap');
    return layout;
}

function logBootProgress(progressAddress, tid, layout, suffix) {
    writeMemory(layout.completed, '0000000000000000', 'completed counter');
    writeMemory(layout.total, '0000000000000000', 'total counter');
    writeMemory(layout.stage, '00'.repeat(512), 'progress stage');
    const result = remoteCall(
        progressAddress,
        tid,
        layout.trap,
        [layout.completed, layout.total, layout.stage, 512n]);
    const completed = littleEndianHexStringToNumber(readMemory(layout.completed, 8));
    const total = littleEndianHexStringToNumber(readMemory(layout.total, 8));
    const stage = readCString(layout.stage, 512);
    log(`NEOSTATION_RPC_PROGRESS_${suffix}: result=${result} completed=${completed} total=${total} stage=${stage || '<none>'}`);
}

function remoteCall(address, tid, trap, args) {
    const saveId = send_command(`QSaveRegisterState;thread:${tid};`);
    if (!saveId || !/^[0-9]+$/.test(saveId)) {
        throw new Error(`Could not save registers: ${saveId}`);
    }
    try {
        for (let index = 0; index < 4; index++) {
            const value = index < args.length ? BigInt(args[index]) : 0n;
            const response = send_command(
                `P${index.toString(16)}=${numberToLittleEndianHexString(value)};thread:${tid};`);
            if (response !== 'OK') throw new Error(`Could not write x${index}: ${response}`);
        }
        const lrWrite = send_command(
            `P1e=${numberToLittleEndianHexString(trap)};thread:${tid};`);
        const pcWrite = send_command(
            `P20=${numberToLittleEndianHexString(address)};thread:${tid};`);
        if (lrWrite !== 'OK' || pcWrite !== 'OK') {
            throw new Error(`Could not set call registers: lr=${lrWrite} pc=${pcWrite}`);
        }
        const stopPacket = send_command(`vCont;c:${tid}`) || '';
        log(`NEOSTATION_RPC_CALL_STOP: address=0x${address.toString(16)} packet=${stopPacket}`);
        return readRegisterX0(stopPacket, tid);
    } finally {
        const restore = send_command(
            `QRestoreRegisterState:${saveId};thread:${tid};`);
        if (restore !== 'OK') throw new Error(`Could not restore registers: ${restore}`);
    }
}

function readRegisterX0(stopPacket, tid) {
    const match = /(?:^|;)00:(?<value>[0-9a-f]{16});/i.exec(stopPacket);
    if (match) return littleEndianHexStringToNumber(match.groups.value);
    const raw = send_command(`p0;thread:${tid};`) || '';
    if (!/^[0-9a-f]{16}$/i.test(raw)) {
        throw new Error(`Could not read x0 return value: ${raw}`);
    }
    return littleEndianHexStringToNumber(raw);
}

function writeMemory(address, hex, label) {
    const response = send_command(
        `M${address.toString(16)},${(hex.length / 2).toString(16)}:${hex}`);
    if (response !== 'OK') throw new Error(`Could not write ${label}: ${response}`);
}

function readMemory(address, length) {
    const response = send_command(`m${address.toString(16)},${length.toString(16)}`) || '';
    if (!/^[0-9a-f]+$/i.test(response) || response.length < length * 2) {
        throw new Error(`Could not read memory at 0x${address.toString(16)}: ${response}`);
    }
    return response.substring(0, length * 2);
}

function readCString(address, maxLength) {
    if (address === 0n) return '';
    const response = send_command(`m${address.toString(16)},${maxLength.toString(16)}`) || '';
    if (!/^[0-9a-f]+$/i.test(response)) return `<unreadable:${response}>`;
    return hexToAscii(response);
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

function littleEndianHexStringToNumber(hex) {
    const bytes = hex.match(/../g) || [];
    let value = 0n;
    for (let index = Math.min(bytes.length, 8) - 1; index >= 0; index--) {
        value = (value << 8n) | BigInt(`0x${bytes[index]}`);
    }
    return value;
}

function numberToLittleEndianHexString(number) {
    const bytes = [];
    let value = BigInt(number);
    for (let index = 0; index < 8; index++) {
        bytes.push(Number(value & 0xffn));
        value >>= 8n;
    }
    return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function hexToAscii(hex) {
    let text = '';
    for (let index = 0; index + 1 < hex.length; index += 2) {
        const byte = parseInt(hex.substring(index, index + 2), 16);
        if (byte === 0) break;
        text += String.fromCharCode(byte);
    }
    return text;
}
'''
write('assets/data/rpcs3_stikdebug_launch.js', rpcs3_script)

my_games_path = 'lib/screens/game_screen/my_games_list.dart'
my_games = read(my_games_path)
if "import 'package:neostation/services/audio_policy_service.dart';" not in my_games:
    my_games = my_games.replace(
        "import 'package:neostation/services/sfx_service.dart';\n",
        "import 'package:neostation/services/sfx_service.dart';\n"
        "import 'package:neostation/services/audio_policy_service.dart';\n",
        1,
    )
fields_marker = r'''  // Media controllers.
  VideoPlayerController? _videoController;
'''
fields_replacement = r'''  // Media controllers. Every selection gets a generation token; transitions
  // are serialized so an old AVPlayer can never overlap a replacement.
  VideoPlayerController? _videoController;
  int _videoGeneration = 0;
  Future<void> _videoTransition = Future<void>.value();
'''
if fields_marker not in my_games:
    raise SystemExit('Video controller field marker missing')
my_games = my_games.replace(fields_marker, fields_replacement, 1)
write(my_games_path, my_games)

secondary_path = 'lib/screens/game_screen/my_games_list/secondary_display.dart'
secondary = read(secondary_path)
start = secondary.index('  /// Hard reset of the video preview system.')
end = secondary.index('  /// Orchestrates background tasks triggered by game selection changes.', start)
new_reset_block = r'''  /// Queues video work behind any in-flight initialize/dispose operation.
  Future<void> _queueVideoTransition(Future<void> Function() operation) {
    final next = _videoTransition
        .catchError((_) {})
        .then((_) => operation());
    _videoTransition = next.catchError((error, stack) {
      _SystemGamesListState._log.w('Video transition failed: $error');
    });
    return next;
  }

  Future<void> _retireVideoController(
    VideoPlayerController? controller, {
    required String reason,
  }) async {
    if (controller == null) return;
    try {
      if (controller.value.isInitialized) {
        await controller.setVolume(0.0);
        await controller.pause();
      }
    } catch (error) {
      _SystemGamesListState._log.w(
        'Could not mute/pause old video ($reason): $error',
      );
    }
    try {
      await controller.dispose();
    } catch (error) {
      _SystemGamesListState._log.w(
        'Could not dispose old video ($reason): $error',
      );
    }
  }

  void _invalidateVideoSelection({required String reason}) {
    _videoGeneration++;
    _videoTimer?.cancel();
    _videoTimer = null;
    final controller = _videoController;
    _videoController = null;

    if (mounted) {
      rebuild(() {
        _showVideo = false;
        _isVideoLoading = false;
      });
    }
    unawaited(
      _queueVideoTransition(
        () => _retireVideoController(controller, reason: reason),
      ),
    );
  }

  /// Hard reset of the video preview system.
  void _resetVideoState() {
    _invalidateVideoSelection(reason: 'reset');
  }

  /// Graceful termination of video resources with state synchronization.
  void _stopVideoAndCleanup() {
    _invalidateVideoSelection(reason: 'cleanup');
    _updateMusicDucking();
  }

'''
secondary = secondary[:start] + new_reset_block + secondary[end:]
start = secondary.index('  /// Initiates the media preview sequence for the primary and secondary displays.')
end = secondary.index('  /// Resolves the absolute filesystem path for', start)
new_video_block = r'''  /// Initiates the media preview sequence for the primary and secondary displays.
  ///
  /// The existing dwell timer remains an input debounce only. Media readiness
  /// is determined from controller events, never from this duration.
  void _startVideoTimer() {
    _invalidateVideoSelection(reason: 'selection-changed');
    if (!mounted || _isGameLaunching || _selectedGame == null) return;

    final generation = _videoGeneration;
    final game = _selectedGame!;
    _videoTimer = Timer(_SystemGamesListState._videoDelay, () async {
      _videoTimer = null;
      if (!mounted ||
          generation != _videoGeneration ||
          _selectedGame != game ||
          _isGameLaunching) {
        return;
      }

      await _updateSecondaryDisplayVideo(game);
      if (!mounted || generation != _videoGeneration) return;
      final showGameInfo = context
          .read<SqliteConfigProvider>()
          .config
          .showGameInfo;
      if (showGameInfo) {
        await _initializeVideo(game, generation: generation);
      }
    });
  }

  Future<void> _initializeVideo(
    GameModel game, {
    required int generation,
  }) async {
    if (!mounted ||
        generation != _videoGeneration ||
        _selectedGame != game ||
        _isGameLaunching) {
      return;
    }

    final showGameInfo = context
        .read<SqliteConfigProvider>()
        .config
        .showGameInfo;
    if (!showGameInfo) return;
    rebuild(() => _isVideoLoading = true);

    final videoPath = _getVideoPath(game);
    final file = File(videoPath);
    final fileExists = _fileProvider.isInitialized
        ? await _fileProvider.fileExists(videoPath)
        : file.existsSync();
    if (!mounted || generation != _videoGeneration || _selectedGame != game) {
      return;
    }
    if (!fileExists) {
      rebuild(() {
        _showVideo = false;
        _isVideoLoading = false;
      });
      return;
    }

    await _queueVideoTransition(() async {
      if (!mounted || generation != _videoGeneration || _selectedGame != game) {
        return;
      }

      final previous = _videoController;
      _videoController = null;
      await _retireVideoController(previous, reason: 'replacement');
      if (!mounted || generation != _videoGeneration || _selectedGame != game) {
        return;
      }

      final controller = VideoPlayerController.file(
        file,
        videoPlayerOptions: VideoPlayerOptions(mixWithOthers: true),
      );
      try {
        await controller.initialize();
        if (!mounted || generation != _videoGeneration || _selectedGame != game) {
          await _retireVideoController(controller, reason: 'stale-initialize');
          return;
        }

        await controller.setVolume(0.0);
        await controller.setLooping(true);
        await AudioPolicyService().ensureSilentCompatibleSession(
          reason: 'video-preview-initialized',
        );
        await controller.play();
        await AudioPolicyService().ensureSilentCompatibleSession(
          reason: 'video-preview-started',
        );

        await _waitForPreparedVideoFrame(controller, generation: generation);
        if (!mounted || generation != _videoGeneration || _selectedGame != game) {
          await _retireVideoController(controller, reason: 'stale-ready');
          return;
        }

        rebuild(() {
          _videoController = controller;
          _showVideo = true;
          _isVideoLoading = false;
        });

        final videoSoundEnabled = context
            .read<SqliteConfigProvider>()
            .config
            .videoSound;
        if (videoSoundEnabled) {
          await _fadeVideoVolume(
            controller,
            target: 1.0,
            generation: generation,
          );
        }
        _updateMusicDucking();
      } catch (error, stack) {
        _SystemGamesListState._log.e(
          'Error initializing serialized video preview: $error',
          error: error,
          stackTrace: stack,
        );
        await _retireVideoController(controller, reason: 'initialize-error');
        if (mounted && generation == _videoGeneration) {
          rebuild(() {
            _showVideo = false;
            _isVideoLoading = false;
          });
        }
      }
    });
  }

  Future<void> _waitForPreparedVideoFrame(
    VideoPlayerController controller, {
    required int generation,
  }) async {
    if (controller.value.position > Duration.zero &&
        !controller.value.isBuffering) {
      return;
    }

    final completer = Completer<void>();
    late VoidCallback listener;
    listener = () {
      if (generation != _videoGeneration) {
        if (!completer.isCompleted) completer.complete();
        return;
      }
      final value = controller.value;
      if (value.hasError) {
        if (!completer.isCompleted) {
          completer.completeError(
            StateError(value.errorDescription ?? 'Video player error'),
          );
        }
      } else if (value.isInitialized &&
          value.isPlaying &&
          !value.isBuffering &&
          value.position > Duration.zero) {
        if (!completer.isCompleted) completer.complete();
      }
    };
    controller.addListener(listener);
    try {
      await completer.future.timeout(const Duration(seconds: 5));
    } finally {
      controller.removeListener(listener);
    }
  }

  Future<void> _fadeVideoVolume(
    VideoPlayerController controller, {
    required double target,
    required int generation,
  }) async {
    const steps = 4;
    for (var step = 1; step <= steps; step++) {
      if (!mounted ||
          generation != _videoGeneration ||
          _videoController != controller) {
        return;
      }
      await controller.setVolume(target * step / steps);
      if (step < steps) {
        await Future<void>.delayed(const Duration(milliseconds: 25));
      }
    }
  }

  Future<void> _syncVideoVolumeWithConfig() async {
    final controller = _videoController;
    if (!mounted || controller == null || !controller.value.isInitialized) {
      return;
    }
    final enabled = context.read<SqliteConfigProvider>().config.videoSound;
    await controller.setVolume(enabled ? 1.0 : 0.0);
    await AudioPolicyService().ensureSilentCompatibleSession(
      reason: 'video-preview-config-change',
    );
  }

'''
secondary = secondary[:start] + new_video_block + secondary[end:]
write(secondary_path, secondary)

my_games = read(my_games_path)
old_duck = """    // Refresh audio ducking logic (e.g., when toggling video sound).
    _updateMusicDucking();
"""
new_duck = """    // Refresh audio ducking and the active AVPlayer volume when the
    // video-sound preference changes.
    _updateMusicDucking();
    unawaited(_syncVideoVolumeWithConfig());
"""
if old_duck not in my_games:
    raise SystemExit('Config video-volume marker missing')
my_games = my_games.replace(old_duck, new_duck, 1)
write(my_games_path, my_games)

audio_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('all SoLoud clients use the centralized audio policy', () {
    final policy = File('lib/services/audio_policy_service.dart')
        .readAsStringSync();
    expect(policy, contains('ensureSilentCompatibleSession'));
    expect(policy, contains('volume: 0.0'));
    expect(policy, contains('after-play'));

    for (final path in <String>[
      'lib/services/sfx_service.dart',
      'lib/services/home_music_service.dart',
      'lib/services/music_player_service.dart',
    ]) {
      final source = File(path).readAsStringSync();
      expect(source, contains('AudioPolicyService'));
    }
  });

  test('native policy observes lifecycle and audio resets', () {
    final swift = File(
      'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift',
    ).readAsStringSync();
    expect(swift, contains('AVAudioSession.routeChangeNotification'));
    expect(swift, contains('AVAudioSession.mediaServicesWereResetNotification'));
    expect(swift, contains('UIApplication.didBecomeActiveNotification'));
    expect(swift, contains('setCategory(.ambient'));
  });
}
'''
write('test/audio_policy_service_test.dart', audio_test)

rpcs3_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';

void main() {
  group('RPCS3 Stage 7', () {
    test('PARAM.SFO title beats synthetic legacy metadata', () {
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
    });

    test('RPCS3 0.2 state-aware descriptor is complete', () {
      final descriptor = Rpcs3LaunchService
          .supportedCoreFunctions['5C4D64FFB79930AD879C13009838F136'];
      expect(descriptor?['boot'], 0x36224);
      expect(descriptor?['state'], 0x36a8c);
      expect(descriptor?['progress'], 0x36afc);
      expect(descriptor?['lastError'], 0x37f34);
    });

    test('generated script carries request metadata and no placeholders', () {
      final template = File('assets/data/rpcs3_stikdebug_launch.js')
          .readAsStringSync();
      final script = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'BLES00412',
        displayTitle: 'The Lord of the Rings: Conquest™',
        sourcePath: '/Data/games/DiscImages/BLES00412',
        sourceKind: 'disc-image',
        sessionId: 'test-session',
      );
      expect(script, contains('BLES00412'));
      expect(script, contains('DiscImages/BLES00412'));
      expect(script, contains('NEOSTATION_RPC_BOOT_RESULT'));
      expect(script, contains('NEOSTATION_RPC_LAST_ERROR'));
      expect(script, contains('NEOSTATION_RPC_STATE_BEFORE'));
      expect(script, isNot(contains('__NEOSTATION_')));
    });

    test('launcher no longer schedules background app-open timers', () {
      final dart = File('lib/services/rpcs3_launch_service.dart')
          .readAsStringSync();
      expect(dart, contains('openJitRequest'));
      expect(dart, isNot(contains('warmupDelay')));
      expect(dart, isNot(contains('_minimumReturnDelay')));
    });
  });
}
'''
write('test/rpcs3_stage7_test.dart', rpcs3_test)

video_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('video preview transitions are serialized and generation guarded', () {
    final host = File('lib/screens/game_screen/my_games_list.dart')
        .readAsStringSync();
    final video = File(
      'lib/screens/game_screen/my_games_list/secondary_display.dart',
    ).readAsStringSync();

    expect(host, contains('_videoGeneration'));
    expect(host, contains('_videoTransition'));
    expect(video, contains('_queueVideoTransition'));
    expect(video, contains('await controller.dispose()'));
    expect(video, contains('await controller.setVolume(0.0)'));
    expect(video, contains('_waitForPreparedVideoFrame'));
    expect(video, contains('value.position > Duration.zero'));
    expect(video, contains('_fadeVideoVolume'));
    expect(video, contains('AudioPolicyService'));
  });
}
'''
write('test/video_preview_lifecycle_test.dart', video_test)

stage3_path = 'test/rpcs3_stage3_test.dart'
stage3 = read(stage3_path)
old_stage3 = r'''    test('RPCS3 direct script is fingerprinted and title-specific', () {
      final template = File('assets/data/rpcs3_stikdebug_launch.js')
          .readAsStringSync();
      final script = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00412',
      );
      expect(script, contains('"BLES00412"'));
      expect(script, contains('5C4D64FFB79930AD879C13009838F136'));
      expect(script, contains('221732'));
      expect(script, contains('CFE15492152B331E83959A3CF9AC8A9F'));
      expect(script, contains('NEOSTATION_RPC_DIRECT_CORE_NOT_READY'));
      expect(script, contains('NEOSTATION_RPC_DIRECT_BOOT_COMPLETED'));
      expect(script, isNot(contains('__NEOSTATION_')));
    });
'''
new_stage3 = r'''    test('RPCS3 direct script is fingerprinted and state-aware', () {
      final template = File('assets/data/rpcs3_stikdebug_launch.js')
          .readAsStringSync();
      final script = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00412',
      );
      expect(script, contains('"BLES00412"'));
      expect(script, contains('5C4D64FFB79930AD879C13009838F136'));
      expect(script, contains('221732'));
      expect(script, contains('CFE15492152B331E83959A3CF9AC8A9F'));
      expect(script, contains('NEOSTATION_RPC_BOOT_RESULT'));
      expect(script, contains('NEOSTATION_RPC_STATE_BEFORE'));
      expect(script, contains('NEOSTATION_RPC_LAST_ERROR'));
      expect(script, isNot(contains('__NEOSTATION_')));
    });
'''
if old_stage3 not in stage3:
    raise SystemExit('Stage 3 RPCS3 script test marker missing')
stage3 = stage3.replace(old_stage3, new_stage3, 1)
write(stage3_path, stage3)

stage6 = r'''import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:neostation/services/rpcs3_title_catalog_service.dart';

void main() {
  group('RPCS3 Stage 6 reliability', () {
    test(
      'cached raw serial receives GameDB title even without live folder',
      () async {
        final enriched = await Rpcs3LibraryService.applyTitleCatalogForTesting(
          const <Rpcs3LibraryGame>[
            Rpcs3LibraryGame(
              titleId: 'BLES00412',
              title: 'BLES00412',
              version: '',
              category: '',
              sourcePath: '/unavailable/RPCS3/Data/game.iso',
              sourceKind: 'legacy-cache',
            ),
          ],
          const <String, String>{
            'BLES00412': 'The Lord of the Rings: Conquest',
          },
        );
        expect(enriched.single.title, 'The Lord of the Rings: Conquest');
      },
    );

    test('GameDB normalization accepts dashed PS3 serials', () {
      expect(
        Rpcs3TitleCatalogService.normalizeTitleId('BLES-00412'),
        'BLES00412',
      );
    });

    test('RPCS3 0.2 descriptor includes state, progress and error exports', () {
      final descriptor = Rpcs3LaunchService
          .supportedCoreFunctions['5C4D64FFB79930AD879C13009838F136'];
      expect(descriptor?['boot'], 0x36224);
      expect(descriptor?['state'], 0x36a8c);
      expect(descriptor?['progress'], 0x36afc);
      expect(descriptor?['lastError'], 0x37f34);
    });

    test('direct-launch template receives all request diagnostics', () {
      const template =
          'title=__NEOSTATION_TITLE_ID_JSON__ '
          'display=__NEOSTATION_DISPLAY_TITLE_JSON__ '
          'path=__NEOSTATION_SOURCE_PATH_JSON__ '
          'kind=__NEOSTATION_SOURCE_KIND_JSON__ '
          'session=__NEOSTATION_SESSION_ID_JSON__ '
          'cores=__NEOSTATION_SUPPORTED_CORES_JSON__';
      final rendered = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00412',
        displayTitle: 'The Lord of the Rings: Conquest',
        sourcePath: '/Data/games/DiscImages/BLES00412',
        sourceKind: 'disc-image',
        sessionId: 'session-1',
      );
      expect(rendered, contains('BLES00412'));
      expect(rendered, contains('DiscImages/BLES00412'));
      expect(rendered, contains('5C4D64FFB79930AD879C13009838F136'));
      expect(rendered, isNot(contains('__NEOSTATION_')));
    });
  });
}
'''
write('test/rpcs3_stage6_test.dart', stage6)

print('NeoStation Stage 7 patch applied.')
