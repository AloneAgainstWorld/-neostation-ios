from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'Expected one marker in {path}, found {count}: {old[:100]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


# Build 140. Keep every Build 138/139 asset declaration untouched.
pubspec = ROOT / 'pubspec.yaml'
replace_once(pubspec, 'version: 0.9.9+139', 'version: 0.9.9+140')

# Retire only the failed private-memory RPCS3 second-pass script. RPCS3 library
# sync, title repair, scraping and the stable StikDebug JIT request remain.
old_script = ROOT / 'assets/data/rpcs3_stikdebug_launch.js'
if old_script.exists():
    old_script.unlink()

# Extend the existing Shortcut helper with device-local RPCS3 automation state.
# Personal automations and Switch Control switches cannot be shipped inside an
# IPA: Apple stores them per-device. NeoStation can open Shortcuts and remember
# whether the user completed the one-time setup.
shortcut_service = ROOT / 'lib/services/ios_shortcut_jit_launch_service.dart'
shortcut_service.write_text(r'''import 'dart:io';

import 'package:neostation/services/logger_service.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

/// Runs user-configured Apple Shortcuts used by NeoStation's iOS emulator
/// launch flows and opens their one-time setup screens.
class IosShortcutJitLaunchService {
  IosShortcutJitLaunchService._();

  static final _log = LoggerService.instance;

  static const String melonxShortcutName = 'NeoStation+MeloNX+JIT';
  static const String armsx2ShortcutName = 'NeoStation+ARMSX2+JIT';

  /// A personal automation is intentionally used for RPCS3 instead of a
  /// shareable `.shortcut`: the Switch Control switch/recipe referenced by the
  /// automation is a device-local accessibility entity and cannot be safely
  /// pre-bound on another iPhone.
  static const String _rpcs3AutomationConfiguredKey =
      'ios_rpcs3_switch_control_automation_configured_v1';

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

  static Future<bool> isRpcs3AutomationConfigured() async {
    if (!Platform.isIOS) return false;
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_rpcs3AutomationConfiguredKey) ?? false;
  }

  static Future<void> setRpcs3AutomationConfigured(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_rpcs3AutomationConfiguredKey, value);
  }

  /// Opens Shortcuts so the user can create/edit the device-local Personal
  /// Automation: App = RPCS3, Is Opened, Run Immediately, then Switch Control
  /// actions bound to that iPhone's custom switch recipe.
  static Future<bool> openRpcs3AutomationSetup() async {
    if (!Platform.isIOS) return false;
    try {
      return await launchUrl(
        Uri.parse('shortcuts://'),
        mode: LaunchMode.externalApplication,
      );
    } catch (e) {
      _log.e(
        'IosShortcutJitLaunchService: failed to open RPCS3 automation setup: $e',
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

  /// Runs an installed Shortcut and passes its input as text. Kept for the
  /// existing ARMSX2/MeloNX integrations.
  static Future<bool> run({
    required String shortcutName,
    required String input,
  }) async {
    if (!Platform.isIOS) return false;
    final shortcutUri = Uri(
      scheme: 'shortcuts',
      host: 'run-shortcut',
      queryParameters: <String, String>{
        'name': shortcutName,
        'input': 'text',
        'text': input,
      },
    );
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

# Stable RPCS3 launch path. The old lifecycle observer, pending request,
# second StikDebug attach, core UUID map and private rpcs3_ios_boot_game call are
# intentionally gone. The Personal Automation is triggered by iOS itself when
# RPCS3 becomes foreground; NeoStation only has to make the single JIT request.
rpcs3_launch = ROOT / 'lib/services/rpcs3_launch_service.dart'
rpcs3_launch.write_text(r'''import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/ios_shortcut_jit_launch_service.dart';
import 'package:neostation/services/logger_service.dart';

/// Stable RPCS3 iOS launcher with an optional device-local Switch Control
/// Personal Automation for the fixed `Commencer` tap.
///
/// RPCS3 0.2 exposes no supported App Intent or deep link for a specific game.
/// NeoStation therefore launches only the standard StikDebug Universal JIT
/// request. If the user configured the iOS automation, iOS reacts when RPCS3
/// opens and performs the accessibility gesture. Game selection remains manual.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';
  static final LoggerService _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');

  /// Retained for the existing main.dart call. Build 140 intentionally has no
  /// RPCS3 lifecycle observer or delayed second pass.
  static Future<void> initialize() async {}

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  static Future<bool> launchTitle(
    String? rawTitleId, {
    String? displayTitle,
    String? sourcePath,
    String? sourceKind,
  }) async {
    if (!Platform.isIOS) return false;
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null) return false;

    final automationConfigured =
        await IosShortcutJitLaunchService.isRpcs3AutomationConfigured();
    _log.i(
      'RPCS3 launch: SINGLE_PASS_JIT titleId=$titleId '
      'automation=${automationConfigured ? 'configured' : 'manual'} '
      'title=${displayTitle ?? ''} sourceKind=${sourceKind ?? ''} '
      'sourcePath=${sourcePath ?? ''}',
    );

    final opened = await ExternalFolderAccess.openJitRequest(
      targetBaseBundleId: targetBundleId,
      scriptName: 'universal.js',
      debugFileName: 'rpcs3_launch_debug.txt',
    );
    _log.i(
      'RPCS3 launch: ${opened == true ? 'JIT_OPENED' : 'JIT_FAILED'} '
      'titleId=$titleId automation=${automationConfigured ? 'armed' : 'manual'}',
    );
    return opened == true;
  }
}
''', encoding='utf-8')

# Make diagnostics accurately describe the new path.
game_launch = ROOT / 'lib/services/game/game_launch_service.dart'
game_text = game_launch.read_text(encoding='utf-8')
if "'ios_rpcs3_stikdebug'" not in game_text:
    raise SystemExit('Expected RPCS3 session label was not found')
game_launch.write_text(
    game_text.replace(
        "'ios_rpcs3_stikdebug'",
        "'ios_rpcs3_stikdebug_switch_control'",
        1,
    ),
    encoding='utf-8',
)

# Settings UI: preserve RPCS3 Data linking/sync exactly and add a separate
# opt-in setup action for the per-device automation.
settings = ROOT / 'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart'
settings_text = settings.read_text(encoding='utf-8')
method_marker = '''  List<Widget> _iosEmulatorCards(ThemeData theme) {
'''
setup_method = r'''  Future<void> _configureRpcs3Launch() async {
    final configured =
        await IosShortcutJitLaunchService.isRpcs3AutomationConfigured();
    if (!mounted) return;
    final isFrench = Localizations.localeOf(context).languageCode == 'fr';

    final instructions = isFrench
        ? 'Configuration locale iPhone (une seule fois) :\n\n'
              '1. Réglages > Accessibilité > Contrôle de commutateurs : créez un commutateur et une recette avec un geste personnalisé qui touche le bouton « Commencer » de RPCS3 en paysage.\n\n'
              '2. Dans Raccourcis > Automatisation, créez une automatisation personnelle : App > RPCS3 > Est ouverte > Exécuter immédiatement.\n\n'
              '3. Ajoutez « Définir Contrôle de commutateurs » sur Activé, puis « Définir l’état du commutateur Contrôle de commutateurs » et sélectionnez VOTRE commutateur.\n\n'
              '4. Si nécessaire pour votre recette, désactivez ensuite Contrôle de commutateurs à la fin de l’automatisation.\n\n'
              'Cette automatisation s’exécute chaque fois que RPCS3 s’ouvre. Elle peut automatiser « Commencer », mais RPCS3 0.2 ne fournit toujours aucune API permettant à NeoStation de sélectionner automatiquement un jeu précis.'
        : 'One-time local iPhone setup:\n\n'
              '1. Settings > Accessibility > Switch Control: create a switch and recipe with a custom landscape gesture that taps RPCS3’s Start button.\n\n'
              '2. In Shortcuts > Automation, create a Personal Automation: App > RPCS3 > Is Opened > Run Immediately.\n\n'
              '3. Add “Set Switch Control” = On, then “Set Switch Control Switch State” and select YOUR switch.\n\n'
              '4. If your recipe needs it, turn Switch Control off again at the end of the automation.\n\n'
              'This automation runs whenever RPCS3 opens. It can automate Start, but RPCS3 0.2 still provides no supported API for NeoStation to select a specific game.';

    final action = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(
          isFrench
              ? 'RPCS3 — « Commencer » automatique (alpha)'
              : 'RPCS3 — automatic Start (alpha)',
        ),
        content: SingleChildScrollView(child: Text(instructions)),
        actions: [
          TextButton(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: instructions));
              if (dialogContext.mounted) {
                Navigator.of(dialogContext).pop('copied');
              }
            },
            child: Text(isFrench ? 'Copier les étapes' : 'Copy steps'),
          ),
          if (configured)
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop('disable'),
              child: Text(isFrench ? 'Désactiver' : 'Disable'),
            ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop('open'),
            child: Text(isFrench ? 'Ouvrir Raccourcis' : 'Open Shortcuts'),
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

    if (action == 'open') {
      final opened =
          await IosShortcutJitLaunchService.openRpcs3AutomationSetup();
      if (!mounted || opened) return;
      AppNotification.showNotification(
        context,
        isFrench
            ? 'Impossible d’ouvrir Raccourcis.'
            : 'Could not open Shortcuts.',
        type: NotificationType.error,
      );
      return;
    }

    if (action == 'copied') {
      AppNotification.showNotification(
        context,
        isFrench
            ? 'Étapes copiées dans le presse-papiers.'
            : 'Setup steps copied to the clipboard.',
        type: NotificationType.info,
      );
      return;
    }

    final enable = action == 'enable';
    await IosShortcutJitLaunchService.setRpcs3AutomationConfigured(enable);
    if (!mounted) return;
    setState(() {});
    AppNotification.showNotification(
      context,
      enable
          ? (isFrench
                ? 'Automatisation RPCS3 marquée comme configurée.'
                : 'RPCS3 automation marked as configured.')
          : (isFrench
                ? 'Automatisation RPCS3 désactivée dans NeoStation. Le lancement StikDebug standard reste actif.'
                : 'RPCS3 automation disabled in NeoStation. Standard StikDebug launch remains active.'),
      type: NotificationType.info,
    );
  }

