import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_soloud/flutter_soloud.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'logger_service.dart';
import 'music_player_service.dart';
import 'sfx_service.dart';

/// Plays user-selected ambience only while the primary Systems menu is visible.
///
/// The user chooses the audio file from General settings. NeoStation copies it
/// into its own application-support directory so the selection survives file
/// provider/security-scoped access changes. Playback shares NeoStation's
/// existing SoLoud engine, yields to the Music player, and stops outside the
/// main menu or while the app is backgrounded.
class HomeMusicService extends ChangeNotifier with WidgetsBindingObserver {
  HomeMusicService._internal();

  static final HomeMusicService _instance = HomeMusicService._internal();
  factory HomeMusicService() => _instance;

  static const String _preferenceKey = 'neostation_home_music_enabled';
  static const String _pathPreferenceKey = 'neostation_home_music_path';
  static const String _namePreferenceKey = 'neostation_home_music_name';
  static const double _volume = 0.28;
  static const List<String> _allowedExtensions = [
    'mp3',
    'wav',
    'ogg',
    'flac',
  ];

  final LoggerService _log = LoggerService.instance;

  bool _initialized = false;
  bool _enabled = false;
  bool _mainMenuActive = false;
  bool _appActive = true;
  bool _starting = false;

  String? _musicPath;
  String? _musicName;
  AudioSource? _source;
  SoundHandle? _handle;

  bool get enabled => _enabled;
  bool get hasMusic =>
      _musicPath != null && _musicPath!.isNotEmpty && File(_musicPath!).existsSync();
  String? get selectedFileName => _musicName;

  Future<void> init() async {
    if (_initialized) return;

    try {
      final prefs = await SharedPreferences.getInstance();
      _musicPath = prefs.getString(_pathPreferenceKey);
      _musicName = prefs.getString(_namePreferenceKey);
      _enabled = prefs.getBool(_preferenceKey) ?? false;

      if (!hasMusic) {
        _musicPath = null;
        _musicName = null;
        _enabled = false;
        await prefs.remove(_pathPreferenceKey);
        await prefs.remove(_namePreferenceKey);
        await prefs.setBool(_preferenceKey, false);
      }
    } catch (e) {
      _enabled = false;
      _musicPath = null;
      _musicName = null;
      _log.w('[HomeMusic] Could not load preference: $e');
    }

    _initialized = true;
    WidgetsBinding.instance.addObserver(this);
    MusicPlayerService().addListener(_onUserMusicChanged);
    notifyListeners();

    await _syncPlayback();
  }

  /// Enables/disables the main-menu music preference.
  ///
  /// Turning it on opens the system file picker. If the user chooses a file it
  /// replaces the previous selection. If the picker is cancelled and a prior
  /// selection exists, that prior file is simply re-enabled.
  Future<void> setEnabled(bool value) async {
    if (!_initialized) await init();

    if (value) {
      final imported = await _pickAndStoreMusic();
      if (!imported && !hasMusic) {
        _enabled = false;
        notifyListeners();
        return;
      }
      _enabled = true;
    } else {
      _enabled = false;
    }

    await _persistPreference();
    notifyListeners();
    await _syncPlayback();
  }

  Future<void> setMainMenuActive(bool value) async {
    if (!_initialized) await init();
    if (_mainMenuActive == value) return;

    _mainMenuActive = value;
    await _syncPlayback();
  }

  /// Removes the stored custom music file and disables menu music.
  Future<void> clearMusic() async {
    if (!_initialized) await init();
    await _stopPlayback();

    final oldPath = _musicPath;
    _musicPath = null;
    _musicName = null;
    _enabled = false;

    if (oldPath != null) {
      try {
        final file = File(oldPath);
        if (await file.exists()) await file.delete();
      } catch (e) {
        _log.w('[HomeMusic] Could not delete old music file: $e');
      }
    }

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_pathPreferenceKey);
      await prefs.remove(_namePreferenceKey);
      await prefs.setBool(_preferenceKey, false);
    } catch (e) {
      _log.w('[HomeMusic] Could not clear preference: $e');
    }

    notifyListeners();
  }

  Future<bool> _pickAndStoreMusic() async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: _allowedExtensions,
        allowMultiple: false,
      );
      final picked = result?.files.single;
      final sourcePath = picked?.path;
      if (picked == null || sourcePath == null || sourcePath.isEmpty) {
        return false;
      }

      final source = File(sourcePath);
      if (!await source.exists()) return false;

      final supportDir = await getApplicationSupportDirectory();
      final musicDir = Directory(p.join(supportDir.path, 'home_music'));
      await musicDir.create(recursive: true);

      await _stopPlayback();

      // Keep one app-owned file only, so replacing the selection cannot leave
      // stale copies behind.
      await for (final entity in musicDir.list()) {
        if (entity is File) {
          try {
            await entity.delete();
          } catch (_) {}
        }
      }

      final extension = p.extension(picked.name).toLowerCase();
      final safeExtension = _allowedExtensions.contains(
        extension.replaceFirst('.', ''),
      )
          ? extension
          : '.mp3';
      final destination = File(
        p.join(musicDir.path, 'main_menu_music$safeExtension'),
      );
      await source.copy(destination.path);

      _musicPath = destination.path;
      _musicName = picked.name;

      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_pathPreferenceKey, destination.path);
      await prefs.setString(_namePreferenceKey, picked.name);

      _log.i('[HomeMusic] Selected main-menu music: ${picked.name}');
      return true;
    } catch (e) {
      _log.w('[HomeMusic] Could not import selected music: $e');
      return false;
    }
  }

  Future<void> _persistPreference() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_preferenceKey, _enabled);
      if (_musicPath != null) {
        await prefs.setString(_pathPreferenceKey, _musicPath!);
      }
      if (_musicName != null) {
        await prefs.setString(_namePreferenceKey, _musicName!);
      }
    } catch (e) {
      _log.w('[HomeMusic] Could not save preference: $e');
    }
  }

  void _onUserMusicChanged() {
    unawaited(_syncPlayback());
  }

  bool get _shouldPlay =>
      _enabled &&
      hasMusic &&
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
    if (_starting || _handle != null || !_shouldPlay || _musicPath == null) {
      return;
    }
    _starting = true;

    try {
      // SFX owns the shared engine's normal initialization path and is already
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
    } catch (e) {
      _source = null;
      _handle = null;
      _log.w('[HomeMusic] Could not start selected music: $e');
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
      unawaited(_syncPlayback());
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      _appActive = false;
      unawaited(_stopPlayback());
    }
  }
}
