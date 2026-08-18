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


def insert_import(path: str, import_line: str) -> None:
    text = read(path)
    if import_line in text:
        return
    matches = list(re.finditer(r'^import .*?;\s*$', text, flags=re.MULTILINE))
    if not matches:
        raise SystemExit(f'No imports found in {path}')
    index = matches[-1].end()
    write(path, text[:index] + '\n' + import_line + text[index:])


def find_block_end(text: str, brace_index: int) -> int:
    depth = 0
    quote = None
    escape = False
    for index in range(brace_index, len(text)):
        ch = text[index]
        if quote is not None:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ('\"', "'"):
            quote = ch
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return index + 1
    raise SystemExit('Unbalanced block')


def replace_function(path: str, signature_pattern: str, replacement: str) -> None:
    text = read(path)
    match = re.search(signature_pattern, text, flags=re.MULTILINE)
    if not match:
        if replacement.strip() in text:
            return
        raise SystemExit(f'Function marker not found in {path}: {signature_pattern}')
    brace = text.find('{', match.start())
    end = find_block_end(text, brace)
    write(path, text[:match.start()] + replacement.rstrip() + text[end:])


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
    raise SystemExit('Could not update build number')
write('pubspec.yaml', pubspec)


# ---------------------------------------------------------------------------
# 1. Central audio policy: one serialized iOS session policy and one volume gate
# ---------------------------------------------------------------------------
audio_policy = r'''import 'dart:async';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'logger_service.dart';

/// Shared audio policy for every NeoStation audio producer.
///
/// iOS does not expose a supported API that reports the hardware Ring/Silent
/// switch state. The supported contract is to keep every app-owned output on
/// an `AVAudioSession.Category.ambient` session. iOS then silences those active
/// outputs immediately when the switch is engaged and restores their configured
/// volume when it is disengaged.
///
/// This service serializes category changes so SoLoud and AVPlayer cannot race
/// each other, provides the common app/lifecycle volume gate, and lets active
/// players react to policy changes through one source of truth.
class AudioPolicySnapshot {
  const AudioPolicySnapshot({
    required this.applicationActive,
    required this.applicationAudioEnabled,
    required this.revision,
  });

  final bool applicationActive;
  final bool applicationAudioEnabled;
  final int revision;

  bool get playbackAllowed => applicationActive && applicationAudioEnabled;

  double effectiveVolume(double configuredVolume) =>
      playbackAllowed ? configuredVolume.clamp(0.0, 1.0) : 0.0;
}

typedef AudioPolicyClient = FutureOr<void> Function(
  AudioPolicySnapshot snapshot,
);

class AudioPolicyService extends ChangeNotifier with WidgetsBindingObserver {
  AudioPolicyService._internal();

  static final AudioPolicyService _instance = AudioPolicyService._internal();
  factory AudioPolicyService() => _instance;

  final LoggerService _log = LoggerService.instance;
  final Map<Object, AudioPolicyClient> _clients = <Object, AudioPolicyClient>{};

  bool _initialized = false;
  bool _applicationActive = true;
  bool _applicationAudioEnabled = true;
  int _revision = 0;
  Future<void> _sessionQueue = Future<void>.value();

  bool get initialized => _initialized;
  bool get playbackAllowed => snapshot.playbackAllowed;
  AudioPolicySnapshot get snapshot => AudioPolicySnapshot(
    applicationActive: _applicationActive,
    applicationAudioEnabled: _applicationAudioEnabled,
    revision: _revision,
  );

  Future<void> init() async {
    if (_initialized) return;
    _initialized = true;
    WidgetsBinding.instance.addObserver(this);
    await enforceSilentSwitchPolicy(reason: 'initialization');
  }

  /// Registers one active audio client and returns an unregister callback.
  VoidCallback registerClient(Object owner, AudioPolicyClient client) {
    _clients[owner] = client;
    unawaited(_invokeClient(client, snapshot));
    return () => _clients.remove(owner);
  }

  double effectiveVolume(double configuredVolume) =>
      snapshot.effectiveVolume(configuredVolume);

  /// Application-level mute gate. It is intentionally separate from the
  /// hardware switch: the latter is enforced by iOS through `.ambient`.
  Future<void> setApplicationAudioEnabled(
    bool value, {
    String reason = 'application setting',
  }) async {
    if (_applicationAudioEnabled == value) return;
    _applicationAudioEnabled = value;
    _revision++;
    _log.i('[AudioPolicy] Audio ${value ? 'enabled' : 'muted'}: $reason');
    await _notifyClients();
    if (value) await enforceSilentSwitchPolicy(reason: 'unmute:$reason');
  }

  /// Reasserts the only native session category NeoStation is allowed to use.
  /// Calls are serialized because SoLoud/AVPlayer can initialize concurrently.
  Future<void> enforceSilentSwitchPolicy({required String reason}) {
    if (!Platform.isIOS) return Future<void>.value();
    final completer = Completer<void>();
    _sessionQueue = _sessionQueue.catchError((_) {}).then((_) async {
      try {
        await ExternalFolderAccess.configureAudioSessionForSilentMode();
        completer.complete();
      } catch (error) {
        _log.w('[AudioPolicy] Could not enforce ambient session ($reason): $error');
        completer.complete();
      }
    });
    return completer.future;
  }

  Future<void> _notifyClients() async {
    final current = snapshot;
    final callbacks = List<AudioPolicyClient>.from(_clients.values);
    for (final callback in callbacks) {
      await _invokeClient(callback, current);
    }
    notifyListeners();
  }

  Future<void> _invokeClient(
    AudioPolicyClient callback,
    AudioPolicySnapshot current,
  ) async {
    try {
      await callback(current);
    } catch (error) {
      _log.w('[AudioPolicy] Client update failed: $error');
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final active = state == AppLifecycleState.resumed;
    if (_applicationActive == active) {
      if (active) {
        unawaited(enforceSilentSwitchPolicy(reason: 'resume'));
      }
      return;
    }
    _applicationActive = active;
    _revision++;
    unawaited(_notifyClients());
    if (active) {
      unawaited(enforceSilentSwitchPolicy(reason: 'resume'));
    }
  }
}
'''
write('lib/services/audio_policy_service.dart', audio_policy)


# Initialize the policy before any eager audio consumer.
insert_import(
    'lib/main.dart',
    "import 'package:neostation/services/audio_policy_service.dart';",
)
main = read('lib/main.dart')
if 'await AudioPolicyService().init();' not in main:
    marker = 'WidgetsFlutterBinding.ensureInitialized();'
    if marker not in main:
        raise SystemExit('Widgets binding marker missing in main.dart')
    main = main.replace(
        marker,
        marker + '\n  await AudioPolicyService().init();',
        1,
    )
write('lib/main.dart', main)


# ---------------------------------------------------------------------------
# SFX: retain active handles, centralize policy, stop active voices when muted
# ---------------------------------------------------------------------------
sfx_path = 'lib/services/sfx_service.dart'
sfx = read(sfx_path)
sfx = sfx.replace(
    "import 'package:external_folder_access/external_folder_access.dart';\n",
    "import 'package:neostation/services/audio_policy_service.dart';\n",
)
if "audio_policy_service.dart" not in sfx:
    insert_import(sfx_path, "import 'package:neostation/services/audio_policy_service.dart';")
    sfx = read(sfx_path)

field_marker = '  final Map<String, AudioSource> _sources = {};'
field_addition = '''  final Map<String, AudioSource> _sources = {};
  final Set<SoundHandle> _activeHandles = <SoundHandle>{};
  final Map<SoundHandle, Timer> _handleCleanupTimers = <SoundHandle, Timer>{};
  VoidCallback? _audioPolicyUnregister;'''
if '_activeHandles' not in sfx:
    if field_marker not in sfx:
        raise SystemExit('SFX source field marker missing')
    sfx = sfx.replace(field_marker, field_addition, 1)

