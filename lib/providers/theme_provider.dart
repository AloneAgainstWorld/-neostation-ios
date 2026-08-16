import 'dart:io';

import 'package:neostation/services/logger_service.dart';
import 'package:flutter/material.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/services/custom_theme_service.dart';
import 'package:neostation/services/startup_theme_cache.dart';
import 'package:neostation/repositories/config_repository.dart';
import 'package:neostation/services/config_service.dart';
import 'package:neostation/utils/image_utils.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

/// Provider responsible for managing the application's visual theme.
///
/// The color theme and the optional main-menu custom background are persisted
/// independently. The background is rendered only by the Systems main menu;
/// playlists and other top-level screens keep their normal theme background.
class ThemeProvider extends ChangeNotifier with WidgetsBindingObserver {
  static final _log = LoggerService.instance;
  static const String _customBackgroundPreferenceKey =
      'neostation_custom_background_path';

  ThemeData _currentTheme =
      (WidgetsBinding.instance.platformDispatcher.platformBrightness ==
          Brightness.dark)
      ? AppThemes.darkTheme
      : AppThemes.lightTheme;

  String _currentThemeName = 'system';
  String? _customBackgroundPath;

  ThemeData get currentTheme {
    if (_currentThemeName == 'system') {
      final brightness =
          WidgetsBinding.instance.platformDispatcher.platformBrightness;
      return brightness == Brightness.dark
          ? availableThemes['dark']!
          : availableThemes['light']!;
    }
    return _currentTheme;
  }

  String get currentThemeName => _currentThemeName;

  String? get customBackgroundPath {
    final value = _customBackgroundPath;
    if (value == null || value.isEmpty) return null;
    return File(value).existsSync() ? value : null;
  }

  bool get hasCustomBackground => customBackgroundPath != null;

  bool get isOled => _currentThemeName == 'oled';

  static final Map<String, ThemeData> availableThemes = {
    'dark': AppThemes.darkTheme,
    'light': AppThemes.lightTheme,
    'oled': AppThemes.oledTheme,
    'valentine': AppThemes.valentineTheme,
    'dracula': AppThemes.draculaTheme,
    'nord': AppThemes.nordTheme,
    'coffee': AppThemes.coffeeTheme,
    'tokyo_night': AppThemes.tokyoNightTheme,
    'retro': AppThemes.retroTheme,
    'abyss': AppThemes.abyssTheme,
    'cyberpunk': AppThemes.cyberpunkTheme,
    'aqua': AppThemes.aquaTheme,
    'palenight': AppThemes.palenightTheme,
    'horizon': AppThemes.horizonTheme,
  };

  static const Map<String, String> themeDisplayNames = {
    'system': 'System',
    'dark': 'Dark',
    'light': 'Light',
    'oled': 'OLED',
    'valentine': 'Valentine',
    'dracula': 'Dracula',
    'nord': 'Nord',
    'coffee': 'Coffee',
    'tokyo_night': 'Tokyo Night',
    'retro': 'Retro',
    'abyss': 'Abyss',
    'cyberpunk': 'Cyberpunk',
    'aqua': 'Aqua',
    'palenight': 'Palenight',
    'horizon': 'Horizon',
  };

  ThemeProvider._() {
    WidgetsBinding.instance.addObserver(this);
  }