'''
if method_marker not in settings_text:
    raise SystemExit('Could not locate settings insertion marker')
settings_text = settings_text.replace(method_marker, setup_method + method_marker, 1)

old_action = '''      trailingAction: SizedBox(
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
new_action = '''      trailingAction: Row(
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
            future:
                IosShortcutJitLaunchService.isRpcs3AutomationConfigured(),
            builder: (context, snapshot) {
              final configured = snapshot.data ?? false;
              return SizedBox(
                height: 48.r,
                child: OutlinedButton.icon(
                  onPressed: _configureRpcs3Launch,
                  icon: Icon(
                    configured
                        ? Symbols.check_circle_rounded
                        : Symbols.settings_rounded,
                    size: 20.r,
                  ),
                  label: Text(
                    configured ? 'Auto Start' : 'Automation',
                    style: TextStyle(fontSize: 14.r),
                  ),
                ),
              );
            },
          ),
        ],
      ),
'''
start = settings_text.index('  Widget _buildIOSRpcs3Section(ThemeData theme) {')
end = settings_text.index('  /// ARMSX2 is sync-only', start)
chunk = settings_text[start:end]
if old_action not in chunk:
    raise SystemExit('Could not locate RPCS3 trailing action')
chunk = chunk.replace(old_action, new_action, 1)
settings_text = settings_text[:start] + chunk + settings_text[end:]
settings.write_text(settings_text, encoding='utf-8')

# Keep the library reliability tests while removing assumptions about the
# retired second-pass launcher.
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

  test('old RPCS3 private-memory second pass is retired', () {
    final service = File(
      'lib/services/rpcs3_launch_service.dart',
    ).readAsStringSync();
    expect(service, contains('SINGLE_PASS_JIT'));
    expect(service, contains('openJitRequest'));
    expect(service, contains('isRpcs3AutomationConfigured'));
    expect(service, isNot(contains('supportedCoreFunctions')));
    expect(service, isNot(contains('SECOND_PASS')));
    expect(service, isNot(contains('bootGameOffset')));
    expect(File('assets/data/rpcs3_stikdebug_launch.js').existsSync(), isFalse);
  });

  test('RPCS3 setup is explicitly device-local Personal Automation', () {
    final helper = File(
      'lib/services/ios_shortcut_jit_launch_service.dart',
    ).readAsStringSync();
    final settings = File(
      'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    ).readAsStringSync();
    expect(helper, contains('shortcuts://'));
    expect(helper, contains('isRpcs3AutomationConfigured'));
    expect(settings, contains('Automatisation personnelle'));
    expect(settings, contains('Est ouverte'));
    expect(settings, contains('Exécuter immédiatement'));
    expect(settings, contains('Set Switch Control Switch State'));
    expect(settings, contains('Définir l’état du commutateur Contrôle de commutateurs'));
  });
}
''', encoding='utf-8')

print('Build 140 device-local RPCS3 automation migration applied.')