sfx = sfx.replace(
    'await _restoreSilentModeAudioSession();',
    "await AudioPolicyService().enforceSilentSwitchPolicy(reason: 'sfx-engine');",
)

init_ready_marker = "      _isInitialized = true;\n      _log.i("
if '_audioPolicyUnregister ??=' not in sfx:
    if init_ready_marker not in sfx:
        raise SystemExit('SFX ready marker missing')
    sfx = sfx.replace(
        init_ready_marker,
        "      await AudioPolicyService().init();\n"
        "      _audioPolicyUnregister ??= AudioPolicyService().registerClient(\n"
        "        this,\n"
        "        _handleAudioPolicyChanged,\n"
        "      );\n"
        "      _isInitialized = true;\n"
        "      _log.i(",
        1,
    )

# Engine teardown must invalidate handles/timers too.
teardown_marker = "    _sources.clear();\n    _isInitialized = false;"
if "_activeHandles.clear();" not in sfx:
    if teardown_marker not in sfx:
        raise SystemExit('SFX teardown marker missing')
    sfx = sfx.replace(
        teardown_marker,
        "    for (final timer in _handleCleanupTimers.values) {\n"
        "      timer.cancel();\n"
        "    }\n"
        "    _handleCleanupTimers.clear();\n"
        "    _activeHandles.clear();\n"
        "    _sources.clear();\n"
        "    _isInitialized = false;",
        1,
    )

# Disable now stops voices already in flight.
old_set_enabled = '''  void setEnabled(bool value) {
    _enabled = value;
    _log.d('[SfxService] SFX ${value ? 'enabled' : 'disabled'}');
  }'''
new_set_enabled = '''  void setEnabled(bool value) {
    _enabled = value;
    if (!value) unawaited(_stopActiveHandles());
    _log.d('[SfxService] SFX ${value ? 'enabled' : 'disabled'}');
  }'''
if old_set_enabled in sfx:
    sfx = sfx.replace(old_set_enabled, new_set_enabled, 1)

write(sfx_path, sfx)

replace_function(
    sfx_path,
    r'^  Future<void> _play\(String path\) async\s*\{',
    r'''  Future<void> _play(String path) async {
    final source = _sources[path];
    if (source == null) {
      _log.w('[SfxService] Source not found for: $path');
      return;
    }
    if (!_enabled || !AudioPolicyService().playbackAllowed) return;

    try {
      final policy = AudioPolicyService();
      await policy.enforceSilentSwitchPolicy(reason: 'sfx-before:$path');
      if (!_enabled || !policy.playbackAllowed) return;

      final handle = SoLoud.instance.play(
        source,
        volume: policy.effectiveVolume(_volume),
      );
      _activeHandles.add(handle);

      // Some SoLoud iOS backends activate their session during play(). Apply
      // `.ambient` again after the voice exists so the first buffer and every
      // subsequent buffer obey the hardware Ring/Silent switch.
      await policy.enforceSilentSwitchPolicy(reason: 'sfx-after:$path');
      _scheduleHandleCleanup(handle, source);
    } catch (e) {
      _log.w('[SfxService] Playback error for $path: $e');
    }
  }''',
)

# Replace old per-service native helper with centralized client helpers.
sfx = read(sfx_path)
helper_match = re.search(
    r'^  Future<void> _restoreSilentModeAudioSession\(\) async\s*\{',
    sfx,
    flags=re.MULTILINE,
)
if helper_match:
    end = find_block_end(sfx, sfx.find('{', helper_match.start()))
    helpers = r'''  Future<void> _handleAudioPolicyChanged(
    AudioPolicySnapshot snapshot,
  ) async {
    if (!snapshot.playbackAllowed) {
      await _stopActiveHandles();
      return;
    }
    await AudioPolicyService().enforceSilentSwitchPolicy(
      reason: 'sfx-policy-${snapshot.revision}',
    );
  }

  void _scheduleHandleCleanup(SoundHandle handle, AudioSource source) {
    _handleCleanupTimers.remove(handle)?.cancel();
    Duration length = Duration.zero;
    try {
      length = SoLoud.instance.getLength(source);
    } catch (_) {}
    final cleanupAfter = length > Duration.zero
        ? length + const Duration(milliseconds: 120)
        : const Duration(seconds: 3);
    _handleCleanupTimers[handle] = Timer(cleanupAfter, () {
      _handleCleanupTimers.remove(handle);
      _activeHandles.remove(handle);
    });
  }

  Future<void> _stopActiveHandles() async {
    final handles = List<SoundHandle>.from(_activeHandles);
    _activeHandles.clear();
    for (final timer in _handleCleanupTimers.values) {
      timer.cancel();
    }
    _handleCleanupTimers.clear();
    if (!SoLoud.instance.isInitialized) return;
    for (final handle in handles) {
      try {
        await SoLoud.instance.stop(handle);
      } catch (_) {}
    }
  }'''
    sfx = sfx[:helper_match.start()] + helpers + sfx[end:]

# Ensure dispose stops voices before unloading sources.
dispose_marker = '  Future<void> dispose() async {\n'
if 'await _stopActiveHandles();' not in sfx[sfx.find(dispose_marker):sfx.find(dispose_marker) + 300]:
    if dispose_marker not in sfx:
        raise SystemExit('SFX dispose marker missing')
    sfx = sfx.replace(
        dispose_marker,
        dispose_marker + '    await _stopActiveHandles();\n',
        1,
    )
write(sfx_path, sfx)


# ---------------------------------------------------------------------------
# Home menu music: consume central policy only
# ---------------------------------------------------------------------------
home_path = 'lib/services/home_music_service.dart'
home = read(home_path)
home = home.replace(
    "import 'package:external_folder_access/external_folder_access.dart';\n",
    "import 'package:neostation/services/audio_policy_service.dart';\n",
)
if 'VoidCallback? _audioPolicyUnregister;' not in home:
    marker = '  SoundHandle? _handle;'
    if marker not in home:
        raise SystemExit('HomeMusic handle marker missing')
    home = home.replace(
        marker,
        marker + '\n  VoidCallback? _audioPolicyUnregister;',
        1,
    )

observer_marker = '    WidgetsBinding.instance.addObserver(this);'
if '_audioPolicyUnregister ??=' not in home:
    if observer_marker not in home:
        raise SystemExit('HomeMusic observer marker missing')
    home = home.replace(
        observer_marker,
        "    await AudioPolicyService().init();\n"
        "    _audioPolicyUnregister ??= AudioPolicyService().registerClient(\n"
        "      this,\n"
        "      (_) => _syncPlayback(),\n"
        "    );\n"
        + observer_marker,
        1,
    )

home = home.replace(
    '      !MusicPlayerService().isPlaying;',
    '      !MusicPlayerService().isPlaying &&\n      AudioPolicyService().playbackAllowed;',
)
home = home.replace(
    'await _restoreSilentModeAudioSession();',
    "await AudioPolicyService().enforceSilentSwitchPolicy(reason: 'home-music');",
)
home = home.replace(
    'volume: _volume, looping: true',
    'volume: AudioPolicyService().effectiveVolume(_volume), looping: true',
)
# Keep helper names used by lifecycle, but delegate to policy.
helper = re.search(
    r'^  Future<void> _restoreSilentModeAudioSession\(\) async\s*\{',
    home,
    flags=re.MULTILINE,
)
if helper:
    end = find_block_end(home, home.find('{', helper.start()))
    replacement = r'''  Future<void> _restoreSilentModeAudioSession() =>
      AudioPolicyService().enforceSilentSwitchPolicy(reason: 'home-music');'''
    home = home[:helper.start()] + replacement + home[end:]
write(home_path, home)


# ---------------------------------------------------------------------------
# Music player: central volume gate and ambient-session enforcement
# ---------------------------------------------------------------------------
music_path = 'lib/services/music_player_service.dart'
insert_import(music_path, "import 'package:neostation/services/audio_policy_service.dart';")
music = read(music_path)
if 'VoidCallback? _audioPolicyUnregister;' not in music:
    marker = '  bool _isInitialized = false;'
    if marker not in music:
        raise SystemExit('Music player init field marker missing')
    music = music.replace(
        marker,
        marker + '\n  VoidCallback? _audioPolicyUnregister;',
        1,
    )