  static Future<ThemeProvider> create() async {
    final provider = ThemeProvider._();
    await provider._loadSavedTheme();
    return provider;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangePlatformBrightness() {
    if (_currentThemeName == 'system') {
      _log.i('Platform brightness changed, updating system theme...');
      _updateSystemTheme();
      _notifyThemeChanged();
    }
  }

  void _notifyThemeChanged() {
    StartupThemeCache.save(currentTheme);
    notifyListeners();
  }

  void _updateSystemTheme() {
    final brightness =
        WidgetsBinding.instance.platformDispatcher.platformBrightness;
    _currentTheme = brightness == Brightness.dark
        ? availableThemes['dark']!
        : availableThemes['light']!;
  }

  Future<void> _loadCustomThemes() async {
    try {
      final themes = await CustomThemeService.loadAll();
      AppThemes.customThemes
        ..clear()
        ..addEntries(themes.map((t) => MapEntry(t.id, t)));
    } catch (e) {
      _log.e('Error loading custom themes: $e');
    }
  }

  Future<void> _loadCustomBackground() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedPath = prefs.getString(_customBackgroundPreferenceKey);
      if (savedPath == null || savedPath.isEmpty) return;

      final file = File(savedPath);
      if (await file.exists() && ImageUtils.isSupportedBackground(savedPath)) {
        _customBackgroundPath = savedPath;
      } else {
        await prefs.remove(_customBackgroundPreferenceKey);
      }
    } catch (e) {
      _log.e('Error loading custom background: $e');
    }
  }

  Future<void> _loadSavedTheme() async {
    try {
      await _loadCustomThemes();
      await _loadCustomBackground();

      final savedThemeName = await ConfigRepository.getThemeName();
      if (savedThemeName == 'system') {
        _currentThemeName = 'system';
        _updateSystemTheme();
        _notifyThemeChanged();
      } else if (availableThemes.containsKey(savedThemeName)) {
        _currentTheme = availableThemes[savedThemeName]!;
        _currentThemeName = savedThemeName;
        _notifyThemeChanged();
      } else if (AppThemes.customThemes.containsKey(savedThemeName)) {
        _currentTheme = AppThemes.customThemes[savedThemeName]!.themeData;
        _currentThemeName = savedThemeName;
        _notifyThemeChanged();
      } else {
        _log.w(
          'Saved theme "$savedThemeName" is no longer available, falling back to system.',
        );
        _currentThemeName = 'system';
        _updateSystemTheme();
        await ConfigRepository.updateThemeName('system');
        _notifyThemeChanged();
      }
    } catch (e) {
      _log.e('Error loading saved theme: $e');
    }
  }

  Future<void> setTheme(String themeName) async {
    if (themeName == 'system') {
      _currentThemeName = 'system';
      _updateSystemTheme();
      try {
        await ConfigRepository.updateThemeName('system');
      } catch (e) {
        _log.e('Error saving theme: $e');
      }
      _notifyThemeChanged();
      return;
    }

    ThemeData? resolved = availableThemes[themeName];
    resolved ??= AppThemes.customThemes[themeName]?.themeData;

    if (resolved != null) {
      _currentTheme = resolved;
      _currentThemeName = themeName;
      try {
        await ConfigRepository.updateThemeName(themeName);
      } catch (e) {
        _log.e('Error saving theme: $e');
      }
      _notifyThemeChanged();
    }
  }

  /// Copies a selected image/GIF/video into NeoStation's user-data directory.
  /// It is intentionally not part of ThemeData: only the main Systems menu
  /// renders it, so game playlists and the rest of the app remain unchanged.
  Future<String> setCustomBackground(File sourceFile) async {
    if (!await sourceFile.exists()) {
      throw FileSystemException(
        'Custom background file was not found',
        sourceFile.path,
      );
    }
    if (!ImageUtils.isSupportedBackground(sourceFile.path)) {
      throw const FormatException('Unsupported custom background format');
    }

    final userDataPath = await ConfigService.getUserDataPath();
    final targetDir = Directory(path.join(userDataPath, 'custom_background'));
    await targetDir.create(recursive: true);

    final extension = path.extension(sourceFile.path).toLowerCase();
    final targetPath = path.join(targetDir.path, 'background$extension');
    final normalizedSource = path.normalize(sourceFile.absolute.path);
    final normalizedTarget = path.normalize(File(targetPath).absolute.path);

    await for (final entity in targetDir.list(followLinks: false)) {
      if (entity is File &&
          path.normalize(entity.absolute.path) != normalizedSource) {
        try {
          await entity.delete();
        } catch (_) {}
      }
    }

    if (normalizedSource != normalizedTarget) {
      await sourceFile.copy(targetPath);
    }

    _customBackgroundPath = targetPath;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_customBackgroundPreferenceKey, targetPath);
    notifyListeners();
    return targetPath;
  }

  Future<void> clearCustomBackground() async {
    final oldPath = _customBackgroundPath;
    _customBackgroundPath = null;

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_customBackgroundPreferenceKey);

    if (oldPath != null && oldPath.isNotEmpty) {
      try {
        final file = File(oldPath);
        if (await file.exists()) await file.delete();
      } catch (_) {}
    }

    notifyListeners();
  }

  List<Map<String, String>> getThemeList() {
    final list = availableThemes.keys.map((key) {
      return {'name': key, 'displayName': themeDisplayNames[key] ?? key};
    }).toList();

    for (final custom in AppThemes.customThemes.values) {
      list.add({'name': custom.id, 'displayName': custom.name});
    }

    return list;
  }

  bool isCustomTheme(String themeName) =>
      AppThemes.customThemes.containsKey(themeName);

  Future<ThemeImportResult> importTheme(File file) async {
    final reserved = {...availableThemes.keys, 'system'};
    final result = await CustomThemeService.importFromFile(
      file.path,
      reservedIds: reserved,
      existing: AppThemes.customThemes.values.toList(),
    );
    AppThemes.customThemes[result.theme.id] = result.theme;
    notifyListeners();
    await setTheme(result.theme.id);
    return result;
  }

  Future<void> deleteTheme(String themeName) async {
    if (!AppThemes.customThemes.containsKey(themeName)) return;

    await CustomThemeService.delete(themeName);
    AppThemes.customThemes.remove(themeName);

    if (_currentThemeName == themeName) {
      await setTheme('system');
    } else {
      notifyListeners();
    }
  }
}
