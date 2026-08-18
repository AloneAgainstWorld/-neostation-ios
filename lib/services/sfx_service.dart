import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter_soloud/flutter_soloud.dart';
import 'package:neostation/services/audio_policy_service.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path_provider/path_provider.dart';

/// Independent service for managing user interface sound effects (SFX).
///
/// Operates in isolation from [MusicPlayerService] but shares the same
/// underlying [SoLoud] singleton engine. Handles pre-loading assets, volume
/// control, and debounce logic to prevent audio stacking during rapid
/// navigation.
///
/// Sound catalogue:
/// - Navigation: `nav1.wav`, `nav2.wav`, `nav3.wav` (randomized, no-repeat).
/// - Confirm/Enter: `enter.wav`.
/// - Back/Cancel: `back.wav`.
class SfxService {
  static final SfxService _instance = SfxService._internal();
  factory SfxService() => _instance;
  SfxService._internal();

  /// List of navigation sound asset paths.
  static const List<String> _navSounds = [
    'assets/sounds/nav1.wav',
    'assets/sounds/nav2.wav',
    'assets/sounds/nav3.wav',
  ];

  /// Path to the enter/confirm sound asset.
  static const String _enterSound = 'assets/sounds/enter.wav';

  /// Path to the back/cancel sound asset.
  static const String _backSound = 'assets/sounds/back.wav';

  /// Threshold to collapse rapid duplicate calls into a single playback event.
  static const int _debounceMs = 60;

  final _log = LoggerService.instance;
  final _random = Random();

  /// Cache of pre-loaded [AudioSource] objects for low-latency playback.
  final Map<String, AudioSource> _sources = {};

  /// Handles of currently active short UI sounds. Keeping them lets a policy
  /// change or engine teardown silence voices that already started.
  final List<SoundHandle> _activeHandles = <SoundHandle>[];

  /// Serializes every UI voice start. Rapid input can otherwise create two
  /// SoLoud voices while the iOS audio session is being reasserted, leaving a
  /// tiny audible window under the wrong session category.
  Future<void> _sfxStartSerial = Future<void>.value();

  bool _isInitialized = false;
  bool _isInitializing = false;

  /// Tracks the last played navigation sound index to prevent immediate repetition.
  int _lastNavIndex = -1;

  /// Timestamp of the last successful playback event for debouncing.
  DateTime? _lastPlayTime;

  /// Global toggle for SFX audio.
  bool _enabled = true;

  /// Global SFX playback volume (0.0 to 0.75).
  double _volume = 0.75;

  double get volume => _volume;
  bool get isInitialized => _isInitialized;
  bool get isEnabled => _enabled;

  Completer<void>? _initCompleter;