init_marker = '      _audioData = AudioData(GetSamplesKind.linear);'
if '_audioPolicyUnregister ??=' not in music:
    if init_marker not in music:
        raise SystemExit('Music player audio-data marker missing')
    music = music.replace(
        init_marker,
        "      await AudioPolicyService().init();\n"
        "      _audioPolicyUnregister ??= AudioPolicyService().registerClient(\n"
        "        this,\n"
        "        (_) async {\n"
        "          _applyVolume();\n"
        "          await AudioPolicyService().enforceSilentSwitchPolicy(\n"
        "            reason: 'music-policy',\n"
        "          );\n"
        "        },\n"
        "      );\n"
        "      await AudioPolicyService().enforceSilentSwitchPolicy(\n"
        "        reason: 'music-init',\n"
        "      );\n\n"
        + init_marker,
        1,
    )

old_effective = '    final double effectiveVolume = _isDucked ? _volume * 0.1 : _volume;'
new_effective = '''    final configuredVolume = _isDucked ? _volume * 0.1 : _volume;
    final effectiveVolume = AudioPolicyService().effectiveVolume(
      configuredVolume,
    );'''
if old_effective in music:
    music = music.replace(old_effective, new_effective, 1)

# Reassert after any SoLoud play assignment in the primary start path.
if "reason: 'music-after-play'" not in music:
    play_match = re.search(r'_currentHandle\s*=\s*[^;]*?\.play\(', music)
    if play_match:
        open_paren = music.find('(', play_match.start())
        depth = 0
        close = None
        for index in range(open_paren, len(music)):
            if music[index] == '(':
                depth += 1
            elif music[index] == ')':
                depth -= 1
                if depth == 0:
                    semicolon = music.find(';', index)
                    close = semicolon + 1
                    break
        if close:
            music = (
                music[:close]
                + "\n      await AudioPolicyService().enforceSilentSwitchPolicy(\n"
                + "        reason: 'music-after-play',\n"
                + "      );"
                + music[close:]
            )
write(music_path, music)


# ---------------------------------------------------------------------------
# 2. RPCS3 names: fix the actual list read path and repair legacy metadata rows
# ---------------------------------------------------------------------------
game_list_path = 'lib/services/game/game_list_service.dart'
game_list = read(game_list_path)

replace_function(
    game_list_path,
    r'^  static bool _hasScreenscraperRealName\(DatabaseGameModel dbGame\)\s*\{',
    r'''  static bool _hasScreenscraperRealName(DatabaseGameModel dbGame) {
    final candidate = dbGame.screenscraperRealName?.trim();
    if (candidate == null || candidate.isEmpty) return false;
    if (!dbGame.romPath.toLowerCase().startsWith('rpcs3-library://')) {
      return true;
    }
    return GameModel.isMeaningfulRpcs3MetadataNameForTesting(
      candidate,
      titleId: dbGame.titleId,
      filename: dbGame.filename,
    );
  }''',
)

replace_function(
    game_list_path,
    r'^  static \(\{String name, bool showRomFileNameSubtitle\}\) _resolveListDisplayName\(\{',
    r'''  static ({String name, bool showRomFileNameSubtitle}) _resolveListDisplayName({
    required DatabaseGameModel dbGame,
    required bool preferFileName,
    required bool hideExtension,
    required bool hideParentheses,
    required bool hideBrackets,
    required Set<String> validExtensionsSet,
  }) {
    final filename = dbGame.filename;
    final isRpcs3Virtual = dbGame.romPath.toLowerCase().startsWith(
      'rpcs3-library://',
    );
    final scraped = _hasScreenscraperRealName(dbGame);

    String? meaningfulRpcs3Name(String? value) {
      if (!isRpcs3Virtual) return value?.trim();
      return GameModel.isMeaningfulRpcs3MetadataNameForTesting(
        value,
        titleId: dbGame.titleId,
        filename: filename,
      )
          ? value!.trim()
          : null;
    }

    final meaningfulScraped = scraped
        ? meaningfulRpcs3Name(dbGame.screenscraperRealName)
        : null;
    final meaningfulRealName = meaningfulRpcs3Name(dbGame.realName);
    final meaningfulTitleName = meaningfulRpcs3Name(dbGame.titleName);
    final coalesced = isRpcs3Virtual
        ? meaningfulScraped ??
              meaningfulRealName ??
              meaningfulTitleName ??
              filename
        : dbGame.realName ?? dbGame.titleName ?? filename;

    // URI-backed RPCS3 rows use the Title ID as their synthetic filename. A
    // global "prefer filename" option must not hide an available PARAM.SFO or
    // ScreenScraper title for those rows.
    if (preferFileName && !isRpcs3Virtual) {
      return (
        name: _formatListNameFromFilename(
          filename,
          validExtensionsSet,
          hideExtension: hideExtension,
          hideParentheses: hideParentheses,
          hideBrackets: hideBrackets,
        ),
        showRomFileNameSubtitle: false,
      );
    }
    if (scraped && meaningfulScraped != null) {
      return (
        name: _formatListNameFromScrapedTitle(meaningfulScraped),
        showRomFileNameSubtitle: !isRpcs3Virtual,
      );
    }
    if (coalesced != filename) {
      return (name: coalesced, showRomFileNameSubtitle: false);
    }
    return (
      name: _formatListNameFromFilename(
        filename,
        validExtensionsSet,
        hideExtension: hideExtension,
        hideParentheses: hideParentheses,
        hideBrackets: hideBrackets,
      ),
      showRomFileNameSubtitle: false,
    );
  }''',
)

game_list = read(game_list_path)
# Replace every manual GameModel construction in this read service with the
# canonical database conversion, then apply only list-specific presentation.
search_from = 0
replaced_models = 0
while True:
    start = game_list.find('return GameModel(', search_from)
    if start < 0:
        break
    paren = game_list.find('(', start)
    depth = 0
    end = None
    for index in range(paren, len(game_list)):
        if game_list[index] == '(':
            depth += 1
        elif game_list[index] == ')':
            depth -= 1
            if depth == 0:
                semicolon = game_list.find(';', index)
                end = semicolon + 1
                break
    if end is None:
        raise SystemExit('Could not parse GameModel constructor in GameListService')
    block = game_list[start:end]
    folder_expr = 'system.folderName' if 'systemFolderName: system.folderName' in block else 'dbGame.systemFolderName'
    replacement = f'''return GameModel.fromDatabaseModel(dbGame).copyWith(
            name: resolved.name,
            showRomFileNameSubtitle: resolved.showRomFileNameSubtitle,
            systemFolderName: {folder_expr},
          );'''
    indent = re.match(r'\s*', game_list[game_list.rfind('\n', 0, start) + 1:start]).group(0)
    replacement = replacement.replace('\n', '\n' + indent)
    game_list = game_list[:start] + replacement + game_list[end:]
    search_from = start + len(replacement)
    replaced_models += 1
if replaced_models < 4:
    raise SystemExit(f'Expected at least 4 GameModel read conversions, got {replaced_models}')
write(game_list_path, game_list)


# Wrap RPCS3 import so every sync repairs old synthetic metadata too.
rpcs3_library_path = 'lib/services/rpcs3_library_service.dart'
rpcs3_library = read(rpcs3_library_path)
raw_decl = re.search(
    r'^  static Future<Rpcs3SyncResult> _importIntoNeoStation\(',
    rpcs3_library,
    flags=re.MULTILINE,
)
if not raw_decl:
    raise SystemExit('RPCS3 import method missing')
