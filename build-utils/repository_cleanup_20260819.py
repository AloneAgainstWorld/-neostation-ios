from pathlib import Path
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def remove_between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        raise RuntimeError(f"missing start marker: {start}")
    j = text.find(end, i)
    if j < 0:
        raise RuntimeError(f"missing end marker: {end}")
    return text[:i] + text[j:]


# Remove the temporary on-device FileProvider diagnostic.
path = "lib/main.dart"
text = read(path)
text = remove_between(
    text,
    "  // TEMPORARY iOS DIAGNOSTIC",
    "  // Inicializar localizacion con idioma persistido",
)
write(path, text)

# Make the RPCS3 settings card reflect the actual stable behavior.
path = "lib/screens/settings_screen/new_settings_options/directories_settings_content.dart"
text = read(path)
text = remove_between(
    text,
    "  Future<void> _configureRpcs3Launch() async {",
    "  Future<void> _linkRpcs3DataFolder() async {",
)
section_start = text.index("  Widget _buildIOSRpcs3Section(")
section_end = text.index("  /// ARMSX2", section_start)
section = text[section_start:section_end]
old_start = section.index("      trailingAction: Row(")
old_end_marker = "      ),\n    );\n  }\n\n"
section.rindex(old_end_marker)  # Validate the expected source shape.
replacement = """      trailingAction: SizedBox(
        height: 32,
        child: OutlinedButton.icon(
          onPressed: _linkingFolderKey == null ? _syncWithRpcs3 : null,
          icon: const Icon(Symbols.sync_rounded, size: 16),
          label: Text(Rpcs3LibraryLocale.sync(context)),
        ),
      ),
    );
  }

"""
section = section[:old_start] + replacement
text = text[:section_start] + section + text[section_end:]
write(path, text)

# Remove the retired RPCS3 Shortcut compatibility surface while keeping the
# active MeloNX and ARMSX2 Shortcut flows intact.
path = "lib/services/ios_shortcut_jit_launch_service.dart"
text = read(path)
text = remove_between(
    text,
    "  /// Historical RPCS3 helper name retained",
    "  /// One-time installer for the exact NeoStation MeloNX launch Shortcut.",
)
text = remove_between(
    text,
    "  /// RPCS3 intentionally has no shared iCloud installer.",
    "  static bool get hasMeloNXShortcutInstaller",
)
text = re.sub(
    r"\n  static bool get hasRpcs3ShortcutInstaller =>\n      _rpcs3ShortcutInstallUrl\.startsWith\('https://www\.icloud\.com/shortcuts/'\);\n",
    "\n",
    text,
)
text = remove_between(
    text,
    "  /// Opens the historical RPCS3 Shortcut setup entry point.",
    "  /// Builds the canonical Shortcuts URL used by NeoStation to invoke an",
)
if "rpcs3Shortcut" in text or "RPCS3+Start" in text:
    raise RuntimeError("RPCS3 Shortcut residue remains in shortcut service")
write(path, text)

# Simplify RPCS3 launch comments to the current contract only.
write(
    "lib/services/rpcs3_launch_service.dart",
    """import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/logger_service.dart';

/// Stable RPCS3 iOS launcher.
///
/// NeoStation requests StikDebug Universal JIT for RPCS3, then leaves RPCS3
/// responsible for its native Start/Commencer screen and game selection.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';

  static final LoggerService _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  /// Compatibility hook used by application startup.
  static Future<void> initialize() async {}

  /// Opens StikDebug with its Universal JIT request for RPCS3.
  ///
  /// [displayTitle], [sourcePath], and [sourceKind] are retained for diagnostics
  /// and compatibility with existing callers. RPCS3 performs game selection.
  static Future<bool> launchTitle(
    String? rawTitleId, {
    String? displayTitle,
    String? sourcePath,
    String? sourceKind,
  }) async {
    if (!Platform.isIOS) return false;

    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null) return false;

    _log.i(
      'RPCS3 standard launch: titleId=$titleId '
      'title=${displayTitle?.trim() ?? ''} '
      'sourceKind=${sourceKind?.trim() ?? ''} '
      'sourcePath=${sourcePath?.trim() ?? ''}',
    );

    try {
      final opened = await ExternalFolderAccess.openJitRequest(
        targetBaseBundleId: targetBundleId,
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      return opened == true;
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: standard JIT handoff failed for $titleId',
        error: error,
        stackTrace: stack,
      );
      return false;
    }
  }
}
""",
)

# Remove dead RPCS3 library helpers reported by the analyzer.
path = "lib/services/rpcs3_library_service.dart"
text = read(path)
text = remove_between(
    text,
    "  static Future<Map<String, String>> _parseGamesYml(File file) async {",
    "  @visibleForTesting\n  static Map<String, String> parseGamesYmlTextForTesting",
)
text = remove_between(
    text,
    "  static Future<String?> _resolveRegisteredPath(",
    "  static Future<String?> _findEntityByBasename(",
)
write(path, text)

