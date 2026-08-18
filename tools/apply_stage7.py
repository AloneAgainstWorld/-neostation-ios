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


def regex_replace_once(path: str, pattern: str, replacement: str, *, flags: int = 0) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'Regex marker not found in {path}: {pattern[:160]!r}')
    write(path, updated)


def insert_import(path: str, import_line: str) -> None:
    text = read(path)
    if import_line in text:
        return
    imports = list(re.finditer(r'^import .*?;\s*$', text, flags=re.MULTILINE))
    if not imports:
        raise SystemExit(f'No imports found in {path}')
    pos = imports[-1].end()
    write(path, text[:pos] + '\n' + import_line + text[pos:])


# ---------------------------------------------------------------------------
# Build number
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
# 1. One audio-session policy for every NeoStation audio client.
# ---------------------------------------------------------------------------
audio_policy = r'''import 'dart:async';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/widgets.dart';

import 'logger_service.dart';

/// Central owner of NeoStation's native audio-session policy.
///
/// iOS deliberately does not expose a public API that reports the hardware
/// Ring/Silent switch. The supported way to honour it is to keep the entire app
/// on an `AVAudioSession.Category.ambient` session. Every audio backend in
/// NeoStation calls this service after it creates, reloads or starts a player,
/// preventing SoLoud or AVPlayer from silently replacing the shared session
/// with a category that ignores the switch.
class AudioPolicyService with WidgetsBindingObserver {
  AudioPolicyService._internal();

  static final AudioPolicyService _instance = AudioPolicyService._internal();
  factory AudioPolicyService() => _instance;

  final LoggerService _log = LoggerService.instance;

  bool _initialized = false;
  Future<void> _serial = Future<void>.value();
  int _applicationCount = 0;

  bool get isInitialized => _initialized;
  int get applicationCountForTesting => _applicationCount;

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    WidgetsBinding.instance.addObserver(this);
    await ensureSilentCompatibleSession(reason: 'application-start');
  }

  /// Reasserts the single native session policy in a serialized queue.
  ///
  /// Serializing these calls matters because SoLoud asset loads and AVPlayer
  /// initialization can complete concurrently during rapid menu navigation.
  Future<void> ensureSilentCompatibleSession({required String reason}) {
    if (!Platform.isIOS) return Future<void>.value();

    final completer = Completer<void>();
    _serial = _serial.catchError((Object _) {}).then((_) async {
      try {
        final applied =
            await ExternalFolderAccess.configureAudioSessionForSilentMode();
        if (applied != true) {
          _log.w('[AudioPolicy] Native ambient session was not applied: $reason');
        } else {
          _applicationCount++;
        }
        completer.complete();
      } catch (error, stack) {
        _log.e(
          '[AudioPolicy] Failed to apply ambient session: $reason',
          error: error,
          stackTrace: stack,
        );
        completer.complete();
      }
    });
    return completer.future;
  }

  Future<void> prepareForPlayback(String client) =>
      ensureSilentCompatibleSession(reason: '$client:prepare');

  Future<void> afterPlaybackStarted(String client) =>
      ensureSilentCompatibleSession(reason: '$client:started');

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(ensureSilentCompatibleSession(reason: 'application-resumed'));
    }
  }
}
'''
write('lib/services/audio_policy_service.dart', audio_policy)

# Initialize policy before any eager audio client.
insert_import('lib/main.dart', "import 'services/audio_policy_service.dart';")
replace_once(
    'lib/main.dart',
    """  final log = LoggerService.instance;
  log.i('NeoStation starting...');

  if (Platform.isIOS) {
""",
    """  final log = LoggerService.instance;
  log.i('NeoStation starting...');

  await AudioPolicyService().initialize();

  if (Platform.isIOS) {
""",
)

# SFX: use the central policy and retain handles so active UI sounds can be
# stopped when the user disables SFX or the shared engine is torn down.
sfx_path = 'lib/services/sfx_service.dart'
sfx = read(sfx_path)
sfx = sfx.replace(
    "import 'package:external_folder_access/external_folder_access.dart';\n",
    "import 'package:neostation/services/audio_policy_service.dart';\n",
)
sfx = sfx.replace(
    """  /// Cache of pre-loaded [AudioSource] objects for low-latency playback.
  final Map<String, AudioSource> _sources = {};
""",
    """  /// Cache of pre-loaded [AudioSource] objects for low-latency playback.
  final Map<String, AudioSource> _sources = {};

  /// Handles of currently active short UI sounds. Keeping them lets a policy
  /// change or engine teardown silence voices that already started.
  final List<SoundHandle> _activeHandles = <SoundHandle>[];
""",
)
sfx = sfx.replace(
    'await _restoreSilentModeAudioSession();',
    "await AudioPolicyService().ensureSilentCompatibleSession(\n        reason: 'sfx-engine-initialized',\n      );",
    1,
)
sfx = sfx.replace(
    'await _restoreSilentModeAudioSession();',
    "await AudioPolicyService().ensureSilentCompatibleSession(\n        reason: 'sfx-assets-loaded',\n      );",
    1,
)
sfx = sfx.replace(
    """  void handleEngineTornDown() {
    _sources.clear();
""",
    """  void handleEngineTornDown() {
    _activeHandles.clear();
    _sources.clear();
""",
)
sfx = sfx.replace(
    """  Future<void> dispose() async {
    for (final source in _sources.values) {
""",
    """  Future<void> dispose() async {
    await stopAllSounds();
    for (final source in _sources.values) {
""",
)
sfx = sfx.replace(
    """  void setEnabled(bool value) {
    _enabled = value;
    _log.d('[SfxService] SFX ${value ? 'enabled' : 'disabled'}');
  }
""",
    """  void setEnabled(bool value) {
    _enabled = value;
    if (!value) unawaited(stopAllSounds());
    _log.d('[SfxService] SFX ${value ? 'enabled' : 'disabled'}');
  }

  /// Stops every UI voice that is still valid without changing the user's
  /// configured SFX volume or enabled preference.
  Future<void> stopAllSounds() async {
    if (!SoLoud.instance.isInitialized || _activeHandles.isEmpty) {
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
""",
)
old_play = """    try {
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
"""
new_play = """    try {
      await AudioPolicyService().prepareForPlayback('sfx');
      final handle = SoLoud.instance.play(source, volume: _volume);
      _activeHandles.add(handle);
      _activeHandles.removeWhere(
        (candidate) => !SoLoud.instance.getIsValidVoiceHandle(candidate),
      );
      await AudioPolicyService().afterPlaybackStarted('sfx');
    } catch (e) {
      _log.w('[SfxService] Playback error for $path: $e');
    }
  }
"""
if old_play not in sfx:
    raise SystemExit('SFX playback block not found')
sfx = sfx.replace(old_play, new_play, 1)
write(sfx_path, sfx)