if '_importIntoNeoStationRaw(' not in rpcs3_library:
    rpcs3_library = (
        rpcs3_library[:raw_decl.start()]
        + rpcs3_library[raw_decl.start():].replace(
            '_importIntoNeoStation(',
            '_importIntoNeoStationRaw(',
            1,
        )
    )
    wrapper = r'''  static Future<Rpcs3SyncResult> _importIntoNeoStation(
    List<Rpcs3LibraryGame> games,
  ) async {
    final result = await _importIntoNeoStationRaw(games);
    await _repairPersistedRpcs3Names(games);
    return result;
  }

'''
    insert_at = rpcs3_library.find(
        '  static Future<Rpcs3SyncResult> _importIntoNeoStationRaw(',
    )
    rpcs3_library = rpcs3_library[:insert_at] + wrapper + rpcs3_library[insert_at:]

repair_helper = r'''  static Future<void> _repairPersistedRpcs3Names(
    List<Rpcs3LibraryGame> games,
  ) async {
    if (games.isEmpty) return;
    final db = await SqliteService.getDatabase();
    await db.transaction((txn) async {
      final metadataInfo = await txn.rawQuery(
        'PRAGMA table_info(user_screenscraper_metadata)',
      );
      final metadataColumns = metadataInfo
          .map((row) => row['name']?.toString() ?? '')
          .where((name) => name.isNotEmpty)
          .toSet();
      final repairableColumns = <String>[
        for (final name in const <String>[
          'ss_real_name',
          'real_name',
          'game_display_name',
        ])
          if (metadataColumns.contains(name)) name,
      ];
      final metadataHasSystem = metadataColumns.contains('app_system_id');

      for (final game in games) {
        final titleId = game.titleId.trim().toUpperCase();
        final title = game.title.trim();
        if (titleId.isEmpty ||
            title.isEmpty ||
            title.toUpperCase() == titleId) {
          continue;
        }

        await txn.rawUpdate(
          '''UPDATE user_roms
             SET title_name = ?
             WHERE app_system_id = 'ps3'
               AND (UPPER(COALESCE(title_id, '')) = ? OR filename = ?)''',
          <Object?>[title, titleId, titleId],
        );

        if (!metadataColumns.contains('filename')) continue;
        for (final column in repairableColumns) {
          final where = metadataHasSystem
              ? "app_system_id = 'ps3' AND filename = ?"
              : 'filename = ?';
          await txn.rawUpdate(
            '''UPDATE user_screenscraper_metadata
               SET $column = NULL
               WHERE $where
                 AND UPPER(
                   REPLACE(TRIM(COALESCE($column, '')), '.RPCS3', '')
                 ) = ?''',
            <Object?>[titleId, titleId],
          );
        }
      }
    });
  }

'''
if '_repairPersistedRpcs3Names(' not in rpcs3_library[rpcs3_library.find('_importIntoNeoStationRaw'):]:
    marker = '  static Future<void> _writeDebugFile('
    if marker not in rpcs3_library:
        raise SystemExit('RPCS3 debug helper marker missing')
    rpcs3_library = rpcs3_library.replace(marker, repair_helper + marker, 1)
write(rpcs3_library_path, rpcs3_library)


# ---------------------------------------------------------------------------
# 3. RPCS3 direct launch: state-driven second pass and real return-code logs
# ---------------------------------------------------------------------------
rpcs3_launch = r'''import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Experimental RPCS3 iOS launcher for the exact inspected RPCS3 cores.
///
/// The first pass remains the proven StikDebug Universal-JIT handoff that opens
/// RPCS3. Once the user presses RPCS3's native Start button and returns once to
/// NeoStation, the second pass is dispatched immediately from a real foreground
/// lifecycle event. It no longer schedules another delayed `launch-app`, which
/// previously reopened RPCS3's Start page from the background.
///
/// The direct script fingerprints the loaded dylib, resolves ASLR from its live
/// load address, records state/progress, calls `rpcs3_ios_boot_game`, reads its
/// integer return value from x0, then restores registers and detaches.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';

  /// UUID -> verified exported function offsets from the dylib load address.
  static const Map<String, Map<String, int>> supportedCoreFunctions =
      <String, Map<String, int>>{
        'CFE15492152B331E83959A3CF9AC8A9F': <String, int>{
          'boot': 0x2fa18,
        },
        '5C4D64FFB79930AD879C13009838F136': <String, int>{
          'boot': 0x36224,
          'state': 0x36a8c,
          'progress': 0x36afc,
        },
      };

  static const Map<String, int> supportedCoreBootOffsets = <String, int>{
    'CFE15492152B331E83959A3CF9AC8A9F': 0x2fa18,
    '5C4D64FFB79930AD879C13009838F136': 0x36224,
  };
  static const String currentCoreUuid =
      '5C4D64FF-B799-30AD-879C-13009838F136';
  static const int currentBootGameOffset = 0x36224;
  static const String expectedCoreUuid = currentCoreUuid;
  static const int bootGameOffset = currentBootGameOffset;

  static const String _assetPath = 'assets/data/rpcs3_stikdebug_launch.js';
  static const String _pendingRequestKey = 'rpcs3_pending_launch_request_v2';
  static const String _pendingStageKey = 'rpcs3_pending_launch_stage_v2';
  static const String _stageWaitingForRpcStart = 'waiting_for_rpc_start';
  static const String _stageDirectDispatched = 'direct_dispatched';
  static const Duration _requestLifetime = Duration(minutes: 12);

  static final LoggerService _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');
  static bool _resumeDispatchRunning = false;

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
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
    if (normalized == null) {
      throw const FormatException('Invalid RPCS3 title ID.');
    }
    final request = <String, dynamic>{
      'sessionId': sessionId,
      'titleId': normalized,
      'displayTitle': displayTitle,
      'sourcePath': sourcePath,
      'sourceKind': sourceKind,
    };
    return template
        .replaceAll('__NEOSTATION_REQUEST_JSON__', jsonEncode(request))
        .replaceAll('__NEOSTATION_TITLE_ID_JSON__', jsonEncode(normalized))
        .replaceAll(
          '__NEOSTATION_SUPPORTED_FUNCTIONS_JSON__',
          jsonEncode(supportedCoreFunctions),
        )
        .replaceAll(
          '__NEOSTATION_SUPPORTED_CORES_JSON__',
          jsonEncode(supportedCoreBootOffsets),
        )
        .replaceAll(
          '__NEOSTATION_CORE_UUID_JSON__',
          jsonEncode(currentCoreUuid),
        )
        .replaceAll(
          '__NEOSTATION_BOOT_OFFSET_HEX__',
          currentBootGameOffset.toRadixString(16),
        );
  }

  static Future<bool> launchTitle(
    String? rawTitleId, {
    String displayTitle = '',
    String sourcePath = '',
    String sourceKind = '',
  }) async {
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null) return false;

    final now = DateTime.now();
    final request = <String, dynamic>{
      'sessionId': '${now.microsecondsSinceEpoch.toRadixString(36)}-$titleId',
      'titleId': titleId,
      'displayTitle': displayTitle,
      'sourcePath': sourcePath,
      'sourceKind': sourceKind,
      'createdAtMs': now.millisecondsSinceEpoch,
      'directAttempts': 0,
    };
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingRequestKey, jsonEncode(request));
    await prefs.setString(_pendingStageKey, _stageWaitingForRpcStart);
    await _appendProtocolLog(
      'REQUEST_CREATED',
      request,
      extra: 'Universal JIT first pass requested.',
    );

    try {
      // This window belongs only to StikDebug's proven Universal preparation;
      // it is not used to infer RPCS3 core readiness or to schedule direct boot.
      final opened = await ExternalFolderAccess.openAppAfterJitPreflight(
        targetBaseBundleId: targetBundleId,
        warmupDelay: const Duration(seconds: 11),
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      await _appendProtocolLog(
        opened == true ? 'FIRST_PASS_OPENED' : 'FIRST_PASS_FAILED',
        request,
      );
      return opened == true;
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: first pass failed for $titleId',
        error: error,
        stackTrace: stack,
      );
      await _appendProtocolLog('FIRST_PASS_ERROR', request, extra: '$error');
      return false;
    }
  }

  /// Called from NeoStation's real `resumed` lifecycle event after the user has
  /// pressed Start in RPCS3 and manually returned once to NeoStation.
  static Future<bool> handleAppResumed() async {
    if (_resumeDispatchRunning) return false;
    _resumeDispatchRunning = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final stage = prefs.getString(_pendingStageKey);
      if (stage != _stageWaitingForRpcStart) return false;
      final raw = prefs.getString(_pendingRequestKey);
      if (raw == null || raw.isEmpty) return false;

      final request = Map<String, dynamic>.from(jsonDecode(raw) as Map);
      final createdAt = DateTime.fromMillisecondsSinceEpoch(
        int.tryParse(request['createdAtMs']?.toString() ?? '') ?? 0,
      );
      if (DateTime.now().difference(createdAt) > _requestLifetime) {
        await clearPendingLaunch(reason: 'expired');
        return false;
      }

      final titleId = normalizeTitleId(request['titleId']?.toString());
      if (titleId == null) {
        await clearPendingLaunch(reason: 'invalid-title');
        return false;
      }

      final template = await rootBundle.loadString(_assetPath);
      final script = buildScriptForTesting(
        template,
        titleId,
        displayTitle: request['displayTitle']?.toString() ?? '',
        sourcePath: request['sourcePath']?.toString() ?? '',
        sourceKind: request['sourceKind']?.toString() ?? '',
        sessionId: request['sessionId']?.toString() ?? '',
      );
      final scriptData = base64Url
          .encode(utf8.encode(script))
          .replaceAll('=', '');

      request['directAttempts'] =
          (int.tryParse(request['directAttempts']?.toString() ?? '0') ?? 0) + 1;
      request['directDispatchedAtMs'] = DateTime.now().millisecondsSinceEpoch;
      await prefs.setString(_pendingRequestKey, jsonEncode(request));
      await prefs.setString(_pendingStageKey, _stageDirectDispatched);
      await _appendProtocolLog(
        'DIRECT_PASS_REQUESTED',
        request,
        extra: 'Foreground dispatch; no delayed target relaunch.',
      );

      final opened = await ExternalFolderAccess.openJitScriptOnly(
        targetBaseBundleId: targetBundleId,
        scriptName: 'neostation-rpcs3-direct-v2.js',
        scriptDataBase64Url: scriptData,
        debugFileName: 'rpcs3_launch_second_pass_debug.txt',
      );
      await _appendProtocolLog(
        opened == true ? 'DIRECT_PASS_OPENED' : 'DIRECT_PASS_FAILED',
        request,
      );
      return opened == true;
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: direct pass failed',
        error: error,
        stackTrace: stack,
      );
      await _appendProtocolLog(
        'DIRECT_PASS_ERROR',
        const <String, dynamic>{},
        extra: '$error',
      );
      return false;
    } finally {
      _resumeDispatchRunning = false;
    }
  }

  static Future<void> clearPendingLaunch({required String reason}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_pendingRequestKey);
    await prefs.remove(_pendingStageKey);
    await _appendProtocolLog(
      'REQUEST_CLEARED',
      const <String, dynamic>{},
      extra: reason,
    );
  }

  static Future<void> _appendProtocolLog(
    String state,
    Map<String, dynamic> request, {
    String? extra,
  }) async {
    try {
      final documents = await getApplicationDocumentsDirectory();
      final file = File(
        path.join(documents.path, 'rpcs3_launch_protocol_debug.txt'),
      );
      final line = <String>[
        '${DateTime.now().toIso8601String()} STATE: $state',
        if (request['sessionId'] != null)
          'Session: ${request['sessionId']}',
        if (request['titleId'] != null) 'Title ID: ${request['titleId']}',
        if (request['displayTitle'] != null)
          'Display title: ${request['displayTitle']}',
        if (request['sourcePath'] != null)
          'Source path: ${request['sourcePath']}',
        if (request['sourceKind'] != null)
          'Source kind: ${request['sourceKind']}',
        if (request['directAttempts'] != null)
          'Direct attempts: ${request['directAttempts']}',
        if (extra != null) 'Extra: $extra',
        '',
      ].join('\n');
      await file.writeAsString(line, mode: FileMode.append, flush: true);
    } catch (_) {}
  }
}
'''
write('lib/services/rpcs3_launch_service.dart', rpcs3_launch)