# Remove unused delayed/two-pass JIT APIs left by the RPCS3 trials.
path = "packages/external_folder_access/lib/external_folder_access.dart"
text = read(path)
text = text.replace(
    "  /// foregrounded. Unlike the legacy preflight helper, this method schedules no\n"
    "  /// UIApplication work after NeoStation is backgrounded.\n",
    "  /// foregrounded. It schedules no UIApplication work after NeoStation is\n"
    "  /// backgrounded.\n",
)
text = remove_between(
    text,
    "  /// Opens [url] immediately, then asks the native iOS layer to open the same",
    "  /// Registers a callback for URLs opened while the app is running",
)
write(path, text)

path = "packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift"
text = read(path)
text = remove_between(
    text,
    "    /// State for the one in-flight delayed launch retry.",
    "    /// Bookmarks are stored per-emulator",
)
for block in (
    '        case "openUrlWithDelayedRetry":\n            openUrlWithDelayedRetry(call: call, result: result)\n',
    '        case "openUrlAfterJitPreflight":\n            openUrlAfterJitPreflight(call: call, result: result)\n',
    '        case "openAppWithTwoPassJit":\n            openAppWithTwoPassJit(call: call, result: result)\n',
):
    if block not in text:
        raise RuntimeError(f"missing native switch block: {block!r}")
    text = text.replace(block, "")
text = remove_between(
    text,
    "    // MARK: - Delayed direct-launch retry",
    "    // MARK: - Immediate StikDebug request",
)
text = remove_between(
    text,
    "    // MARK: - Explicit StikDebug JIT preflight",
    "    /// Returns the suffix SideStore/AltStore appended to NeoStation",
)
text = remove_between(
    text,
    "    private func cancelDelayedRetry(reason: String) {",
    "    private static func safeDebugFileName(_ value: String) -> String {",
)
for token in (
    "openUrlWithDelayedRetry",
    "openUrlAfterJitPreflight",
    "openAppWithTwoPassJit",
    "twoPassWorkItem",
    "delayedRetryWorkItem",
):
    if token in text:
        raise RuntimeError(f"native experimental residue remains: {token}")
write(path, text)

# Keep current RPCS3 metadata/launch regression coverage and remove tests that
# existed only for the retired Shortcut experiment.
write(
    "test/rpcs3_stage7_test.dart",
    """import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';

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

  test('RPCS3 launch uses the basic Universal JIT handoff', () {
    final service = File(
      'lib/services/rpcs3_launch_service.dart',
    ).readAsStringSync();
    expect(service, contains('openJitRequest'));
    expect(service, contains("scriptName: 'universal.js'"));
    expect(service, contains('rpcs3_launch_debug.txt'));
  });
}
""",
)

# Remove historical experiment text from user-facing documentation.
path = "README.md"
text = read(path)
text = re.sub(
    r"\nThe previously tested `NeoStation\+RPCS3\+Start` Shortcut / Switch Control automation.*?standard RPCS3 integration\.\n",
    "",
    text,
)
text = re.sub(
    r"\nSee \[`docs/RPCS3_SHORTCUT_SWITCH_CONTROL\.md`\]\([^\n]+\) for the current status and historical automation notes\.\n",
    "",
    text,
)
write(path, text)

# Update one stale localization comment.
path = "lib/l10n/rpcs3_library_locale.dart"
text = read(path).replace(
    "Localized copy for the experimental RPCS3 iOS library integration.",
    "Localized copy for the RPCS3 iOS library integration.",
)
write(path, text)

# Remove direct dependencies that have no source/test import and are not
# build-tool/config dependencies.
path = "pubspec.yaml"
text = read(path)
for dependency_line in (
    "  widget_mask: ^1.0.0\n",
    "  flutter_tilt: ^4.1.0\n",
    "  mocktail: ^1.0.5\n",
):
    if dependency_line not in text:
        raise RuntimeError(f"missing expected dependency: {dependency_line.strip()}")
    text = text.replace(dependency_line, "")
write(path, text)

# Remove obsolete build/doc/trigger artifacts.
for obsolete in (
    "build-utils/remove_rpcs3_shortcut_ui.py",
    "docs/RPCS3_SHORTCUT_SWITCH_CONTROL.md",
    ".audit-trigger-main",
    ".cleanup-trigger",
):
    p = Path(obsolete)
    if p.exists():
        p.unlink()

# CodeMagic no longer needs to patch source at build time.
path = "codemagic.yaml"
text = read(path)
text = re.sub(
    r"\n      - name: Remove retired RPCS3 Shortcut UI\n        script: \|\n          python3 build-utils/remove_rpcs3_shortcut_ui\.py\n",
    "\n",
    text,
)
if "remove_rpcs3_shortcut_ui.py" in text:
    raise RuntimeError("CodeMagic still references RPCS3 UI patcher")
write(path, text)

# This script is deliberately one-shot and must not remain in the cleaned tree.
Path(__file__).unlink()