# Home menu ambience: route all session mutations through AudioPolicyService.
home_path = 'lib/services/home_music_service.dart'
home = read(home_path)
home = home.replace(
    "import 'package:external_folder_access/external_folder_access.dart';\n",
    "import 'package:neostation/services/audio_policy_service.dart';\n",
)
home = re.sub(
    r"\n  Future<void> _restoreSilentModeAudioSession\(\) async \{.*?\n  \}\n\n  Future<void> _restoreSilentModeAndSync\(\) async \{.*?\n  \}\n",
    "\n",
    home,
    count=1,
    flags=re.DOTALL,
)
home = home.replace(
    'await _restoreSilentModeAudioSession();',
    "await AudioPolicyService().ensureSilentCompatibleSession(\n        reason: 'home-music-engine-ready',\n      );",
    1,
)
home = home.replace(
    'await _restoreSilentModeAudioSession();',
    "await AudioPolicyService().prepareForPlayback('home-music');",
    1,
)
home = home.replace(
    'await _restoreSilentModeAudioSession();',
    "await AudioPolicyService().afterPlaybackStarted('home-music');",
    1,
)
home = home.replace(
    "unawaited(_restoreSilentModeAndSync());",
    "unawaited(_resumeWithAudioPolicy());",
)
resume_marker = """  Future<void> _startPlayback() async {
"""
resume_method = """  Future<void> _resumeWithAudioPolicy() async {
    await AudioPolicyService().ensureSilentCompatibleSession(
      reason: 'home-music-resumed',
    );
    await _syncPlayback();
  }

  Future<void> _startPlayback() async {
"""
if resume_marker not in home:
    raise SystemExit('Home music start marker not found')
home = home.replace(resume_marker, resume_method, 1)
write(home_path, home)

# General music player: the same SoLoud singleton must reassert the same policy.
music_path = 'lib/services/music_player_service.dart'
insert_import(music_path, "import 'package:neostation/services/audio_policy_service.dart';")
music = read(music_path)
music = music.replace(
    """      _soloud!.setVisualizationEnabled(true);
""",
    """      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'music-player-engine-initialized',
      );

      _soloud!.setVisualizationEnabled(true);
""",
    1,
)
music = music.replace(
    """      await SfxService().reinitializeAfterEngineRestart();
""",
    """      await SfxService().reinitializeAfterEngineRestart();
      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'music-player-engine-resumed',
      );
""",
    1,
)
music = music.replace(
    """            _logger.d(\"Loading audio source: $effectivePath\");
            _currentSource = await SoLoud.instance.loadFile(effectivePath);
""",
    """            await AudioPolicyService().prepareForPlayback('music-player');
            _logger.d(\"Loading audio source: $effectivePath\");
            _currentSource = await SoLoud.instance.loadFile(effectivePath);
            await AudioPolicyService().ensureSilentCompatibleSession(
              reason: 'music-player-source-loaded',
            );
""",
    1,
)
music = music.replace(
    """            _currentHandle = SoLoud.instance.play(
              _currentSource!,
              volume: _isDucked ? _volume * 0.5 : _volume,
            );

            _isPlaying = true;
""",
    """            _currentHandle = SoLoud.instance.play(
              _currentSource!,
              volume: _isDucked ? _volume * 0.5 : _volume,
            );
            await AudioPolicyService().afterPlaybackStarted('music-player');

            _isPlaying = true;
""",
    1,
)
music = music.replace(
    """  Future<void> resume() async {
    if (!_isInitialized || _currentHandle == null) return;
    SoLoud.instance.setPause(_currentHandle!, false);
""",
    """  Future<void> resume() async {
    if (!_isInitialized || _currentHandle == null) return;
    await AudioPolicyService().prepareForPlayback('music-player-resume');
    SoLoud.instance.setPause(_currentHandle!, false);
    await AudioPolicyService().afterPlaybackStarted('music-player-resume');
""",
    1,
)
write(music_path, music)

# Muted custom background videos still participate in the same shared native
# session, because AVPlayer initialization itself can change AVAudioSession.
shader_path = 'lib/widgets/shaders/shader_gif_widget.dart'
insert_import(shader_path, "import '../../services/audio_policy_service.dart';")
shader = read(shader_path)
shader = shader.replace(
    """      await controller.initialize();
      if (!mounted || _videoController != controller || widget.imagePath != path) {
""",
    """      await controller.initialize();
      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'custom-background-video-initialized',
      );
      if (!mounted || _videoController != controller || widget.imagePath != path) {
""",
    1,
)
shader = shader.replace(
    """      await controller.play();
      if (mounted && _videoController == controller) {
""",
    """      await controller.play();
      await AudioPolicyService().afterPlaybackStarted(
        'custom-background-video',
      );
      if (mounted && _videoController == controller) {
""",
    1,
)
write(shader_path, shader)


# ---------------------------------------------------------------------------
# 2. Repair RPCS3 names on both the database-model and list-service paths.
# ---------------------------------------------------------------------------
model_path = 'lib/models/game_model.dart'
model = read(model_path)
resolver_marker = """  factory GameModel.fromDatabaseModel(DatabaseGameModel db) {
"""
resolver_method = r'''  /// Resolves names from an existing database row, including rows created by
  /// older RPCS3 builds whose ScreenScraper value was only the Title ID.
  static ({
    String displayName,
    String realName,
    bool hasMeaningfulScrapedName,
  }) resolveDatabaseNamesForDisplay(DatabaseGameModel db) {
    final isRpcs3Virtual = db.romPath.toLowerCase().startsWith(
      'rpcs3-library://',
    );
    if (!isRpcs3Virtual) {
      final name = db.titleName ?? db.realName ?? db.filename;
      return (
        displayName: name,
        realName: db.realName ?? db.filename,
        hasMeaningfulScrapedName:
            db.screenscraperRealName?.trim().isNotEmpty ?? false,
      );
    }

    final scraped = db.screenscraperRealName?.trim();
    final realName = db.realName?.trim();
    final localTitle = db.titleName?.trim();
    final meaningfulScraped = isMeaningfulRpcs3MetadataNameForTesting(
      scraped,
      titleId: db.titleId,
      filename: db.filename,
    );
    final meaningfulReal = isMeaningfulRpcs3MetadataNameForTesting(
      realName,
      titleId: db.titleId,
      filename: db.filename,
    );
    final resolved = (meaningfulScraped ? scraped : null) ??
        (meaningfulReal ? realName : null) ??
        ((localTitle?.isNotEmpty ?? false) ? localTitle : null) ??
        db.filename;
    final resolvedReal = (meaningfulReal ? realName : null) ??
        ((localTitle?.isNotEmpty ?? false) ? localTitle : null) ??
        db.filename;
    return (
      displayName: resolved!,
      realName: resolvedReal!,
      hasMeaningfulScrapedName: meaningfulScraped,
    );
  }

  factory GameModel.fromDatabaseModel(DatabaseGameModel db) {
'''
if 'resolveDatabaseNamesForDisplay' not in model:
    if resolver_marker not in model:
        raise SystemExit('GameModel factory marker missing')
    model = model.replace(resolver_marker, resolver_method, 1)