rpcs3_script = r'''// NeoStation RPCS3 direct title launcher v2.
// Runs only after RPCS3's native Start gate has initialized the active core.
// It fingerprints the live module, resolves ASLR from load_address, records
// readiness, calls rpcs3_ios_boot_game(title_id), reads the int32 return value
// from x0, restores the stopped thread and detaches.

const neoRequest = __NEOSTATION_REQUEST_JSON__;
const neoSupportedFunctions = __NEOSTATION_SUPPORTED_FUNCTIONS_JSON__;
const neoReturnTrapInstruction = 'c0013ed4'; // brk #0xf00e, little endian

let neoPid = get_pid();
let neoAttachResponse = send_command(`vAttach;${neoPid.toString(16)}`);
let neoTid = resolveStoppedThread(neoAttachResponse);
log(`NEOSTATION_RPC_REQUEST: ${JSON.stringify(neoRequest)}`);
log(`NEOSTATION_RPC_PROCESS: pid=${neoPid} attach=${neoAttachResponse}`);
log(`NEOSTATION_RPC_THREAD: ${neoTid || '<missing>'}`);

try {
    if (!neoTid) throw new Error('Could not determine a stopped RPCS3 thread');

    const fingerprint = findFingerprintCore();
    if (!fingerprint) {
        log('NEOSTATION_RPC_CORE_NOT_READY: libRPCS3Core.dylib is not loaded');
        throw new Error('RPCS3 core is not initialized; press Start first');
    }

    const { core, functions, uuid } = fingerprint;
    const moduleBase = parseRemoteAddress(core.load_address);
    const bootAddress = moduleBase + BigInt(functions.boot);
    log(`NEOSTATION_RPC_CORE_UUID: ${uuid}`);
    log(`NEOSTATION_RPC_MODULE_BASE: 0x${moduleBase.toString(16)}`);
    log(`NEOSTATION_RPC_BOOT_ADDRESS: 0x${bootAddress.toString(16)}`);

    const stateBefore = functions.state !== undefined
        ? remoteCallNoArg(moduleBase + BigInt(functions.state), neoTid, 'state-before')
        : null;
    const progressBefore = functions.progress !== undefined
        ? remoteCallNoArg(moduleBase + BigInt(functions.progress), neoTid, 'progress-before')
        : null;
    log(`NEOSTATION_RPC_STATE_BEFORE: ${formatResult(stateBefore)}`);
    log(`NEOSTATION_RPC_PROGRESS_BEFORE: ${formatResult(progressBefore)}`);

    const boot = remoteCallBoot(
        bootAddress,
        neoTid,
        String(neoRequest.titleId || ''),
    );
    log(`NEOSTATION_RPC_TITLE_POINTER: ${boot.argumentPointer}`);
    log(`NEOSTATION_RPC_BOOT_RESULT: signed=${boot.signed32} raw=${boot.rawHex} stop=${boot.stop}`);

    const stateAfter = functions.state !== undefined
        ? remoteCallNoArg(moduleBase + BigInt(functions.state), neoTid, 'state-after')
        : null;
    const progressAfter = functions.progress !== undefined
        ? remoteCallNoArg(moduleBase + BigInt(functions.progress), neoTid, 'progress-after')
        : null;
    log(`NEOSTATION_RPC_STATE_AFTER: ${formatResult(stateAfter)}`);
    log(`NEOSTATION_RPC_PROGRESS_AFTER: ${formatResult(progressAfter)}`);
    log(`NEOSTATION_RPC_BOOT_INTERPRETATION: ${interpretBootCode(boot.signed32)}`);
} catch (error) {
    log(`NEOSTATION_RPC_DIRECT_ERROR: ${error && error.stack ? error.stack : error}`);
} finally {
    const detach = send_command('D');
    log(`NEOSTATION_RPC_DETACH: ${detach}`);
}

function findFingerprintCore() {
    const command = 'jGetLoadedDynamicLibrariesInfos:{"fetch_all_solibs":true,"information-level":"address-name-uuid"}';
    const rawLibraries = send_command(command);
    const jsonStart = rawLibraries ? rawLibraries.indexOf('{') : -1;
    if (jsonStart < 0) throw new Error(`No loaded-image JSON: ${rawLibraries}`);

    const payload = JSON.parse(rawLibraries.substring(jsonStart));
    const images = Array.isArray(payload.images) ? payload.images : [];
    const core = images.find((image) =>
        String(image.pathname || '').includes('libRPCS3Core.dylib'));
    if (!core) return null;

    const uuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const functions = neoSupportedFunctions[uuid];
    if (!functions || functions.boot === undefined) {
        throw new Error(
            `Unsupported RPCS3 core UUID: ${uuid}; supported=${Object.keys(neoSupportedFunctions).join(',')}`);
    }
    return { core, functions, uuid };
}

function remoteCallBoot(address, tid, titleId) {
    if (!titleId) throw new Error('NeoStation passed an empty Title ID');
    const call = beginRemoteCall(tid, 0x4000n);
    try {
        const titleBytes = asciiToHex(titleId + '\0');
        const write = send_command(
            `M${call.scratch.toString(16)},${(titleBytes.length / 2).toString(16)}:${titleBytes}`);
        if (write !== 'OK') throw new Error(`Could not write Title ID: ${write}`);
        log(`NEOSTATION_RPC_TITLE_ID: ${titleId}`);
        log(`NEOSTATION_RPC_SOURCE_PATH: ${String(neoRequest.sourcePath || '')}`);

        writeRegister(tid, '0', call.scratch);
        writeRegister(tid, '1e', call.trap);
        writeRegister(tid, '20', address);
        const stop = send_command(`vCont;c:${tid}`);
        const raw = readX0(stop, tid);
        return {
            signed32: Number(BigInt.asIntN(32, raw)),
            rawHex: `0x${raw.toString(16)}`,
            argumentPointer: `0x${call.scratch.toString(16)}`,
            stop,
        };
    } finally {
        endRemoteCall(call, tid);
    }
}

function remoteCallNoArg(address, tid, label) {
    const call = beginRemoteCall(tid, 0x2000n);
    try {
        writeRegister(tid, '1e', call.trap);
        writeRegister(tid, '20', address);
        const stop = send_command(`vCont;c:${tid}`);
        const raw = readX0(stop, tid);
        return {
            label,
            signed32: Number(BigInt.asIntN(32, raw)),
            rawHex: `0x${raw.toString(16)}`,
            stop,
        };
    } finally {
        endRemoteCall(call, tid);
    }
}

function beginRemoteCall(tid, size) {
    const saved = send_command(`QSaveRegisterState;thread:${tid};`);
    if (!saved || !/^[0-9]+$/.test(saved)) {
        throw new Error(`Could not save registers: ${saved}`);
    }
    let allocation = send_command(`_M${size.toString(16)},rwx`);
    if (!allocation || allocation.startsWith('E')) {
        allocation = send_command(`_M${size.toString(16)},rw`);
    }
    if (!allocation || allocation.startsWith('E')) {
        throw new Error(`Could not allocate remote scratch memory: ${allocation}`);
    }
    const scratch = BigInt(`0x${allocation}`);
    const prepared = prepare_memory_region(scratch, size);
    const trap = scratch + 0x100n;
    const trapWrite = send_command(
        `M${trap.toString(16)},4:${neoReturnTrapInstruction}`);
    if (trapWrite !== 'OK') throw new Error(`Could not write return trap: ${trapWrite}`);
    log(`NEOSTATION_RPC_REMOTE_CALL: save=${saved} scratch=0x${scratch.toString(16)} prepare=${prepared}`);
    return { saved, scratch, trap };
}

function endRemoteCall(call, tid) {
    const restore = send_command(
        `QRestoreRegisterState:${call.saved};thread:${tid};`);
    log(`NEOSTATION_RPC_REGISTER_RESTORE: ${restore}`);
    send_command(`_m${call.scratch.toString(16)}`);
    if (restore !== 'OK') throw new Error(`Could not restore registers: ${restore}`);
}

function writeRegister(tid, register, value) {
    const response = send_command(
        `P${register}=${numberToLittleEndianHexString(value)};thread:${tid};`);
    if (response !== 'OK') {
        throw new Error(`Register ${register} write failed: ${response}`);
    }
}

function readX0(stopResponse, tid) {
    const match = /00:(?<reg>[0-9a-fA-F]{16});/.exec(stopResponse || '');
    if (match) return littleEndianHexStringToNumber(match.groups.reg);
    const direct = send_command(`p0;thread:${tid}`);
    if (!direct || direct.startsWith('E')) {
        throw new Error(`Could not read x0: stop=${stopResponse} p0=${direct}`);
    }
    return littleEndianHexStringToNumber(direct.substring(0, 16));
}

function resolveStoppedThread(response) {
    const direct = /thread:(?<tid>[0-9a-fA-F]+);/.exec(response || '');
    if (direct) return direct.groups.tid;
    const threadList = send_command('qfThreadInfo');
    const list = /^m(?<ids>[0-9a-fA-F,]+)/.exec(threadList || '');
    return list ? list.groups.ids.split(',')[0] : null;
}

function interpretBootCode(code) {
    switch (code) {
        case 0: return 'success';
        case 1: return 'invalid-title-id';
        case 2: return 'core-or-context-not-ready';
        case 10: return 'internal-boot-failure';
        case 14: return 'title-not-found-in-active-library';
        default: return `unknown-return-code-${code}`;
    }
}

function formatResult(result) {
    if (result === null) return '<function unavailable for this fingerprint>';
    return `signed=${result.signed32} raw=${result.rawHex}`;
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
        const code = text.charCodeAt(index);
        if (code > 0x7f) throw new Error('Title ID contains non-ASCII data');
        result += code.toString(16).padStart(2, '0');
    }
    return result;
}

function littleEndianHexStringToNumber(hex) {
    const clean = String(hex).replace(/[^0-9a-fA-F]/g, '').substring(0, 16);
    const bytes = [];
    for (let index = 0; index < clean.length; index += 2) {
        bytes.push(parseInt(clean.substring(index, index + 2), 16));
    }
    let result = 0n;
    for (let index = bytes.length - 1; index >= 0; index--) {
        result = (result << 8n) | BigInt(bytes[index]);
    }
    return result;
}

function numberToLittleEndianHexString(value) {
    let current = BigInt(value);
    const bytes = [];
    for (let index = 0; index < 8; index++) {
        bytes.push(Number(current & 0xffn));
        current >>= 8n;
    }
    return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
'''
write('assets/data/rpcs3_stikdebug_launch.js', rpcs3_script)