  /// Initializes the SoLoud engine and pre-loads all UI sound assets into memory.
  ///
  /// Subsequent calls will wait for the ongoing initialization or return
  /// immediately if already initialized.
  Future<void> init() async {
    if (_isInitialized) return;

    if (_isInitializing) {
      return _initCompleter?.future;
    }

    _isInitializing = true;
    _initCompleter = Completer<void>();

    try {
      _log.i('[SfxService] Initializing...');

      if (!SoLoud.instance.isInitialized) {
        // Pre-create the temp dir SoLoud uses for extracted asset files.
        // Prevents SoLoudTemporaryFolderFailedException on Android when the
        // directory isn't fully ready before the first loadAsset() call.
        try {
          final tempDir = await getTemporaryDirectory();
          await Directory(
            '${tempDir.path}/SoLoudLoader-Temp-Files',
          ).create(recursive: true);
        } catch (_) {}
        await SoLoud.instance.init();
      }

      // SoLoud's iOS backend can activate an audio-session category that
      // ignores the hardware Silent switch. Re-apply NeoStation's intended
      // non-primary/ambient category after engine initialization so UI
      // navigation sounds follow the iPhone Ring/Silent setting.
      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'sfx-engine-initialized',
      );

      final allPaths = [..._navSounds, _enterSound, _backSound];
      for (final path in allPaths) {
        try {
          AudioSource? source;
          int retries = 0;
          while (source == null && retries < 2) {
            try {
              source = await SoLoud.instance.loadAsset(path);
            } catch (e) {
              retries++;
              if (retries < 2) {
                _log.w('[SfxService] Retrying load for $path ($retries/2)...');
                await Future.delayed(const Duration(milliseconds: 200));
              } else {
                rethrow;
              }
            }
          }

          if (source != null) {
            _sources[path] = source;
            _log.d('[SfxService] Loaded: $path');
          }
        } catch (e) {
          _log.w('[SfxService] Could not load $path: $e');
        }
      }

      // Asset loading can make the backend reactivate a non-ambient category.
      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'sfx-assets-loaded',
      );
      _isInitialized = true;
      _log.i(
        '[SfxService] Ready. ${_sources.length}/${allPaths.length} sounds loaded.',
      );
      _initCompleter?.complete();
    } catch (e) {
      _log.e('[SfxService] Init error: $e');
      _initCompleter?.completeError(e);
    } finally {
      _isInitializing = false;
    }
  }

  /// Resets SFX state after the shared [SoLoud] engine has been torn down
  /// elsewhere (e.g. [MusicPlayerService] releasing it while the app is
  /// backgrounded for battery reasons).
  ///
  /// The engine tear-down already disposed every source, so we just drop our
  /// stale handles and mark uninitialized; assets reload on the next
  /// [init]/playback call.
  void handleEngineTornDown() {
    _activeHandles.clear();
    _sources.clear();
    _isInitialized = false;
    _isInitializing = false;
    _initCompleter = null;
    _log.i('[SfxService] Engine released; SFX will reload on resume.');
  }

  /// Reopens the engine (if needed) and reloads SFX assets after a tear-down.
  Future<void> reinitializeAfterEngineRestart() async {
    if (_isInitialized) return;
    await init();
  }

  /// Unloads all cached audio sources.
  ///
  /// Note: This does NOT shut down the shared [SoLoud] engine.
  Future<void> dispose() async {
    await stopAllSounds();
    for (final source in _sources.values) {
      try {
        await SoLoud.instance.disposeSource(source);
      } catch (_) {}
    }
    _sources.clear();
    _isInitialized = false;
    _log.i('[SfxService] Disposed.');
  }

  /// Plays a random navigation sound from the catalogue.
  ///
  /// Ensures that the same sound is not played twice in a row.
  Future<void> playNavSound() async {
    if (!_enabled) return;
    if (!_debounce()) return;
    await _ensureInitialized();
    if (!_isInitialized || _sources.isEmpty) return;

    final index = _pickRandomNavIndex();
    final path = _navSounds[index];
    await _play(path);
    _log.d('[SfxService] nav[$index]: $path');
  }

  /// Plays the confirm/enter sound effect.
  Future<void> playEnterSound() async {
    if (!_enabled) return;
    if (!_debounce()) return;
    await _ensureInitialized();
    if (!_isInitialized) return;
    await _play(_enterSound);
    _log.d('[SfxService] enter');
  }

  /// Plays the back/cancel sound effect.
  Future<void> playBackSound() async {
    if (!_enabled) return;
    if (!_debounce()) return;
    await _ensureInitialized();
    if (!_isInitialized) return;
    await _play(_backSound);
    _log.d('[SfxService] back');
  }

  /// Updates the global SFX volume.
  ///
  /// [value] is clamped between 0.0 and 0.75.
  void setVolume(double value) {
    _volume = value.clamp(0.0, 0.75);
    _log.d('[SfxService] Volume set to $_volume');
  }

  /// Globally enables or disables SFX playback.
  void setEnabled(bool value) {
    _enabled = value;
    if (!value) unawaited(stopAllSounds());
    _log.d('[SfxService] SFX ${value ? 'enabled' : 'disabled'}');
  }

  /// Stops every UI voice that is still valid without changing the user's
  /// configured SFX volume or enabled preference.
  Future<void> stopAllSounds() async {
    if (_activeHandles.isEmpty || !SoLoud.instance.isInitialized) {
      _activeHandles.clear();
      return;
    }
    final handles = List<SoundHandle>.from(_activeHandles);
    _activeHandles.clear();
    for (final handle in handles) {
      try {
        if (SoLoud.instance.getIsValidVoiceHandle(handle)) {
          await SoLoud.instance.stop(handle);
        }
      } catch (_) {}
    }
  }

  /// Validates if a playback request should proceed based on the debounce threshold.
  bool _debounce() {
    final now = DateTime.now();
    if (_lastPlayTime != null &&
        now.difference(_lastPlayTime!).inMilliseconds < _debounceMs) {
      return false;
    }
    _lastPlayTime = now;
    return true;
  }

  /// Ensures the service and SoLoud engine are initialized before playback.
  Future<void> _ensureInitialized() async {
    if (!_isInitialized) await init();
  }

  /// Initiates playback for a pre-loaded source identified by its [path].
  ///
  /// The complete voice-start transaction is serialized. More importantly, a
  /// voice is created paused and at zero volume. Starting/unpausing SoLoud can
  /// reactivate its iOS audio backend, so NeoStation reapplies the `.ambient`
  /// session *after* each of those operations while the voice is still muted.
  /// Only then is the configured SFX volume restored. This closes the brief
  /// audible race that rapid menu presses could expose with the Ring/Silent
  /// switch enabled.
  Future<void> _play(String path) {
    _sfxStartSerial = _sfxStartSerial
        .catchError((Object _) {})
        .then((_) => _playSerially(path));
    return _sfxStartSerial;
  }

  Future<void> _playSerially(String path) async {
    final source = _sources[path];
    if (source == null) {
      _log.w('[SfxService] Source not found for: $path');
      return;
    }
    if (!_enabled || !_isInitialized || !SoLoud.instance.isInitialized) {
      return;
    }

    SoundHandle? handle;
    try {
      // Navigation sounds are intentionally non-overlapping. Besides sounding
      // cleaner during rapid input, this guarantees that no previous SFX voice
      // is audible while a new SoLoud voice may reactivate the audio backend.
      await stopAllSounds();
      if (!_enabled || !SoLoud.instance.isInitialized) return;

      await AudioPolicyService().prepareForPlayback('sfx');
      if (!_enabled || !SoLoud.instance.isInitialized) return;

      // Never create an audible voice. `play` itself can wake the native audio
      // device, so the first policy reassertion happens while it is paused.
      handle = SoLoud.instance.play(source, volume: 0.0, paused: true);
      _activeHandles.add(handle);
      await AudioPolicyService().afterPlaybackStarted('sfx-paused');

      if (!_enabled ||
          !SoLoud.instance.isInitialized ||
          !SoLoud.instance.getIsValidVoiceHandle(handle)) {
        await _stopHandleIfValid(handle);
        return;
      }

      // Unpause at zero volume first. Waking the device must also complete
      // before `.ambient` is asserted for the final time.
      SoLoud.instance.setPause(handle, false);
      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'sfx-unpaused-zero-volume',
      );

      if (!_enabled ||
          !SoLoud.instance.isInitialized ||
          !SoLoud.instance.getIsValidVoiceHandle(handle)) {
        await _stopHandleIfValid(handle);
        return;
      }

      // This is the first point at which the voice can become audible. The
      // native session is already `.ambient`, so iOS remains authoritative for
      // the physical Ring/Silent switch.
      SoLoud.instance.setVolume(handle, _volume);
      _activeHandles.removeWhere(
        (candidate) => !SoLoud.instance.getIsValidVoiceHandle(candidate),
      );
    } catch (e) {
      if (handle != null) await _stopHandleIfValid(handle);
      _log.w('[SfxService] Playback error for $path: $e');
    }
  }

  Future<void> _stopHandleIfValid(SoundHandle handle) async {
    _activeHandles.remove(handle);
    if (!SoLoud.instance.isInitialized) return;
    try {
      if (SoLoud.instance.getIsValidVoiceHandle(handle)) {
        await SoLoud.instance.stop(handle);
      }
    } catch (_) {}
  }

  /// Selects a random navigation sound index that differs from the last played index.
  int _pickRandomNavIndex() {
    if (_navSounds.length == 1) return 0;

    int index;
    do {
      index = _random.nextInt(_navSounds.length);
    } while (index == _lastNavIndex);

    _lastNavIndex = index;
    return index;
  }
}