factory_pattern = re.compile(
    r"  factory GameModel\.fromDatabaseModel\(DatabaseGameModel db\) \{.*?\n    return GameModel\(",
    flags=re.DOTALL,
)
match = factory_pattern.search(model)
if not match:
    raise SystemExit('GameModel database factory block missing')
new_factory_prefix = """  factory GameModel.fromDatabaseModel(DatabaseGameModel db) {
    final resolvedNames = resolveDatabaseNamesForDisplay(db);

    return GameModel("""
model = model[:match.start()] + new_factory_prefix + model[match.end():]
model = model.replace('realname: resolvedRealName!,', 'realname: resolvedNames.realName,', 1)
model = model.replace('name: displayName!,', 'name: resolvedNames.displayName,', 1)
write(model_path, model)

# GameListService bypassed GameModel.fromDatabaseModel and therefore preserved
# the old raw BLES identifier. Make its resolver use the same canonical policy.
list_path = 'lib/services/game/game_list_service.dart'
list_text = read(list_path)
list_text = re.sub(
    r"  static bool _hasScreenscraperRealName\(DatabaseGameModel dbGame\) \{.*?\n  \}\n",
    """  static bool _hasScreenscraperRealName(DatabaseGameModel dbGame) {
    return GameModel.resolveDatabaseNamesForDisplay(
      dbGame,
    ).hasMeaningfulScrapedName;
  }
""",
    list_text,
    count=1,
    flags=re.DOTALL,
)
list_text = list_text.replace(
    """  static ({String name, bool showRomFileNameSubtitle}) _resolveListDisplayName({
""",
    """  static ({
    String name,
    String realName,
    bool showRomFileNameSubtitle,
  }) _resolveListDisplayName({
""",
    1,
)
list_text = list_text.replace(
    """    final filename = dbGame.filename;
    final scraped = _hasScreenscraperRealName(dbGame);
    final coalesced = dbGame.realName ?? dbGame.titleName ?? filename;
""",
    """    final filename = dbGame.filename;
    final resolvedNames = GameModel.resolveDatabaseNamesForDisplay(dbGame);
    final scraped = _hasScreenscraperRealName(dbGame);
    final coalesced = resolvedNames.displayName;
""",
    1,
)
# Add realName to every return record in the resolver.
list_text = list_text.replace(
    'showRomFileNameSubtitle: false,\n      );',
    'realName: resolvedNames.realName,\n        showRomFileNameSubtitle: false,\n      );',
    1,
)
list_text = list_text.replace(
    """      return (
        name: _formatListNameFromScrapedTitle(coalesced),
        showRomFileNameSubtitle: true,
      );
""",
    """      return (
        name: _formatListNameFromScrapedTitle(coalesced),
        realName: resolvedNames.realName,
        showRomFileNameSubtitle: true,
      );
""",
    1,
)
list_text = list_text.replace(
    "return (name: coalesced, showRomFileNameSubtitle: false);",
    "return (\n        name: coalesced,\n        realName: resolvedNames.realName,\n        showRomFileNameSubtitle: false,\n      );",
    1,
)
# Final filename fallback return.
old_final_return = """    return (
      name: _formatListNameFromFilename(
        filename,
        validExtensionsSet,
        hideExtension: hideExtension,
        hideParentheses: hideParentheses,
        hideBrackets: hideBrackets,
      ),
      showRomFileNameSubtitle: false,
    );
"""
new_final_return = """    return (
      name: _formatListNameFromFilename(
        filename,
        validExtensionsSet,
        hideExtension: hideExtension,
        hideParentheses: hideParentheses,
        hideBrackets: hideBrackets,
      ),
      realName: resolvedNames.realName,
      showRomFileNameSubtitle: false,
    );
"""
if old_final_return not in list_text:
    raise SystemExit('GameListService final resolver return missing')
list_text = list_text.replace(old_final_return, new_final_return, 1)
list_text = list_text.replace(
    'realname: dbGame.realName ?? dbGame.filename,',
    'realname: resolved.realName,',
)
write(list_path, list_text)

# Include RPCS3 title_name in SQL coalescing once legacy synthetic metadata has
# been cleared. This also makes list ordering use the repaired title.
sqlite_path = 'lib/data/datasources/sqlite_service.dart'
sqlite = read(sqlite_path)
sqlite = sqlite.replace(
    "s.folder_name IN ('android') OR LOWER(ur.rom_path) LIKE 'melonx://%'",
    "s.folder_name IN ('android') OR LOWER(ur.rom_path) LIKE 'melonx://%' OR LOWER(ur.rom_path) LIKE 'rpcs3-library://%'",
)
write(sqlite_path, sqlite)

# During every RPCS3 reconciliation, overwrite synthetic title_name values and
# clear only the bad ScreenScraper real_name field; preserve descriptions,
# ratings, artwork and real metadata.
rpcs3_library_path = 'lib/services/rpcs3_library_service.dart'
rpcs3 = read(rpcs3_library_path)
rpcs3 = rpcs3.replace(
    """                title_name = CASE
                  WHEN title_name IS NULL OR title_name = '' THEN ? ELSE title_name END,
""",
    """                title_name = CASE
                  WHEN title_name IS NULL OR title_name = ''
                    OR UPPER(TRIM(title_name)) = UPPER(TRIM(COALESCE(title_id, '')))
                    OR UPPER(TRIM(title_name)) = UPPER(TRIM(filename))
                  THEN ? ELSE title_name END,
""",
    1,
)
# Add synthetic metadata cleanup after each virtual upsert.
virtual_insert_end = """        if (game.iconPath != null) {
          artwork.add((filename: syntheticFilename, iconPath: game.iconPath!));
        }
        virtualRows++;
"""
virtual_insert_new = """        await txn.rawUpdate(
          '''
          UPDATE user_screenscraper_metadata
          SET real_name = NULL
          WHERE app_system_id = ?
            AND filename IN (?, ?)
            AND real_name IS NOT NULL
            AND (
              UPPER(TRIM(real_name)) = UPPER(TRIM(?))
              OR UPPER(TRIM(real_name)) = UPPER(TRIM(?))
              OR UPPER(TRIM(real_name)) = UPPER(TRIM(?))
            )
          ''',
          <Object?>[
            systemId,
            syntheticFilename,
            '${game.titleId}.rpcs3',
            game.titleId,
            syntheticFilename,
            '${game.titleId}.rpcs3',
          ],
        );

        if (game.iconPath != null) {
          artwork.add((filename: syntheticFilename, iconPath: game.iconPath!));
        }
        virtualRows++;
"""
if virtual_insert_end not in rpcs3:
    raise SystemExit('RPCS3 virtual insert tail missing')