# Pass title and source diagnostics from the selected GameModel.
game_launch_path = 'lib/services/game/game_launch_service.dart'
game_launch = read(game_launch_path)
old_call = 'final launched = await Rpcs3LaunchService.launchTitle(titleId);'
new_call = '''final sourceUri = Uri.tryParse(game.romPath ?? '');
          final launched = await Rpcs3LaunchService.launchTitle(
            titleId,
            displayTitle: game.name,
            sourcePath:
                sourceUri?.queryParameters['source-path'] ?? game.romPath ?? '',
            sourceKind: sourceUri?.queryParameters['source-kind'] ?? 'rpcs3',
          );'''
if old_call in game_launch:
    game_launch = game_launch.replace(old_call, new_call, 1)
write(game_launch_path, game_launch)


# Add a second-pass method that opens only StikDebug/script while NeoStation is
# foregrounded. It deliberately does not schedule another target-app relaunch.
external_dart_path = 'packages/external_folder_access/lib/external_folder_access.dart'
external_dart = read(external_dart_path)
if 'openJitScriptOnly({' not in external_dart:
    marker = '  /// Registers a callback for URLs opened while the app is running'
    method = r'''  /// Opens StikDebug with a custom script and does not schedule a later
  /// target-app launch. Used for RPCS3's already-running second pass so the
  /// active core/session is not replaced by its Start page.
  static Future<bool?> openJitScriptOnly({
    required String targetBaseBundleId,
    required String scriptName,
    required String scriptDataBase64Url,
    String debugFileName = 'jit_script_only_debug.txt',
  }) async {
    if (!Platform.isIOS) return null;
    try {
      return await _channel.invokeMethod<bool>('openUrlAfterJitPreflight', {
        'launchUrl': 'about:blank',
        'openTargetApp': false,
        'launchAfterPreflight': false,
        'targetBaseBundleId': targetBaseBundleId,
        'delayMs': 0,
        'scriptName': scriptName,
        'scriptData': scriptDataBase64Url,
        'debugFileName': debugFileName,
      });
    } on PlatformException {
      return false;
    }
  }

'''
    if marker not in external_dart:
        raise SystemExit('ExternalFolderAccess insertion marker missing')
    external_dart = external_dart.replace(marker, method + marker, 1)
