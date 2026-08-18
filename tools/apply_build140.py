from pathlib import Path
import plistlib
import uuid

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'Expected marker not found in {path}: {old[:120]!r}')
    if text.count(old) != 1:
        raise SystemExit(f'Expected one marker in {path}, found {text.count(old)}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


# Build number.
pubspec = ROOT / 'pubspec.yaml'
replace_once(pubspec, 'version: 0.9.9+139', 'version: 0.9.9+140')
replace_once(
    pubspec,
    '    - assets/data/\n    - assets/systems/',
    '    - assets/data/\n    - assets/shortcuts/\n    - assets/systems/',
)

# Retire the old injected RPCS3 boot script. The library/scraping integration
# stays intact; only the failed second-pass memory-injection launcher is removed.
old_script = ROOT / 'assets/data/rpcs3_stikdebug_launch.js'
if old_script.exists():
    old_script.unlink()

# Signing-aware JIT URL builder exposed to Dart. This lets NeoStation hand the
# exact StikDebug URL to Shortcuts instead of hard-coding a sideload suffix.
dart_plugin = ROOT / 'packages/external_folder_access/lib/external_folder_access.dart'
plugin_text = dart_plugin.read_text(encoding='utf-8')
marker = '''  /// Opens [url] immediately, then asks the native iOS layer to open the same
'''
insert = '''  /// Builds the exact StikDebug `enable-jit` URL without opening it. The iOS
  /// side applies the same SideStore/AltStore signing suffix logic as
  /// [openJitRequest], which is important when a Shortcut will open the URL
  /// later from another foreground process.
  static Future<String?> buildJitRequestUrl({
    required String targetBaseBundleId,
    String scriptName = 'universal.js',
    String? scriptDataBase64Url,
  }) async {
    if (!Platform.isIOS) return null;
    try {
      return await _channel.invokeMethod<String>('buildJitRequestUrl', {
        'targetBaseBundleId': targetBaseBundleId,
        'scriptName': scriptName,
        if (scriptDataBase64Url != null) 'scriptData': scriptDataBase64Url,
      });
    } on PlatformException {
      return null;
    }
  }

'''
if 'buildJitRequestUrl' not in plugin_text:
    if marker not in plugin_text:
        raise SystemExit('Could not locate Dart plugin insertion marker')
    dart_plugin.write_text(plugin_text.replace(marker, insert + marker, 1), encoding='utf-8')

swift = ROOT / 'packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift'
swift_text = swift.read_text(encoding='utf-8')
replace_once(
    swift,
    '''        case "openJitRequest":
            openJitRequest(call: call, result: result)
''',
    '''        case "openJitRequest":
            openJitRequest(call: call, result: result)
        case "buildJitRequestUrl":
            buildJitRequestUrl(call: call, result: result)
''',
)
swift_text = swift.read_text(encoding='utf-8')
start = swift_text.index('    private func openJitRequest(')
end = swift_text.index('    // MARK: - Explicit StikDebug JIT preflight', start)
new_swift_block = r'''    /// Builds the exact StikDebug request used by both the direct fallback
    /// and the Shortcut orchestration. Keeping this in one native helper means
    /// the signing-specific target bundle suffix can never diverge between the
    /// two launch paths.
    private func makeJitRequestURL(
        args: [String: Any]
    ) -> (url: URL, targetBaseBundleId: String, targetBundleId: String, scriptName: String)? {
        guard let targetBaseBundleId = args["targetBaseBundleId"] as? String,
            !targetBaseBundleId.isEmpty
        else {
            return nil
        }

        let scriptName = ((args["scriptName"] as? String) ?? "universal.js")
            .trimmingCharacters(in: .whitespacesAndNewlines)
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

        guard let url = components.url else { return nil }
        return (url, targetBaseBundleId, targetBundleId, scriptName)
    }

    /// Returns the signing-aware StikDebug URL to Dart without changing the
    /// foreground app. Shortcuts can then own the whole JIT -> RPCS3 ->
    /// Switch Control sequence.
    private func buildJitRequestUrl(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        guard let args = call.arguments as? [String: Any],
            let request = makeJitRequestURL(args: args)
        else {
            result(FlutterError(
                code: "INVALID_JIT_URL",
                message: "buildJitRequestUrl requires targetBaseBundleId",
                details: nil
            ))
            return
        }
        result(request.url.absoluteString)
    }

    private func openJitRequest(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        guard let args = call.arguments as? [String: Any],
            let request = makeJitRequestURL(args: args)
        else {
            result(FlutterError(
                code: "INVALID_JIT_URL",
                message: "openJitRequest requires targetBaseBundleId",
                details: nil
            ))
            return
        }

        let debugFileName = Self.safeDebugFileName(
            (args["debugFileName"] as? String) ?? "jit_request_debug.txt"
        )
        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: true,
            message: "STATE: JIT_REQUEST\n"
                + "Application state: \(Self.applicationStateName())\n"
                + "Target base bundle: \(request.targetBaseBundleId)\n"
                + "Target effective bundle: \(request.targetBundleId)\n"
                + "Script: \(request.scriptName)\n"
                + "URL: \(request.url.absoluteString)"
        )

        UIApplication.shared.open(request.url, options: [:]) { opened in
            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: opened ? "STATE: JIT_REQUEST_OPENED" : "STATE: JIT_REQUEST_FAILED"
            )
            result(opened)
        }
    }

'''
swift.write_text(swift_text[:start] + new_swift_block + swift_text[end:], encoding='utf-8')

# A shared Shortcuts service now owns the user-configured RPCS3 automation and
# can import the signed .shortcut bundled with NeoStation.
shortcut_service = ROOT / 'lib/services/ios_shortcut_jit_launch_service.dart'
shortcut_service.write_text(r'''import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/services.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

/// Runs user-configured Apple Shortcuts used by NeoStation's iOS emulator
/// launch flows and opens their one-time installers.
class IosShortcutJitLaunchService {
  IosShortcutJitLaunchService._();

  static final _log = LoggerService.instance;

  static const String melonxShortcutName = 'NeoStation+MeloNX+JIT';
  static const String armsx2ShortcutName = 'NeoStation+ARMSX2+JIT';

  /// RPCS3 deliberately uses a readable name because NeoStation invokes it
  /// through `shortcuts://run-shortcut` and passes the signing-aware StikDebug
  /// URL as text input.
  static const String rpcs3ShortcutName = 'NeoStation - RPCS3 Start';
  static const String rpcs3ShortcutAsset =
      'assets/shortcuts/NeoStation-RPCS3-Start.shortcut';
  static const String _rpcs3ConfiguredKey =
      'ios_rpcs3_switch_control_shortcut_configured_v1';

  static const String _melonxShortcutInstallUrl =
      'https://www.icloud.com/shortcuts/84b9d0fbdd714c6c9596ba2e3c699031';
  static const String _armsx2ShortcutInstallUrl =
      'https://www.icloud.com/shortcuts/1419632b150747f5bcd7b9bc65e36114';

  static bool get hasMeloNXShortcutInstaller =>
      _melonxShortcutInstallUrl.startsWith(
        'https://www.icloud.com/shortcuts/',
      );

  static bool get hasArmsx2ShortcutInstaller =>
      _armsx2ShortcutInstallUrl.startsWith(
        'https://www.icloud.com/shortcuts/',
      );

  static Future<bool> isRpcs3ShortcutConfigured() async {
    if (!Platform.isIOS) return false;
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_rpcs3ConfiguredKey) ?? false;
  }

  static Future<void> setRpcs3ShortcutConfigured(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_rpcs3ConfiguredKey, value);
  }

  /// Extracts NeoStation's signed RPCS3 Shortcut asset and presents iOS's
  /// document Open In flow. The imported Shortcut is universal up to the
  /// device-local Switch Control binding: after import the user must add the
  /// `Set Switch Control Switch State` action at the clearly marked comment
  /// and choose the switch created on that iPhone.
  static Future<bool> openRpcs3ShortcutInstaller() async {
    if (!Platform.isIOS) return false;
    try {
      final data = await rootBundle.load(rpcs3ShortcutAsset);
      final temp = await getTemporaryDirectory();
      final file = File(
        path.join(temp.path, 'NeoStation - RPCS3 Start.shortcut'),
      );
      await file.writeAsBytes(
        data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
        flush: true,
      );
      return await ExternalFolderAccess.openInMenu(file.path) == true;
    } catch (e) {
      _log.e(
        'IosShortcutJitLaunchService: failed to open RPCS3 Shortcut installer: $e',
      );
      return false;
    }
  }

  static Future<bool> openArmsx2ShortcutInstaller() async {
    if (!Platform.isIOS) return false;
    final target = hasArmsx2ShortcutInstaller
        ? Uri.parse(_armsx2ShortcutInstallUrl)
        : Uri.parse('shortcuts://create-shortcut');
    try {
      return await launchUrl(target, mode: LaunchMode.externalApplication);
    } catch (e) {
      _log.e(
        'IosShortcutJitLaunchService: failed to open ARMSX2 setup: $e',
      );
      return false;
    }
  }

  static Future<bool> openMeloNXShortcutInstaller() async {
    if (!Platform.isIOS || !hasMeloNXShortcutInstaller) return false;
    try {
      return await launchUrl(
        Uri.parse(_melonxShortcutInstallUrl),
        mode: LaunchMode.externalApplication,
      );
    } catch (e) {
      _log.e(
        'IosShortcutJitLaunchService: failed to open MeloNX installer: $e',
      );
      return false;
    }
  }

  /// Pure URL construction kept public for regression tests. Apple Shortcuts
  /// receives the exact StikDebug request as text, so no bundle suffix or query
  /// component is re-created inside the Shortcut itself.
  static Uri buildRunUri({
    required String shortcutName,
    required String input,
  }) => Uri(
    scheme: 'shortcuts',
    host: 'run-shortcut',
    queryParameters: <String, String>{
      'name': shortcutName,
      'input': 'text',
      'text': input,
    },
  );

  static Future<bool> runRpcs3Start(String jitRequestUrl) => run(
    shortcutName: rpcs3ShortcutName,
    input: jitRequestUrl,
  );

  /// Runs an installed Shortcut and passes its input as text.
  static Future<bool> run({
    required String shortcutName,
    required String input,
  }) async {
    if (!Platform.isIOS) return false;
    final shortcutUri = buildRunUri(shortcutName: shortcutName, input: input);
    try {
      return await launchUrl(
        shortcutUri,
        mode: LaunchMode.externalApplication,
      );
    } catch (e) {
      _log.e(
        'IosShortcutJitLaunchService: failed to run $shortcutName: $e',
      );
      return false;
    }
  }
}
''', encoding='utf-8')

# Simplified RPCS3 launcher: no pending lifecycle request, no second StikDebug
# pass, no core UUID/offset injection. Shortcut automation is opt-in; otherwise
# the stable single JIT request leaves Commencer/game selection to the user.
rpcs3_launch = ROOT / 'lib/services/rpcs3_launch_service.dart'
rpcs3_launch.write_text(r'''import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:neostation/services/ios_shortcut_jit_launch_service.dart';
import 'package:neostation/services/logger_service.dart';

/// Stable RPCS3 iOS launcher with an optional Switch Control Shortcut layer.
///
/// RPCS3 0.2 exposes neither an App Intent nor a public URL scheme for a
/// specific game. NeoStation therefore no longer injects private core offsets.
/// When the user explicitly configures the bundled Shortcut, it receives the
/// exact StikDebug JIT URL and can automate the fixed `Commencer` tap through a
/// device-local Switch Control recipe. The selected game itself remains a
/// manual RPCS3-library choice until RPCS3 exposes a supported launch API.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';
  static final LoggerService _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');

  /// Retained as a no-op compatibility hook for main.dart. The old lifecycle
  /// observer/second-pass launcher was intentionally removed in Build 140.
  static Future<void> initialize() async {}

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  @visibleForTesting
  static Uri buildShortcutUriForTesting(String jitRequestUrl) =>
      IosShortcutJitLaunchService.buildRunUri(
        shortcutName: IosShortcutJitLaunchService.rpcs3ShortcutName,
        input: jitRequestUrl,
      );

  static Future<bool> launchTitle(
    String? rawTitleId, {
    String? displayTitle,
    String? sourcePath,
    String? sourceKind,
  }) async {
    if (!Platform.isIOS) return false;
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null) return false;

    String? jitRequestUrl;
    try {
      jitRequestUrl = await ExternalFolderAccess.buildJitRequestUrl(
        targetBaseBundleId: targetBundleId,
        scriptName: 'universal.js',
      );
    } catch (e) {
      _log.w('RPCS3: could not build signing-aware JIT URL: $e');
    }

    final configured =
        await IosShortcutJitLaunchService.isRpcs3ShortcutConfigured();
    if (configured && jitRequestUrl != null && jitRequestUrl.isNotEmpty) {
      _log.i(
        'RPCS3 launch: SHORTCUT_REQUEST titleId=$titleId '
        'title=${displayTitle ?? ''} sourceKind=${sourceKind ?? ''} '
        'sourcePath=${sourcePath ?? ''}',
      );
      final opened = await IosShortcutJitLaunchService.runRpcs3Start(
        jitRequestUrl,
      );
      if (opened) {
        _log.i('RPCS3 launch: SHORTCUT_OPENED titleId=$titleId');
        return true;
      }
      _log.w('RPCS3 launch: SHORTCUT_FAILED; using single-pass JIT fallback');
    }

    // Stable fallback: one StikDebug JIT request only. No background timer,
    // no second attach and no private memory call. The user presses Commencer
    // and chooses the game in RPCS3.
    final opened = await ExternalFolderAccess.openJitRequest(
      targetBaseBundleId: targetBundleId,
      scriptName: 'universal.js',
      debugFileName: 'rpcs3_launch_debug.txt',
    );
    _log.i(
      'RPCS3 launch: ${opened == true ? 'FALLBACK_JIT_OPENED' : 'FALLBACK_JIT_FAILED'} '
      'titleId=$titleId',
    );
    return opened == true;
  }
}
''', encoding='utf-8')

# Game launch diagnostics should no longer claim a private direct-title launch.
game_launch = ROOT / 'lib/services/game/game_launch_service.dart'
game_text = game_launch.read_text(encoding='utf-8')
game_text = game_text.replace(
    "'ios_rpcs3_stikdebug'",
    "'ios_rpcs3_shortcut_or_stikdebug'",
)
game_launch.write_text(game_text, encoding='utf-8')

# Settings: add an opt-in setup dialog and a second RPCS3 card action. The
# library link/resync behavior is preserved exactly.
settings = ROOT / 'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart'
settings_text = settings.read_text(encoding='utf-8')
method_marker = '''  List<Widget> _iosEmulatorCards(ThemeData theme) {
'''
setup_method = r'''  Future<void> _configureRpcs3Launch() async {
    final configured =
        await IosShortcutJitLaunchService.isRpcs3ShortcutConfigured();
    if (!mounted) return;
    final isFrench = Localizations.localeOf(context).languageCode == 'fr';

    final action = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(
          isFrench
              ? 'RPCS3 — automatisation « Commencer » (alpha)'
              : 'RPCS3 — “Start” automation (alpha)',
        ),
        content: SingleChildScrollView(
          child: Text(
            isFrench
                ? 'Cette option remplace l’ancienne injection RPCS3.\n\n'
                      '1. Importez le raccourci NeoStation - RPCS3 Start.\n'
                      '2. Dans Réglages > Accessibilité > Contrôle de commutateurs, créez un commutateur et une recette avec un geste personnalisé qui touche le bouton « Commencer » de RPCS3 en paysage.\n'
                      '3. Ouvrez le raccourci importé. À l’emplacement du commentaire prévu, ajoutez l’action « Définir l’état du commutateur Contrôle de commutateurs » et choisissez VOTRE commutateur local.\n'
                      '4. Revenez ici et choisissez « Configuration terminée ».\n\n'
                      'Le raccourci peut automatiser « Commencer », mais RPCS3 0.2 ne fournit toujours aucune API permettant à NeoStation de sélectionner automatiquement un jeu précis.'
                : 'This replaces the previous RPCS3 memory-injection experiment.\n\n'
                      '1. Import NeoStation - RPCS3 Start.\n'
                      '2. In Settings > Accessibility > Switch Control, create a switch and recipe with a custom landscape gesture that taps RPCS3’s Start button.\n'
                      '3. Open the imported Shortcut. At the marked comment, add “Set Switch Control Switch State” and bind YOUR local switch.\n'
                      '4. Return here and choose “Setup complete”.\n\n'
                      'This can automate Start, but RPCS3 0.2 still exposes no supported API for selecting a specific game.',
          ),
        ),
        actions: [
          if (configured)
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop('disable'),
              child: Text(isFrench ? 'Désactiver' : 'Disable'),
            ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop('install'),
            child: Text(isFrench ? 'Importer le raccourci' : 'Import Shortcut'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop('enable'),
            child: Text(
              isFrench ? 'Configuration terminée' : 'Setup complete',
            ),
          ),
        ],
      ),
    );
    if (!mounted || action == null) return;

    if (action == 'install') {
      final opened =
          await IosShortcutJitLaunchService.openRpcs3ShortcutInstaller();
      if (!mounted) return;
      AppNotification.showNotification(
        context,
        opened
            ? (isFrench
                  ? 'Raccourci RPCS3 envoyé vers iOS. Terminez le réglage du commutateur puis revenez dans NeoStation.'
                  : 'RPCS3 Shortcut sent to iOS. Finish the local switch binding, then return to NeoStation.')
            : (isFrench
                  ? 'Impossible d’ouvrir le raccourci RPCS3.'
                  : 'Could not open the RPCS3 Shortcut.'),
        type: opened ? NotificationType.info : NotificationType.error,
      );
      return;
    }

    final enable = action == 'enable';
    await IosShortcutJitLaunchService.setRpcs3ShortcutConfigured(enable);
    if (!mounted) return;
    setState(() {});
    AppNotification.showNotification(
      context,
      enable
          ? (isFrench
                ? 'Automatisation RPCS3 activée.'
                : 'RPCS3 Shortcut automation enabled.')
          : (isFrench
                ? 'Automatisation RPCS3 désactivée : lancement StikDebug standard.'
                : 'RPCS3 automation disabled: standard StikDebug launch restored.'),
      type: NotificationType.info,
    );
  }

'''
if setup_method not in settings_text:
    if method_marker not in settings_text:
        raise SystemExit('Could not locate settings method insertion marker')
    settings_text = settings_text.replace(method_marker, setup_method + method_marker, 1)

old_rpcs3_action = '''      trailingAction: SizedBox(
        height: 48.r,
        child: FilledButton.icon(
          onPressed: !isLinked ? null : _syncWithRpcs3,
          icon: Icon(Symbols.sync_rounded, size: 20.r),
          label: Text(
            hasSynced
                ? AppLocale.iosEmuResync.getString(context)
                : AppLocale.iosEmuSync.getString(context),
            style: TextStyle(fontSize: 14.r),
          ),
        ),
      ),
'''
new_rpcs3_action = '''      trailingAction: Row(
        children: [
          Expanded(
            child: SizedBox(
              height: 48.r,
              child: FilledButton.icon(
                onPressed: !isLinked ? null : _syncWithRpcs3,
                icon: Icon(Symbols.sync_rounded, size: 20.r),
                label: Text(
                  hasSynced
                      ? AppLocale.iosEmuResync.getString(context)
                      : AppLocale.iosEmuSync.getString(context),
                  style: TextStyle(fontSize: 14.r),
                ),
              ),
            ),
          ),
          SizedBox(width: 8.r),
          FutureBuilder<bool>(
            future: IosShortcutJitLaunchService.isRpcs3ShortcutConfigured(),
            builder: (context, snapshot) {
              final configured = snapshot.data ?? false;
              return SizedBox(
                height: 48.r,
                child: OutlinedButton.icon(
                  onPressed: _configureRpcs3Launch,
                  icon: Icon(
                    configured
                        ? Symbols.check_circle_rounded
                        : Symbols.touch_app_rounded,
                    size: 20.r,
                  ),
                  label: Text(
                    configured ? 'Auto Start' : 'Shortcut',
                    style: TextStyle(fontSize: 14.r),
                  ),
                ),
              );
            },
          ),
        ],
      ),
'''
# Replace only the action inside _buildIOSRpcs3Section by slicing that method.
rpcs3_method_start = settings_text.index('  Widget _buildIOSRpcs3Section(ThemeData theme) {')
rpcs3_method_end = settings_text.index('  /// ARMSX2 is sync-only', rpcs3_method_start)
rpcs3_chunk = settings_text[rpcs3_method_start:rpcs3_method_end]
if old_rpcs3_action not in rpcs3_chunk:
    raise SystemExit('Could not locate RPCS3 trailing action')
rpcs3_chunk = rpcs3_chunk.replace(old_rpcs3_action, new_rpcs3_action, 1)
settings_text = (
    settings_text[:rpcs3_method_start]
    + rpcs3_chunk
    + settings_text[rpcs3_method_end:]
)
settings.write_text(settings_text, encoding='utf-8')

# Stage 6 now keeps only the library/title reliability assertions. The retired
# second-pass protocol must not remain encoded in regression tests.
(ROOT / 'test/rpcs3_stage6_test.dart').write_text(r'''import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:neostation/services/rpcs3_title_catalog_service.dart';

void main() {
  group('RPCS3 library reliability', () {
    test('cached raw serial receives GameDB title even without live folder', () async {
      final enriched = await Rpcs3LibraryService.applyTitleCatalogForTesting(
        const <Rpcs3LibraryGame>[
          Rpcs3LibraryGame(
            titleId: 'BLES00412',
            title: 'BLES00412',
            version: '',
            category: '',
            sourcePath: '/unavailable/RPCS3/Data/game.iso',
            sourceKind: 'disc-image',
          ),
        ],
        const <String, String>{
          'BLES00412': 'The Lord of the Rings: Conquest',
        },
      );
      expect(enriched.single.title, 'The Lord of the Rings: Conquest');
    });

    test('GameDB normalization accepts dashed PS3 serials', () {
      expect(
        Rpcs3TitleCatalogService.normalizeTitleId('BLES-00412'),
        'BLES00412',
      );
    });
  });
}
''', encoding='utf-8')

(ROOT / 'test/rpcs3_stage7_test.dart').write_text(r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/ios_shortcut_jit_launch_service.dart';
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

  test('RPCS3 Shortcut URL carries the exact signing-aware JIT request', () {
    const jit =
        'stikjit://enable-jit?bundle-id=com.xitrix.RPCS3.TEAM&script-name=universal.js';
    final uri = Rpcs3LaunchService.buildShortcutUriForTesting(jit);
    expect(uri.scheme, 'shortcuts');
    expect(uri.host, 'run-shortcut');
    expect(
      uri.queryParameters['name'],
      IosShortcutJitLaunchService.rpcs3ShortcutName,
    );
    expect(uri.queryParameters['input'], 'text');
    expect(uri.queryParameters['text'], jit);
  });

  test('old RPCS3 private-memory second pass is retired', () {
    final service = File(
      'lib/services/rpcs3_launch_service.dart',
    ).readAsStringSync();
    expect(service, contains('buildJitRequestUrl'));
    expect(service, contains('runRpcs3Start'));
    expect(service, contains('FALLBACK_JIT_OPENED'));
    expect(service, contains('openJitRequest'));
    expect(service, isNot(contains('supportedCoreFunctions')));
    expect(service, isNot(contains('SECOND_PASS')));
    expect(service, isNot(contains('bootGameOffset')));
    expect(File('assets/data/rpcs3_stikdebug_launch.js').existsSync(), isFalse);
  });

  test('bundled Shortcut source documents the device-local switch binding', () {
    final source = File(
      'tools/rpcs3_shortcut_source.plist',
    ).readAsStringSync();
    expect(source, contains('is.workflow.actions.openurl'));
    expect(source, contains('is.workflow.actions.delay'));
    expect(
      source,
      contains('com.apple.UniversalAccess.UASettingsShortcuts.UAToggleSwitchControlIntent'),
    );
    expect(source, contains('Set Switch Control Switch State'));
  });
}
''', encoding='utf-8')

# Reproducible source for the signed Shortcut. The final system action that
# manipulates a Switch Control switch cannot be pre-bound portably because the
# switch entity is created locally on each iPhone; a marker comment tells the
# user exactly where to add/bind it once after import.
def uid() -> str:
    return str(uuid.uuid4()).upper()

shortcut = {
    'WFQuickActionSurfaces': [],
    'WFWorkflowActions': [
        {
            'WFWorkflowActionIdentifier': 'is.workflow.actions.comment',
            'WFWorkflowActionParameters': {
                'UUID': uid(),
                'WFCommentActionText': (
                    'NeoStation RPCS3 alpha: Shortcut Input is the exact '
                    'signing-aware StikDebug enable-jit URL generated by NeoStation.'
                ),
            },
        },
        {
            'WFWorkflowActionIdentifier': 'is.workflow.actions.openurl',
            'WFWorkflowActionParameters': {
                'UUID': uid(),
                'WFInput': {
                    'Value': {'Type': 'ExtensionInput'},
                    'WFSerializationType': 'WFTextTokenAttachment',
                },
            },
        },
        {
            'WFWorkflowActionIdentifier': 'is.workflow.actions.delay',
            'WFWorkflowActionParameters': {
                'UUID': uid(),
                'WFDelayTime': 4,
            },
        },
        {
            'WFWorkflowActionIdentifier':
                'com.apple.UniversalAccess.UASettingsShortcuts.UAToggleSwitchControlIntent',
            'WFWorkflowActionParameters': {
                'UUID': uid(),
                'operation': 'turn',
                'state': True,
                'ShowWhenRun': False,
            },
        },
        {
            'WFWorkflowActionIdentifier': 'is.workflow.actions.comment',
            'WFWorkflowActionParameters': {
                'UUID': uid(),
                'WFCommentActionText': (
                    'DEVICE-LOCAL STEP — add “Set Switch Control Switch State” '
                    'directly below this comment and bind the switch/recipe you '
                    'created on this iPhone. This entity cannot be safely '
                    'pre-bound in a shared Shortcut. Its custom gesture should '
                    'tap RPCS3 “Commencer” in landscape.'
                ),
            },
        },
    ],
    'WFWorkflowClientVersion': '4000',
    'WFWorkflowHasOutputFallback': False,
    'WFWorkflowHasShortcutInputVariables': True,
    'WFWorkflowIcon': {
        'WFWorkflowIconGlyphNumber': 59511,
        'WFWorkflowIconStartColor': 2071128575,
    },
    'WFWorkflowImportQuestions': [],
    'WFWorkflowInputContentItemClasses': ['WFStringContentItem', 'WFURLContentItem'],
    'WFWorkflowMinimumClientVersion': 900,
    'WFWorkflowMinimumClientVersionString': '900',
    'WFWorkflowOutputContentItemClasses': [],
    'WFWorkflowTypes': ['WFWorkflowTypeShowInSearch'],
}
source_path = ROOT / 'tools/rpcs3_shortcut_source.plist'
with source_path.open('wb') as fh:
    plistlib.dump(shortcut, fh, fmt=plistlib.FMT_XML, sort_keys=False)

print('Build 140 RPCS3 Shortcut migration applied.')