rpcs3 = rpcs3.replace(virtual_insert_end, virtual_insert_new, 1)
# Expose the source descriptor used only for launch diagnostics.
getter_marker = """  static bool isVirtualLibraryPath(String romPath) {
"""
getter = """  static Rpcs3LibraryGame? cachedGameForTitleId(String? titleId) {
    final normalized = titleId?.trim().toLowerCase() ?? '';
    if (normalized.isEmpty) return null;
    return _cache?[normalized];
  }

  static bool isVirtualLibraryPath(String romPath) {
"""
if getter not in rpcs3:
    if getter_marker not in rpcs3:
        raise SystemExit('RPCS3 cache getter marker missing')
    rpcs3 = rpcs3.replace(getter_marker, getter, 1)
write(rpcs3_library_path, rpcs3)


# ---------------------------------------------------------------------------
# 3. Replace delayed RPCS3 app opens with immediate StikDebug requests and a
#    state/result-aware remote-call protocol.
# ---------------------------------------------------------------------------
external_dart_path = 'packages/external_folder_access/lib/external_folder_access.dart'
external_dart = read(external_dart_path)
immediate_method_marker = """  /// Opens [url] immediately, then asks the native iOS layer to open the same
"""
immediate_method = r'''  /// Opens one StikDebug `enable-jit` request immediately while NeoStation is
  /// foregrounded. Unlike the legacy preflight helper, this method schedules no
  /// UIApplication work after NeoStation is backgrounded.
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
if 'static Future<bool?> openJitRequest' not in external_dart:
    if immediate_method_marker not in external_dart:
        raise SystemExit('ExternalFolderAccess insertion marker missing')
    external_dart = external_dart.replace(
        immediate_method_marker,
        immediate_method + immediate_method_marker,
        1,
    )
write(external_dart_path, external_dart)

native_path = 'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift'
native = read(native_path)
native = native.replace(
    """        case \"configureAudioSessionForSilentMode\":
            configureAudioSessionForSilentMode(result: result)
""",
    """        case \"configureAudioSessionForSilentMode\":
            configureAudioSessionForSilentMode(result: result)
        case \"openJitRequest\":
            openJitRequest(call: call, result: result)
""",
    1,
)
native_marker = """    // MARK: - Explicit StikDebug JIT preflight
"""
native_method = r'''    // MARK: - Immediate StikDebug request

    private func openJitRequest(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        guard let args = call.arguments as? [String: Any],
            let targetBaseBundleId = args["targetBaseBundleId"] as? String,
            !targetBaseBundleId.isEmpty
        else {
            result(FlutterError(
                code: "INVALID_ARGS",
                message: "openJitRequest requires targetBaseBundleId",
                details: nil
            ))
            return
        }

        let scriptName = ((args["scriptName"] as? String) ?? "universal.js")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let debugFileName = Self.safeDebugFileName(
            (args["debugFileName"] as? String) ?? "jit_request_debug.txt"
        )
        let suffix = Self.currentSideloadBundleSuffix()
        let targetBundleId = (suffix?.isEmpty == false)
            ? "\(targetBaseBundleId).\(suffix!)"
            : targetBaseBundleId

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
            result(FlutterError(
                code: "INVALID_JIT_URL",
                message: "Could not build StikDebug request URL",
                details: nil
            ))
            return
        }

        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: true,
            message: "STATE: JIT_REQUEST\n"
                + "Application state: \(Self.applicationStateName())\n"
                + "Target base bundle: \(targetBaseBundleId)\n"
                + "Target effective bundle: \(targetBundleId)\n"
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
if 'private func openJitRequest(' not in native:
    if native_marker not in native:
        raise SystemExit('Native JIT marker missing')
    native = native.replace(native_marker, native_method + native_marker, 1)
write(native_path, native)