write(external_dart_path, external_dart)

external_swift_path = (
    'packages/external_folder_access/ios/Classes/'
    'ExternalFolderAccessPlugin.swift'
)
external_swift = read(external_swift_path)
if 'launchAfterPreflight' not in external_swift:
    marker = '        let openTargetApp = (args["openTargetApp"] as? Bool) ?? false'
    if marker not in external_swift:
        raise SystemExit('Swift openTargetApp marker missing')
    external_swift = external_swift.replace(
        marker,
        marker
        + '\n        let launchAfterPreflight = '
        + '(args["launchAfterPreflight"] as? Bool) ?? true',
        1,
    )

    background_marker = (
        '        delayedRetryBackgroundTask = '
        'UIApplication.shared.beginBackgroundTask('
    )
    if background_marker not in external_swift:
        raise SystemExit('Swift delayed background marker missing')
    direct_branch = r'''        if !launchAfterPreflight {
            UIApplication.shared.open(preflightURL, options: [:]) { success in
                self.appendJitDebug(
                    fileName: debugFileName,
                    text: "\nSTATE: PREFLIGHT_ONLY_RESULT\nSuccess: \(success)\n"
                )
                result(success)
            }
            return
        }

'''
    external_swift = external_swift.replace(
        background_marker,
        direct_branch + background_marker,
        1,
    )
write(external_swift_path, external_swift)


# ---------------------------------------------------------------------------
# 4. Video preview lifecycle: generation cancellation + serialized teardown
# ---------------------------------------------------------------------------
video_path = 'lib/screens/game_screen/my_games_list.dart'
insert_import(video_path, "import 'package:neostation/services/audio_policy_service.dart';")
video = read(video_path)

controller_field = re.search(
    r'^\s*VideoPlayerController\?\s+_videoController\s*;',
    video,
    flags=re.MULTILINE,
)
if not controller_field:
    raise SystemExit('Primary video controller field missing')
if '_videoGeneration' not in video:
    insertion = controller_field.group(0) + r'''
  int _videoGeneration = 0;
  Future<void> _videoTransition = Future<void>.value();
  VoidCallback? _videoPolicyUnregister;'''
    video = video[:controller_field.start()] + insertion + video[controller_field.end():]

# Resolve the current initializer signature and preserve its parameter name.
init_match = re.search(
    r'^\s*Future<void>\s+_initializeVideo\(([^)]*)\)\s*async\s*\{',
    video,
    flags=re.MULTILINE,
)
if not init_match:
    raise SystemExit('Primary _initializeVideo function missing')
params = init_match.group(1).strip()
name_match = re.search(r'([A-Za-z_]\w*)\s*(?:,|$)', params)
if not name_match:
    raise SystemExit('Could not determine video path parameter')
video_var = name_match.group(1)
brace = video.find('{', init_match.start())
init_end = find_block_end(video, brace)

muted_expr = 'false'
for candidate in ('_isVideoMuted', '_isMuted', '_videoMuted'):
    if re.search(rf'\b{re.escape(candidate)}\b', video):
        muted_expr = candidate
        break
volume_expr = f'({muted_expr} ? 0.0 : 1.0)' if muted_expr != 'false' else '1.0'

new_initializer = f'''  Future<void> _initializeVideo({params}) async {{
    final requestedGeneration = ++_videoGeneration;
    _videoTimer?.cancel();
    _videoPolicyUnregister ??= AudioPolicyService().registerClient(
      this,
      (snapshot) async {{
        final controller = _videoController;
        if (controller == null || !controller.value.isInitialized) return;
        await controller.setVolume(
          snapshot.effectiveVolume({volume_expr}),
        );
      }},
    );

    // Serialize teardown/startup so two AVPlayers never own audio output at
    // the same time. Every late async completion checks the selection token.
    final completion = Completer<void>();
    _videoTransition = _videoTransition.catchError((_) {{}}).then((_) async {{
      final previous = _videoController;
      _videoController = null;
      if (mounted && requestedGeneration == _videoGeneration) {{
        setState(() => _isVideoLoading = true);
      }}
      await _disposePreviewVideoController(previous);
      if (!mounted || requestedGeneration != _videoGeneration) return;

      final controller = VideoPlayerController.file(
        File({video_var}),
        videoPlayerOptions: VideoPlayerOptions(mixWithOthers: true),
      );
      try {{
        await controller.setVolume(0.0);
        await controller.initialize();
        if (!mounted || requestedGeneration != _videoGeneration) {{
          await _disposePreviewVideoController(controller);
          return;
        }}

        await controller.setLooping(true);
        await AudioPolicyService().enforceSilentSwitchPolicy(
          reason: 'preview-video-initialized',
        );
        if (!mounted || requestedGeneration != _videoGeneration) {{
          await _disposePreviewVideoController(controller);
          return;
        }}

        _videoController = controller;
        await controller.play();
        // AVPlayer can activate its own session during play(). Reassert the
        // centralized ambient policy after the player is actually running.
        await AudioPolicyService().enforceSilentSwitchPolicy(
          reason: 'preview-video-playing',
        );
        if (!mounted || requestedGeneration != _videoGeneration) {{
          if (identical(_videoController, controller)) _videoController = null;
          await _disposePreviewVideoController(controller);
          return;
        }}

        if (mounted) setState(() => _isVideoLoading = false);
        await _fadePreviewVideoAudio(
          controller,
          requestedGeneration,
          targetVolume: {volume_expr},
        );
      }} catch (error) {{
        if (identical(_videoController, controller)) _videoController = null;
        await _disposePreviewVideoController(controller);
        if (mounted && requestedGeneration == _videoGeneration) {{
          setState(() => _isVideoLoading = false);
        }}
        debugPrint('Video preview initialization failed: $error');
      }}
    }}).whenComplete(() {{
      if (!completion.isCompleted) completion.complete();
    }});
    await completion.future;
  }}'''
video = video[:init_match.start()] + new_initializer + video[init_end:]

helpers_marker = re.search(
    r'^\s*@override\s*\n\s*void dispose\(\)\s*\{',
    video,
    flags=re.MULTILINE,
)
if not helpers_marker:
    raise SystemExit('Primary video state dispose missing')
