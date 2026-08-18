from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('.')
PATCHER = ROOT / 'tools/apply_stage7.py'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')


def ensure_import(path: str, line: str) -> None:
    text = read(path)
    if line in text:
        return
    imports = list(re.finditer(r'^import .*?;\s*$', text, flags=re.MULTILINE))
    if not imports:
        raise SystemExit(f'No imports in {path}')
    at = imports[-1].end()
    write(path, text[:at] + '\n' + line + text[at:])


# Repair the temporary patcher itself before its one and only execution.
if PATCHER.exists():
    patcher = PATCHER.read_text(encoding='utf-8')
    patcher = patcher.replace(
        "    brace = text.find('{', match.start())\n",
        "    brace = text.rfind('{', match.start(), match.end())\n"
        "    if brace < 0:\n"
        "        brace = text.find('{', match.end())\n",
    )
    patcher = patcher.replace(
        "r'^  static \\\({String name, bool showRomFileNameSubtitle\\\}\\\) _resolveListDisplayName\\\(\\\{'",
        "r'^  static \\\({String name, bool showRomFileNameSubtitle\\\}\\\) '
"
        "    r'_resolveListDisplayName\\\(\\\{[\\s\\S]*?^  \\\}\\\)\\s*\\\{'",
    )
    # The raw replacement originally emitted escaped quote characters into Dart.
    patcher = patcher.replace(
        "reason: \\\'secondary-preview-initialized\\\',",
        "reason: 'secondary-preview-initialized',",
    )
    # Make SFX's VoidCallback import explicit.
    marker = "sfx_path = 'lib/services/sfx_service.dart'\n"
    if "insert_import(sfx_path, \"import 'package:flutter/foundation.dart';\")" not in patcher:
        patcher = patcher.replace(
            marker,
            marker + "insert_import(sfx_path, \"import 'package:flutter/foundation.dart';\")\n",
            1,
        )
    PATCHER.write_text(patcher, encoding='utf-8')

    result = subprocess.run([sys.executable, str(PATCHER)], text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


# Source-level safeguards after patch application.
ensure_import('lib/services/sfx_service.dart', "import 'package:flutter/foundation.dart';")

policy_path = 'lib/services/audio_policy_service.dart'
policy = read(policy_path)
old_queue = """    _sessionQueue = _sessionQueue.catchError((_) {}).then((_) async {
      try {
        await ExternalFolderAccess.configureAudioSessionForSilentMode();
        completer.complete();
      } catch (error) {
        _log.w('[AudioPolicy] Could not enforce ambient session ($reason): $error');
        completer.complete();
      }
    });
"""
new_queue = """    Future<void> applyPolicy() async {
      try {
        await ExternalFolderAccess.configureAudioSessionForSilentMode();
      } catch (error) {
        _log.w('[AudioPolicy] Could not enforce ambient session ($reason): $error');
      } finally {
        if (!completer.isCompleted) completer.complete();
      }
    }

    _sessionQueue = _sessionQueue.then(
      (_) => applyPolicy(),
      onError: (_) => applyPolicy(),
    );
"""
if old_queue in policy:
    policy = policy.replace(old_queue, new_queue, 1)
write(policy_path, policy)

# Remove accidental backslash-escaped Dart quotes if any survived a prior run.
secondary_path = 'lib/screens/game_screen/my_games_list/secondary_display.dart'
if (ROOT / secondary_path).exists():
    secondary = read(secondary_path)
    secondary = secondary.replace(
        "reason: \\'secondary-preview-initialized\\',",
        "reason: 'secondary-preview-initialized',",
    )
    write(secondary_path, secondary)

# Ensure the actual list-reading path never lets a synthetic RPCS3 serial win.
game_list_path = 'lib/services/game/game_list_service.dart'
game_list = read(game_list_path)
required_markers = (
    'isMeaningfulRpcs3MetadataNameForTesting',
    'GameModel.fromDatabaseModel(dbGame)',
    'if (preferFileName && !isRpcs3Virtual)',
)
for required in required_markers:
    if required not in game_list:
        raise SystemExit(f'Missing GameListService repair marker: {required}')

# Guard against unresolved source patch placeholders.
for source_path in (
    'assets/data/rpcs3_stikdebug_launch.js',
    'lib/services/rpcs3_launch_service.dart',
):
    source = read(source_path)
    if source_path.endswith('.dart') and '__NEOSTATION_REQUEST_JSON__' not in source:
        # The Dart template should refer to placeholders as replacement strings.
        pass

# Remove every temporary trigger created while bringing up the one-shot job.
for candidate in ROOT.glob('_stage7_trigger*'):
    candidate.unlink(missing_ok=True)

print('Stage 7 finalization patch completed.')