# New launch service: no warm-up timers; a real resume event starts an immediate
# state-aware second attachment. Keep diagnostics in Documents and preserve the
# request descriptor across app switches.
rpcs3_launch = r'''import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// State-driven RPCS3 iOS launcher for the exact inspected core builds.
///
/// StikDebug itself launches/attaches the target application. NeoStation no
/// longer schedules UIApplication opens from the background. Pass one runs the
/// Universal JIT script. Once RPCS3Core is initialized and NeoStation resumes,
/// pass two immediately attaches with a script that reads the core state,
/// dispatches the selected Title ID, captures the real return code and logs the
/// resulting state/progress/error.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';

  static const Map<String, Map<String, int>> supportedCoreFunctions =
      <String, Map<String, int>>{
        'CFE15492152B331E83959A3CF9AC8A9F': <String, int>{
          'boot': 0x2fa18,
        },
        '5C4D64FFB79930AD879C13009838F136': <String, int>{
          'boot': 0x36224,
          'emulationState': 0x36a8c,
          'bootProgress': 0x36afc,
          'globalState': 0x37a80,
          'lastError': 0x37f34,
        },
      };

  static const String currentCoreUuid = '5C4D64FF-B799-30AD-879C-13009838F136';
  static const int currentBootGameOffset = 0x36224;
  static const String expectedCoreUuid = currentCoreUuid;
  static const int bootGameOffset = currentBootGameOffset;

  static const String _assetPath = 'assets/data/rpcs3_stikdebug_launch.js';
  static const String _pendingRequestKey = 'rpcs3_pending_launch_request_v2';
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
    String displayTitle = '',
    String sourcePath = '',
    String sourceKind = '',
    String sessionId = 'test-session',
  }) {
    final normalized = normalizeTitleId(titleId);
    if (normalized == null) throw const FormatException('Invalid RPCS3 title ID.');
    final request = <String, String>{
      'titleId': normalized,
      'displayTitle': displayTitle,
      'sourcePath': sourcePath,
      'sourceKind': sourceKind,
      'sessionId': sessionId,
    };
    return template
        .replaceAll('__NEOSTATION_REQUEST_JSON__', jsonEncode(request))
        .replaceAll(
          '__NEOSTATION_SUPPORTED_CORES_JSON__',
          jsonEncode(supportedCoreFunctions),
        );
  }

  @visibleForTesting
  static bool shouldContinuePendingForTesting({
    required DateTime now,
    required DateTime startedAt,
    required bool launchWasBackgrounded,
  }) {
    final age = now.difference(startedAt);
    return launchWasBackgrounded && !age.isNegative && age <= _pendingLifetime;
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
    final request = <String, dynamic>{
      'titleId': titleId,
      'displayTitle': displayTitle?.trim() ?? '',
      'sourcePath': sourcePath?.trim() ?? '',
      'sourceKind': sourceKind?.trim() ?? '',
      'sessionId': '${now.millisecondsSinceEpoch}-$titleId',
      'startedMs': now.millisecondsSinceEpoch,
    };

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_pendingRequestKey, jsonEncode(request));
      _launchWasBackgrounded = false;
      _continuationInFlight = false;
      await _writeLaunchState('FIRST_PASS_REQUESTED', request: request);

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
    final request = await _loadPendingRequest();
    if (request == null) return;

    final startedAt = DateTime.fromMillisecondsSinceEpoch(
      request['startedMs'] as int,
    );
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
      final script = buildScriptForTesting(
        template,
        request['titleId'] as String,
        displayTitle: request['displayTitle'] as String,
        sourcePath: request['sourcePath'] as String,
        sourceKind: request['sourceKind'] as String,
        sessionId: request['sessionId'] as String,
      );
      final scriptData = base64Url.encode(utf8.encode(script)).replaceAll('=', '');
      await _writeLaunchState('SECOND_PASS_REQUESTED', request: request);

      final opened = await ExternalFolderAccess.openJitRequest(
        targetBaseBundleId: targetBundleId,
        scriptName: 'neostation-rpcs3-stateful.js',
        scriptDataBase64Url: scriptData,
        debugFileName: 'rpcs3_launch_second_pass_debug.txt',
      );
      await _writeLaunchState(
        opened == true ? 'SECOND_PASS_OPENED' : 'SECOND_PASS_FAILED',
        request: request,
      );
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: stateful second pass failed',
        error: error,
        stackTrace: stack,
      );
      await _writeLaunchState(
        'SECOND_PASS_EXCEPTION',
        request: request,
        extra: error.toString(),
      );
    } finally {
      await _clearPendingLaunch(reason: 'SECOND_PASS_FINISHED');
      _continuationInFlight = false;
    }
  }

  static Future<Map<String, dynamic>?> _loadPendingRequest() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_pendingRequestKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      final request = Map<String, dynamic>.from(decoded);
      final titleId = normalizeTitleId(request['titleId']?.toString());
      final startedMs = int.tryParse(request['startedMs']?.toString() ?? '');
      if (titleId == null || startedMs == null) return null;
      request['titleId'] = titleId;
      request['startedMs'] = startedMs;
      request['displayTitle'] = request['displayTitle']?.toString() ?? '';
      request['sourcePath'] = request['sourcePath']?.toString() ?? '';
      request['sourceKind'] = request['sourceKind']?.toString() ?? '';
      request['sessionId'] = request['sessionId']?.toString() ?? '';
      return request;
    } catch (_) {
      return null;
    }
  }

  static Future<void> _discardExpiredPendingLaunch() async {
    final request = await _loadPendingRequest();
    if (request == null) return;
    final startedAt = DateTime.fromMillisecondsSinceEpoch(
      request['startedMs'] as int,
    );
    if (DateTime.now().difference(startedAt) > _pendingLifetime) {
      await _clearPendingLaunch(reason: 'STARTUP_PENDING_EXPIRED');
    }
  }

  static Future<void> _clearPendingLaunch({required String reason}) async {
    try {
      final request = await _loadPendingRequest();
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_pendingRequestKey);
      await _writeLaunchState(reason, request: request);
    } catch (_) {}
  }

  static Future<void> _writeLaunchState(
    String state, {
    Map<String, dynamic>? request,
    String? extra,
  }) async {
    final line = <String>[
      '${DateTime.now().toIso8601String()} STATE=$state',
      if (request != null) 'session=${request['sessionId']}',
      if (request != null) 'titleId=${request['titleId']}',
      if (request != null) 'title=${request['displayTitle']}',
      if (request != null) 'sourceKind=${request['sourceKind']}',
      if (request != null) 'sourcePath=${request['sourcePath']}',
      if (extra != null) 'extra=$extra',
    ].join(' | ');
    _log.i('RPCS3 launch protocol: $line');
    try {
      final documents = await getApplicationDocumentsDirectory();
      await File(path.join(documents.path, 'rpcs3_launch_protocol_debug.txt'))
          .writeAsString('$line\n', mode: FileMode.append, flush: true);
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
write('lib/services/rpcs3_launch_service.dart', rpcs3_launch)

# Pass real discovery information into the persisted launch request.
game_launch_path = 'lib/services/game/game_launch_service.dart'
game_launch = read(game_launch_path)
game_launch = game_launch.replace(
    """          final launched = await Rpcs3LaunchService.launchTitle(titleId);
""",
    """          final linkedGame = Rpcs3LibraryService.cachedGameForTitleId(
            titleId,
          );
          final launched = await Rpcs3LaunchService.launchTitle(
            titleId,
            displayTitle: game.name,
            sourcePath: linkedGame?.sourcePath,
            sourceKind: linkedGame?.sourceKind,
          );
""",
    1,
)
write(game_launch_path, game_launch)

# Stateful StikDebug script. It uses the module load address (ASLR-safe), checks
# RPCS3's actual initialized state, captures x0 before restoring registers and
# reads last_error/progress for diagnostics.
rpcs3_script = r'''// NeoStation RPCS3 state-aware direct title launcher.
// Derived from StikDebug Universal JIT Script (GPL-3.0):
// https://github.com/StikDebug/StikDebug/blob/main/StikDebug/Scripts/universal.js

const neoRequest = __NEOSTATION_REQUEST_JSON__;
const neoSupportedCores = __NEOSTATION_SUPPORTED_CORES_JSON__;
const neoReturnTrapInstruction = 'c0013ed4'; // brk #0xf00e, little endian

const pid = get_pid();
const attachResponse = send_command(`vAttach;${pid.toString(16)}`);
log(`NEOSTATION_RPC_REQUEST: ${JSON.stringify(neoRequest)}`);
log(`NEOSTATION_RPC_PROCESS: pid=${pid} attach=${attachResponse}`);

