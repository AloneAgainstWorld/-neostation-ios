import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_soloud/flutter_soloud.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'logger_service.dart';
import 'music_player_service.dart';
import 'sfx_service.dart';

/// Plays the fork's bundled ambience only while the primary Systems menu is
/// actually visible.
///
/// This deliberately shares NeoStation's existing SoLoud engine instead of
/// opening a second iOS audio stack. It also yields to the user's Music player,
/// stops when the app is backgrounded, and reloads its source after a shared
/// engine restart.
class HomeMusicService extends ChangeNotifier with WidgetsBindingObserver {
  HomeMusicService._internal();

  static final HomeMusicService _instance = HomeMusicService._internal();
  factory HomeMusicService() => _instance;

  static const String _preferenceKey = 'neostation_home_music_enabled';
  static const String _assetPath =
      'assets/sounds/neostation_home_ambience_loop.mp3';
  static const double _volume = 0.28;

  final LoggerService _log = LoggerService.instance;

  bool _initialized = false;
  bool _enabled = true;
  bool _mainMenuActive = false;
  bool _appActive = true;
  bool _starting = false;

  AudioSource? _source;
  SoundHandle? _handle;

  bool get enabled => _enabled;

  Future<void> init() async {
    if (_initialized) return;

    try {
      final prefs = await SharedPreferences.getInstance();
      _enabled = prefs.getBool(_preferenceKey) ?? true;
    } catch (e) {
      _log.w('[HomeMusic] Could not load preference: $e');
    }

    _initialized = true;
    WidgetsBinding.instance.addObserver(this);
    MusicPlayerService().addListener(_onUserMusicChanged);
    notifyListeners();

    await _syncPlayback();
  }

  Future<void> setEnabled(bool value) async {
    if (!_initialized) await init();
    if (_enabled == value) return;

    _enabled = value;
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_preferenceKey, value);
    } catch (e) {
      _log.w('[HomeMusic] Could not save preference: $e');
    }

    await _syncPlayback();
  }

  Future<void> setMainMenuActive(bool value) async {
    if (!_initialized) await init();
    if (_mainMenuActive == value) return;

    _mainMenuActive = value;
    await _syncPlayback();
  }

  void _onUserMusicChanged() {
    unawaited(_syncPlayback());
  }

  bool get _shouldPlay =>
      _enabled &&
      _mainMenuActive &&
      _appActive &&
      !MusicPlayerService().isPlaying;

  Future<void> _syncPlayback() async {
    if (_shouldPlay) {
      await _startPlayback();
    } else {
      await _stopPlayback();
    }
  }

  Future<void> _startPlayback() async {
    if (_starting || _handle != null || !_shouldPlay) return;
    _starting = true;

    try {
      // SFX owns the shared engine's normal initialization path and is already
      // concurrency-safe, so using it here avoids two callers racing SoLoud.
      await SfxService().init();
      if (!_shouldPlay) return;

      final source = await SoLoud.instance.loadAsset(_assetPath);
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
      _log.i('[HomeMusic] Main-menu ambience started.');
    } catch (e) {
      // Missing/unsupported assets must never block the UI. This also makes a
      // source-package checkout usable before the optional audio file is added.
      _source = null;
      _handle = null;
      _log.w('[HomeMusic] Could not start ambience: $e');
    } finally {
      _starting = false;
    }
  }

  Future<void> _stopPlayback() async {
    final handle = _handle;
    final source = _source;
    _handle = null;
    _source = null;

    if (!SoLoud.instance.isInitialized) return;

    if (handle != null) {
      try {
        await SoLoud.instance.stop(handle);
      } catch (_) {}
    }

    if (source != null) {
      try {
        await SoLoud.instance.disposeSource(source);
      } catch (_) {}
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _appActive = true;
      // Another lifecycle observer can still be restoring the shared engine;
      // using the normal sync path lets SFX serialize that initialization.
      unawaited(_syncPlayback());
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      _appActive = false;
      unawaited(_stopPlayback());
    }
  }
}