if '_disposePreviewVideoController(' not in video[init_match.start() + len(new_initializer):helpers_marker.start()]:
    helpers = r'''
  Future<void> _disposePreviewVideoController(
    VideoPlayerController? controller,
  ) async {
    if (controller == null) return;
    try {
      await controller.setVolume(0.0);
    } catch (_) {}
    try {
      await controller.pause();
    } catch (_) {}
    try {
      await controller.dispose();
    } catch (_) {}
  }

  Future<void> _fadePreviewVideoAudio(
    VideoPlayerController controller,
    int generation, {
    required double targetVolume,
  }) async {
    final policy = AudioPolicyService();
    final effectiveTarget = policy.effectiveVolume(targetVolume);
    if (effectiveTarget <= 0.0) {
      await controller.setVolume(0.0);
      return;
    }

    // Readiness is established by initialize()/generation checks above. This
    // 96 ms ramp only removes the first-buffer click; it is not a load delay.
    const steps = 4;
    for (var step = 1; step <= steps; step++) {
      if (!mounted ||
          generation != _videoGeneration ||
          !identical(_videoController, controller)) {
        return;
      }
      await controller.setVolume(effectiveTarget * step / steps);
      if (step != steps) {
        await Future<void>.delayed(const Duration(milliseconds: 24));
      }
    }
  }

'''
    video = video[:helpers_marker.start()] + helpers + video[helpers_marker.start():]

# Remove fixed debounce timers around _initializeVideo; generation cancellation
# makes stale initialization harmless and teardown starts immediately.
video = re.sub(
    r'''_videoTimer\s*=\s*Timer\(\s*const Duration\(milliseconds:\s*\d+\),\s*\(\)\s*(?:async\s*)?\{\s*(?:await\s+)?_initializeVideo\(([^;]+)\);\s*\}\s*\);''',
    r'unawaited(_initializeVideo(\1));',
    video,
    flags=re.DOTALL,
)
video = re.sub(
    r'''_videoTimer\s*=\s*Timer\(\s*const Duration\(milliseconds:\s*\d+\),\s*\(\)\s*=>\s*_initializeVideo\(([^)]+)\)\s*\);''',
    r'unawaited(_initializeVideo(\1));',
    video,
    flags=re.DOTALL,
)

# Ensure state disposal invalidates all async completions and mutes immediately.
dispose_match = re.search(
    r'^\s*@override\s*\n\s*void dispose\(\)\s*\{',
    video,
    flags=re.MULTILINE,
)
if dispose_match:
    body_brace = video.find('{', dispose_match.start())
    body_end = find_block_end(video, body_brace)
    body = video[dispose_match.start():body_end]
    if '_videoGeneration++;' not in body:
        body = body.replace(
            '{',
            '''{
    _videoGeneration++;
    _videoTimer?.cancel();
    _videoPolicyUnregister?.call();
    _videoPolicyUnregister = null;
    final controllerToDispose = _videoController;
    _videoController = null;
    unawaited(_disposePreviewVideoController(controllerToDispose));''',
            1,
        )
        # Remove duplicate non-awaited disposal of the same field in this body.
        body = re.sub(
            r'\n\s*_videoController\?\.(?:pause|dispose)\(\);',
            '',
            body,
        )
        video = video[:dispose_match.start()] + body + video[body_end:]
write(video_path, video)


# Secondary display must never create a second audible preview pipeline.
secondary_path = 'lib/screens/game_screen/my_games_list/secondary_display.dart'
if (ROOT / secondary_path).exists():
    secondary = read(secondary_path)
    if 'VideoPlayerController' in secondary:
        insert_import(
            secondary_path,
            "import 'package:neostation/services/audio_policy_service.dart';",
        )
        secondary = read(secondary_path)
        secondary = re.sub(
            r'(await\s+([A-Za-z_]\w*)\.initialize\(\);)',
            r'await \2.setVolume(0.0);\n        \1\n        await AudioPolicyService().enforceSilentSwitchPolicy(\n          reason: \'secondary-preview-initialized\',\n        );',
            secondary,
            count=1,
        )
        write(secondary_path, secondary)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
audio_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/audio_policy_service.dart';

void main() {
  test('central policy gates every configured volume', () async {
    final policy = AudioPolicyService();
    await policy.init();
    expect(policy.effectiveVolume(0.75), 0.75);
    await policy.setApplicationAudioEnabled(false, reason: 'test');
    expect(policy.effectiveVolume(0.75), 0.0);
    await policy.setApplicationAudioEnabled(true, reason: 'test');
    expect(policy.effectiveVolume(0.75), 0.75);
  });

  test('all NeoStation audio producers consume the central policy', () {
    for (final path in <String>[
      'lib/services/sfx_service.dart',
      'lib/services/home_music_service.dart',
      'lib/services/music_player_service.dart',
      'lib/screens/game_screen/my_games_list.dart',
    ]) {
      final source = File(path).readAsStringSync();
      expect(source, contains('AudioPolicyService'));
    }
    final sfx = File('lib/services/sfx_service.dart').readAsStringSync();
    expect(sfx, contains('_activeHandles'));
    expect(sfx, contains('_stopActiveHandles'));
  });
}
'''
write('test/audio_policy_service_test.dart', audio_test)

video_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('preview video lifecycle cancels stale selections and awaits teardown', () {
    final source = File(
      'lib/screens/game_screen/my_games_list.dart',
    ).readAsStringSync();
    expect(source, contains('_videoGeneration'));
    expect(source, contains('_videoTransition'));
    expect(source, contains('await controller.dispose()'));
    expect(source, contains('requestedGeneration != _videoGeneration'));
    expect(source, contains('await controller.setVolume(0.0)'));
    expect(source, contains("reason: 'preview-video-playing'"));
    expect(source, isNot(contains('Duration(milliseconds: 1500)'));
  });
}
'''
write('test/video_preview_lifecycle_test.dart', video_test)

name_test = r'''import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';

void main() {
  test('legacy RPCS3 serial metadata yields to PARAM.SFO title', () {
    final game = GameModel.fromDatabaseModel(
      DatabaseGameModel(
        appSystemId: 'ps3',
        filename: 'BLES00412',
        romPath: 'rpcs3-library://game?title-id=BLES00412',
        titleId: 'BLES00412',
        titleName: 'The Lord of the Rings: Conquest™',
        realName: 'BLES00412',
        screenscraperRealName: 'BLES00412.rpcs3',
      ),
    );
    expect(game.name, 'The Lord of the Rings: Conquest™');
    expect(game.realname, 'The Lord of the Rings: Conquest™');
  });
}
'''
write('test/rpcs3_existing_metadata_repair_test.dart', name_test)

launch_test = r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';

void main() {
  test('RPCS3 direct script records state and reads the real boot return', () {
    final template = File(
      'assets/data/rpcs3_stikdebug_launch.js',
    ).readAsStringSync();
    final script = Rpcs3LaunchService.buildScriptForTesting(
      template,
      'BLES00412',
      displayTitle: 'The Lord of the Rings: Conquest™',
      sourcePath: '/Data/games/discImgs/BLES00412',
      sourceKind: 'disc-image',
    );
    expect(script, contains('NEOSTATION_RPC_MODULE_BASE'));
    expect(script, contains('NEOSTATION_RPC_BOOT_ADDRESS'));
    expect(script, contains('NEOSTATION_RPC_STATE_BEFORE'));
    expect(script, contains('NEOSTATION_RPC_BOOT_RESULT'));
    expect(script, contains('BigInt.asIntN(32'));
    expect(script, contains('5C4D64FFB79930AD879C13009838F136'));
    expect(script, isNot(contains('__NEOSTATION_')));
  });

  test('second pass does not schedule another target-app relaunch', () {
    final dart = File(
      'lib/services/rpcs3_launch_service.dart',
    ).readAsStringSync();
    expect(dart, contains('openJitScriptOnly'));
    final native = File(
      'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift',
    ).readAsStringSync();
    expect(native, contains('launchAfterPreflight'));
    expect(native, contains('PREFLIGHT_ONLY_RESULT'));
  });
}
'''
write('test/rpcs3_launch_protocol_test.dart', launch_test)

print('NeoStation Stage 7 patch applied.')