let scratch = 0n;
try {
    const tid = resolveStoppedThread(attachResponse);
    if (!tid) throw new Error('Could not determine a stopped RPCS3 thread');
    log(`NEOSTATION_RPC_THREAD: ${tid}`);

    const fingerprint = findFingerprintCore();
    if (!fingerprint) throw new Error('libRPCS3Core.dylib is not loaded');
    const core = fingerprint.core;
    const functions = fingerprint.functions;
    const base = parseRemoteAddress(core.load_address);
    log(`NEOSTATION_RPC_CORE_UUID: ${fingerprint.uuid}`);
    log(`NEOSTATION_RPC_MODULE_BASE: 0x${base.toString(16)}`);

    scratch = allocateScratch();
    const trap = scratch + 0x100n;
    writeMemory(trap, neoReturnTrapInstruction, 'return trap');

    const globalStateBefore = functions.globalState == null
        ? null
        : callUInt64(base + BigInt(functions.globalState), [], tid, trap, 'global-state-before');
    const emulationStateBefore = functions.emulationState == null
        ? null
        : callUInt64(base + BigInt(functions.emulationState), [], tid, trap, 'emulation-state-before');
    log(`NEOSTATION_RPC_STATE_BEFORE: global=${formatValue(globalStateBefore)} emulation=${formatValue(emulationStateBefore)}`);

    const progressBefore = functions.bootProgress == null
        ? null
        : callBootProgress(base + BigInt(functions.bootProgress), tid, trap);
    if (progressBefore != null) {
        log(`NEOSTATION_RPC_PROGRESS_BEFORE: ${JSON.stringify(progressBefore)}`);
    }

    // RPCS3 0.2's exported boot function requires the iOS core state to be 2.
    // This replaces the old timing guesses with the same state the function
    // itself checks internally.
    if (globalStateBefore != null && globalStateBefore !== 2n) {
        throw new Error(`RPCS3Core is not ready (global state ${globalStateBefore})`);
    }

    const titleAddress = scratch + 0x800n;
    const titleHex = asciiToHex(neoRequest.titleId + '\0');
    writeMemory(titleAddress, titleHex, 'title ID');
    log(`NEOSTATION_RPC_TITLE_POINTER: 0x${titleAddress.toString(16)} value=${neoRequest.titleId}`);

    const bootAddress = base + BigInt(functions.boot);
    log(`NEOSTATION_RPC_BOOT_ADDRESS: 0x${bootAddress.toString(16)}`);
    const bootResult = callUInt64(
        bootAddress,
        [titleAddress],
        tid,
        trap,
        'boot-game');
    log(`NEOSTATION_RPC_BOOT_RESULT: ${bootResult} (${bootResultName(bootResult)})`);

    let lastError = '';
    if (functions.lastError != null) {
        const errorPointer = callUInt64(
            base + BigInt(functions.lastError),
            [],
            tid,
            trap,
            'last-error');
        if (errorPointer != 0n) {
            lastError = readCString(errorPointer, 768);
        }
    }
    log(`NEOSTATION_RPC_LAST_ERROR: ${lastError || '<empty>'}`);

    const globalStateAfter = functions.globalState == null
        ? null
        : callUInt64(base + BigInt(functions.globalState), [], tid, trap, 'global-state-after');
    const emulationStateAfter = functions.emulationState == null
        ? null
        : callUInt64(base + BigInt(functions.emulationState), [], tid, trap, 'emulation-state-after');
    log(`NEOSTATION_RPC_STATE_AFTER: global=${formatValue(globalStateAfter)} emulation=${formatValue(emulationStateAfter)}`);

    const progressAfter = functions.bootProgress == null
        ? null
        : callBootProgress(base + BigInt(functions.bootProgress), tid, trap);
    if (progressAfter != null) {
        log(`NEOSTATION_RPC_PROGRESS_AFTER: ${JSON.stringify(progressAfter)}`);
    }

    if (bootResult !== 0n) {
        throw new Error(`rpcs3_ios_boot_game returned ${bootResultName(bootResult)}${lastError ? `: ${lastError}` : ''}`);
    }
    log(`NEOSTATION_RPC_BOOT_CONFIRMED: ${neoRequest.titleId}`);
} catch (error) {
    log(`NEOSTATION_RPC_ERROR: ${error && error.stack ? error.stack : error}`);
} finally {
    if (scratch !== 0n) send_command(`_m${scratch.toString(16)}`);
    const detachResponse = send_command('D');
    log(`NEOSTATION_RPC_DETACH: ${detachResponse}`);
}

function resolveStoppedThread(initialPacket) {
    let packet = initialPacket || '';
    let match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups.tid;
    packet = send_command('?') || '';
    match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups.tid;
    const current = send_command('qC') || '';
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
    if (functions == null) {
        throw new Error(`Unsupported RPCS3 core UUID: ${uuid}`);
    }
    return { core, uuid, functions };
}

function allocateScratch() {
    let response = send_command('_M4000,rwx');
    if (!response || response.startsWith('E')) response = send_command('_M4000,rw');
    if (!response || response.startsWith('E')) {
        throw new Error(`Could not allocate remote scratch memory: ${response}`);
    }
    const address = BigInt(`0x${response}`);
    const prepared = prepare_memory_region(address, 0x4000n);
    log(`NEOSTATION_RPC_SCRATCH: 0x${address.toString(16)} prepare=${prepared}`);
    return address;
}

function callUInt64(address, args, tid, trap, label) {
    const saveId = send_command(`QSaveRegisterState;thread:${tid};`);
    if (!saveId || !/^[0-9]+$/.test(saveId)) {
        throw new Error(`${label}: could not save registers: ${saveId}`);
    }
    try {
        for (let index = 0; index < 4; index++) {
            const value = index < args.length ? BigInt(args[index]) : 0n;
            const write = send_command(
                `P${index.toString(16)}=${numberToLittleEndianHexString(value)};thread:${tid};`);
            if (write !== 'OK') throw new Error(`${label}: x${index} write failed: ${write}`);
        }
        const lrWrite = send_command(`P1e=${numberToLittleEndianHexString(trap)};thread:${tid};`);
        const pcWrite = send_command(`P20=${numberToLittleEndianHexString(address)};thread:${tid};`);
        if (lrWrite !== 'OK' || pcWrite !== 'OK') {
            throw new Error(`${label}: lr=${lrWrite} pc=${pcWrite}`);
        }
        const stop = send_command(`vCont;c:${tid}`) || '';
        let result = extractRegister(stop, '00');
        if (result == null) {
            const raw = send_command(`p0;thread:${tid};`) || send_command('p0') || '';
            result = /^[0-9a-f]{16}$/i.test(raw) ? littleEndianHexStringToNumber(raw) : null;
        }
        if (result == null) throw new Error(`${label}: return register unavailable; stop=${stop}`);
        log(`NEOSTATION_RPC_CALL: ${label} address=0x${address.toString(16)} result=${result}`);
        return result;
    } finally {
        const restore = send_command(`QRestoreRegisterState:${saveId};thread:${tid};`);
        if (restore !== 'OK') log(`NEOSTATION_RPC_RESTORE_ERROR: ${label} ${restore}`);
    }
}

function callBootProgress(address, tid, trap) {
    const current = scratch + 0x200n;
    const total = scratch + 0x208n;
    const text = scratch + 0x300n;
    writeMemory(current, '00000000', 'progress current');
    writeMemory(total, '00000000', 'progress total');
    writeMemory(text, '00', 'progress text');
    const status = callUInt64(address, [current, total, text, 1024n], tid, trap, 'boot-progress');
    return {
        status: Number(status),
        current: readU32(current),
        total: readU32(total),
        text: readCString(text, 1024),
    };
}

function writeMemory(address, hex, label) {
    const response = send_command(`M${address.toString(16)},${(hex.length / 2).toString(16)}:${hex}`);
    if (response !== 'OK') throw new Error(`${label} write failed: ${response}`);
}

function readU32(address) {
    const raw = send_command(`m${address.toString(16)},4`) || '';
    if (!/^[0-9a-f]{8}$/i.test(raw)) return -1;
    return Number(littleEndianHexStringToNumber(raw));
}

function readCString(address, maxBytes) {
    const raw = send_command(`m${address.toString(16)},${maxBytes.toString(16)}`) || '';
    return hexToAscii(raw);
}

function extractRegister(packet, registerTag) {
    const expression = new RegExp(`${registerTag}:(?<reg>[0-9a-f]{16});`, 'i');
    const match = expression.exec(packet);
    return match ? littleEndianHexStringToNumber(match.groups.reg) : null;
}

function bootResultName(value) {
    const number = Number(value);
    switch (number) {
        case 0: return 'success';
        case 1: return 'invalid-title-id';
        case 2: return 'core-not-ready';
        case 10: return 'internal-boot-failure';
        case 14: return 'title-not-found';
        default: return `status-${number}`;
    }
}

function formatValue(value) {
    return value == null ? 'unavailable' : value.toString();
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

function hexToAscii(hex) {
    let result = '';
    for (let index = 0; index + 1 < hex.length; index += 2) {
        const value = parseInt(hex.substring(index, index + 2), 16);
        if (!Number.isFinite(value) || value === 0) break;
        result += String.fromCharCode(value);
    }
    return result;
}

function littleEndianHexStringToNumber(hex) {
    const bytes = [];
    for (let index = 0; index < hex.length; index += 2) {
        bytes.push(parseInt(hex.substring(index, index + 2), 16));
    }
    let result = 0n;
    for (let index = bytes.length - 1; index >= 0; index--) {
        result = (result << 8n) | BigInt(bytes[index]);
    }
    return result;
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
'''
write('assets/data/rpcs3_stikdebug_launch.js', rpcs3_script)


# ---------------------------------------------------------------------------
# 4. Serialize preview video lifecycle and ignore stale async selections.
# ---------------------------------------------------------------------------
my_games_path = 'lib/screens/game_screen/my_games_list.dart'
insert_import(my_games_path, "import 'package:neostation/services/audio_policy_service.dart';")
my_games = read(my_games_path)
my_games = my_games.replace(
    """  bool _isVideoLoading = false;
  static const Duration _videoDelay = Duration(milliseconds: 1500);
""",
    """  bool _isVideoLoading = false;
  int _videoGeneration = 0;
  Future<void> _videoTransition = Future<void>.value();
  static const Duration _videoDelay = Duration(milliseconds: 1500);
""",
    1,
)
write(my_games_path, my_games)

part_path = 'lib/screens/game_screen/my_games_list/secondary_display.dart'
part = read(part_path)
# Replace reset/stop methods with generation invalidation and serialized teardown.
reset_pattern = re.compile(
    r"  /// Hard reset of the video preview system\..*?  /// Orchestrates background tasks triggered by game selection changes\.",
    flags=re.DOTALL,
)
reset_replacement = r'''  /// Hard reset of the video preview system.
  void _resetVideoState() {
    _invalidateVideoPreview(updateDucking: false);
  }

  /// Graceful termination of video resources with state synchronization.
  void _stopVideoAndCleanup() {
    _invalidateVideoPreview(updateDucking: true);
  }

  void _invalidateVideoPreview({required bool updateDucking}) {
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

    if (controller != null) {
      _videoTransition = _videoTransition
          .catchError((Object _) {})
          .then((_) => _disposeVideoController(controller, reason: 'invalidate'));
    }
    if (updateDucking) _updateMusicDucking();
  }

  Future<void> _disposeVideoController(
    VideoPlayerController controller, {
    required String reason,
  }) async {
    try {
      if (controller.value.isInitialized) {
        await controller.setVolume(0.0);
        await controller.pause();
      }
    } catch (error) {
      _SystemGamesListState._log.w('Video stop failed ($reason): $error');
    }
    try {
      await controller.dispose();
    } catch (error) {
      _SystemGamesListState._log.w('Video dispose failed ($reason): $error');
    }
  }

  Future<void> _fadeVideoVolume(
    VideoPlayerController controller, {
    required int generation,
    required double target,
  }) async {
    if (target <= 0) {
      await controller.setVolume(0.0);
      return;
    }
    // Readiness and cancellation are handled above. This short ramp only
    // removes the initial audio edge/click after the first decoded frame.
    const steps = 4;
    for (var step = 1; step <= steps; step++) {
      if (!mounted || generation != _videoGeneration ||
          _videoController != controller) return;
      await controller.setVolume(target * step / steps);
      if (step < steps) {
        await Future<void>.delayed(const Duration(milliseconds: 25));
      }
    }
  }

  /// Orchestrates background tasks triggered by game selection changes.'''
part, count = reset_pattern.subn(reset_replacement, part, count=1)
if count != 1:
    raise SystemExit('Primary video reset block not found')

# Capture generation at timer creation.
part = part.replace(
    """    _videoTimer = Timer(_SystemGamesListState._videoDelay, () async {
      if (!mounted) return;
      if (mounted && _selectedGame != null) {
""",
    """    final generation = _videoGeneration;
    final scheduledGame = _selectedGame;
    _videoTimer = Timer(_SystemGamesListState._videoDelay, () async {
      if (!mounted || generation != _videoGeneration) return;
      if (scheduledGame != null && _selectedGame == scheduledGame) {
""",
    1,
)
part = part.replace(
    'await _updateSecondaryDisplayVideo(_selectedGame!);',
    'await _updateSecondaryDisplayVideo(scheduledGame);',
    1,
)
part = part.replace(
    'await _initializeVideo(_selectedGame!);',
    'await _initializeVideo(scheduledGame, generation: generation);',
    1,
)

# Replace full initialize method up to next documented method.
init_pattern = re.compile(
    r"  /// Initializes the video player for the primary UI, including volume and loop management\..*?\n  /// Resolves the absolute filesystem path for",
    flags=re.DOTALL,
)
init_replacement = r'''  /// Initializes one preview generation. Controller destruction/creation is
  /// serialized so two AVPlayers can never own audio output at the same time.
  Future<void> _initializeVideo(
    GameModel game, {
    required int generation,
  }) async {
    if (!mounted || generation != _videoGeneration || _selectedGame != game) {
      return;
    }
    final config = context.read<SqliteConfigProvider>().config;
    if (!config.showGameInfo || _isGameLaunching) return;

    rebuild(() => _isVideoLoading = true);
    final videoPath = _getVideoPath(game);
    final exists = _fileProvider.isInitialized
        ? await _fileProvider.fileExists(videoPath)
        : File(videoPath).existsSync();
    if (!mounted || generation != _videoGeneration || _selectedGame != game) {
      return;
    }
    if (!exists) {
      rebuild(() {
        _showVideo = false;
        _isVideoLoading = false;
      });
      return;
    }

    final transition = _videoTransition.catchError((Object _) {}).then((_) async {
      if (!mounted || generation != _videoGeneration || _selectedGame != game) {
        return;
      }
      final old = _videoController;
      _videoController = null;
      if (old != null) {
        await _disposeVideoController(old, reason: 'replacement');
      }
      if (!mounted || generation != _videoGeneration || _selectedGame != game) {
        return;
      }

      final controller = VideoPlayerController.file(
        File(videoPath),
        videoPlayerOptions: VideoPlayerOptions(mixWithOthers: true),
      );
      try {
        await controller.initialize();
        await AudioPolicyService().ensureSilentCompatibleSession(
          reason: 'game-preview-video-initialized',
        );
        if (!mounted || generation != _videoGeneration || _selectedGame != game) {
          await _disposeVideoController(controller, reason: 'stale-initialize');
          return;
        }

        await controller.setVolume(0.0);
        await controller.setLooping(true);
        await controller.play();
        await AudioPolicyService().afterPlaybackStarted('game-preview-video');
        if (!mounted || generation != _videoGeneration || _selectedGame != game) {
          await _disposeVideoController(controller, reason: 'stale-play');
          return;
        }

        _videoController = controller;
        rebuild(() {
          _showVideo = true;
          _isVideoLoading = false;
        });
        await _fadeVideoVolume(
          controller,
          generation: generation,
          target: config.videoSound ? 1.0 : 0.0,
        );
        _updateMusicDucking();
      } catch (error) {
        await _disposeVideoController(controller, reason: 'initialize-error');
        if (mounted && generation == _videoGeneration) {
          rebuild(() {
            _showVideo = false;
            _isVideoLoading = false;
          });
        }
        _SystemGamesListState._log.e(
          'Error initializing video generation $generation: $error',
        );
      }
    });
    _videoTransition = transition;
    await transition;
    if (mounted && generation == _videoGeneration && !_showVideo) {
      rebuild(() => _isVideoLoading = false);
    }
  }

  /// Resolves the absolute filesystem path for'''
part, count = init_pattern.subn(init_replacement, part, count=1)
if count != 1:
    raise SystemExit('Primary video initialize method not found')
write(part_path, part)

# Secondary-screen AVPlayer: retain its existing generation checks but ensure
# the central session is reasserted around initialization/start. Its existing
# mute state remains authoritative for volume.
secondary_path = 'lib/screens/secondary_screen/secondary_screen.dart'
insert_import(secondary_path, "import 'package:neostation/services/audio_policy_service.dart';")
secondary = read(secondary_path)
secondary = secondary.replace(
    """      await controller.initialize();
""",
    """      await controller.initialize();
      await AudioPolicyService().ensureSilentCompatibleSession(
        reason: 'secondary-preview-video-initialized',
      );
""",
    1,
)
secondary = secondary.replace(
    """      await controller.play();
""",
    """      await controller.play();
      await AudioPolicyService().afterPlaybackStarted(
        'secondary-preview-video',
      );
""",
    1,
)
write(secondary_path, secondary)


# ---------------------------------------------------------------------------
# Tests and documentation.
# ---------------------------------------------------------------------------
audio_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('all NeoStation audio clients use the central audio policy', () {
    final policy = File('lib/services/audio_policy_service.dart').readAsStringSync();
    expect(policy, contains('class AudioPolicyService'));
    expect(policy, contains('ensureSilentCompatibleSession'));

    for (final file in <String>[
      'lib/services/sfx_service.dart',
      'lib/services/home_music_service.dart',
      'lib/services/music_player_service.dart',
      'lib/screens/game_screen/my_games_list/secondary_display.dart',
      'lib/screens/secondary_screen/secondary_screen.dart',
      'lib/widgets/shaders/shader_gif_widget.dart',
    ]) {
      expect(
        File(file).readAsStringSync(),
        contains('AudioPolicyService'),
        reason: file,
      );
    }
  });

  test('SFX retains and can stop active handles', () {
    final source = File('lib/services/sfx_service.dart').readAsStringSync();
    expect(source, contains('_activeHandles'));
    expect(source, contains('stopAllSounds'));
    expect(source, contains('getIsValidVoiceHandle'));
  });
}
'''
write('test/audio_policy_service_test.dart', audio_test)

video_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('primary preview serializes replacement and rejects stale generations', () {
    final host = File('lib/screens/game_screen/my_games_list.dart').readAsStringSync();
    final media = File(
      'lib/screens/game_screen/my_games_list/secondary_display.dart',
    ).readAsStringSync();
    expect(host, contains('_videoGeneration'));
    expect(host, contains('_videoTransition'));
    expect(media, contains('generation != _videoGeneration'));
    expect(media, contains('await controller.dispose()'));
    expect(media, contains("reason: 'replacement'"));
    expect(media, contains("reason: 'stale-initialize'"));
    expect(media, contains('await controller.setVolume(0.0)'));
  });
}
'''
write('test/video_preview_lifecycle_test.dart', video_test)

rpcs3_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';

void main() {
  test('existing synthetic RPCS3 metadata resolves to PARAM.SFO title', () {
    final resolved = GameModel.resolveDatabaseNamesForDisplay(
      DatabaseGameModel(
        filename: 'BLES00412',
        romPath: 'rpcs3-library://game?title-id=BLES00412',
        titleId: 'BLES00412',
        titleName: 'The Lord of the Rings: Conquest™',
        realName: 'BLES00412',
        screenscraperRealName: 'BLES00412',
      ),
    );
    expect(resolved.displayName, 'The Lord of the Rings: Conquest™');
    expect(resolved.realName, 'The Lord of the Rings: Conquest™');
    expect(resolved.hasMeaningfulScrapedName, isFalse);
  });

  test('RPCS3 protocol is immediate and records real return/state diagnostics', () {
    final service = File('lib/services/rpcs3_launch_service.dart').readAsStringSync();
    final script = File('assets/data/rpcs3_stikdebug_launch.js').readAsStringSync();
    expect(service, contains('openJitRequest'));
    expect(service, isNot(contains('warmupDelay:')));
    expect(script, contains('NEOSTATION_RPC_STATE_BEFORE'));
    expect(script, contains('NEOSTATION_RPC_BOOT_RESULT'));
    expect(script, contains('NEOSTATION_RPC_LAST_ERROR'));
    expect(script, contains('NEOSTATION_RPC_PROGRESS_AFTER'));
    expect(script, contains('p0;thread:'));
  });

  test('generated script contains the inspected RPCS3 0.2 function map', () {
    final template = File('assets/data/rpcs3_stikdebug_launch.js').readAsStringSync();
    final script = Rpcs3LaunchService.buildScriptForTesting(
      template,
      'BLES00412',
      displayTitle: 'The Lord of the Rings: Conquest™',
      sourcePath: '/Data/games/discImgs/BLES00412',
      sourceKind: 'disc-image',
      sessionId: 'session-1',
    );
    expect(script, contains('223884'));
    expect(script, contains('223996'));
    expect(script, contains('227968'));
    expect(script, contains('229172'));
    expect(script, isNot(contains('__NEOSTATION_')));
  });
}
'''
write('test/rpcs3_stage7_test.dart', rpcs3_test)

readme = read('README.md')
readme = re.sub(
    r"- \*\*RPCS3 iOS\*\*[^\n]*",
    '- **RPCS3 iOS** authoritative Data-folder synchronization, repaired '
    'PARAM.SFO title precedence, Title-ID ScreenScraper lookup and an '
    'experimental state-aware StikDebug launch protocol for the inspected '
    'RPCS3 iOS 0.1/0.2 cores.',
    readme,
    count=1,
)
write('README.md', readme)

print('NeoStation Stage 7 patch applied.')
