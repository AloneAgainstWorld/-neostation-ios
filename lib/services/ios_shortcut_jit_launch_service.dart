import 'dart:io';

import 'package:neostation/services/logger_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// Runs user-configured Apple Shortcuts used by NeoStation's iOS emulator
/// launch flow and opens their one-time installation/setup links.
class IosShortcutJitLaunchService {
  IosShortcutJitLaunchService._();

  static final _log = LoggerService.instance;

  /// Keep these names in sync with the shared/user-created Shortcuts.
  /// The `+` characters are part of the actual Shortcut names and are
  /// percent-encoded by [Uri] below.
  static const String melonxShortcutName = 'NeoStation+MeloNX+JIT';
  static const String armsx2ShortcutName = 'NeoStation+ARMSX2+JIT';
  static const String rpcs3ShortcutName = 'NeoStation+RPCS3+Start';

  /// One-time installer for the exact NeoStation MeloNX launch Shortcut.
  static const String _melonxShortcutInstallUrl =
      'https://www.icloud.com/shortcuts/84b9d0fbdd714c6c9596ba2e3c699031';

  /// One-time installer for the exact NeoStation ARMSX2 launch Shortcut.
  static const String _armsx2ShortcutInstallUrl =
      'https://www.icloud.com/shortcuts/1419632b150747f5bcd7b9bc65e36114';

  /// RPCS3 intentionally has no shared iCloud installer yet.
  ///
  /// The automation depends on a Switch Control switch/gesture created on the
  /// user's own device, and Apple does not provide a public API for an app to
  /// create that accessibility configuration. NeoStation therefore opens the
  /// official Shortcuts editor and shows the required device-local steps in
  /// its settings UI instead of shipping a misleading pre-bound Shortcut.
  static const String _rpcs3ShortcutInstallUrl = '';

  static bool get hasMeloNXShortcutInstaller =>
      _melonxShortcutInstallUrl.startsWith(
        'https://www.icloud.com/shortcuts/',
      );

  static bool get hasArmsx2ShortcutInstaller =>
      _armsx2ShortcutInstallUrl.startsWith(
        'https://www.icloud.com/shortcuts/',
      );

  static bool get hasRpcs3ShortcutInstaller =>
      _rpcs3ShortcutInstallUrl.startsWith(
        'https://www.icloud.com/shortcuts/',
      );

  /// Opens the shared ARMSX2 launch Shortcut. While the iCloud sharing link
  /// is not configured yet, fall back to Apple's official create-shortcut URL.
  static Future<bool> openArmsx2ShortcutInstaller() async {
    if (!Platform.isIOS) return false;

    final target = hasArmsx2ShortcutInstaller
        ? Uri.parse(_armsx2ShortcutInstallUrl)
        : Uri.parse('shortcuts://create-shortcut');

    try {
      return await launchUrl(
        target,
        mode: LaunchMode.externalApplication,
      );
    } catch (e) {
      _log.e(
        'IosShortcutJitLaunchService: failed to open ARMSX2 setup: $e',
      );
      return false;
    }
  }

  /// Opens Apple's import sheet for the shared MeloNX Shortcut.
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

  /// Opens the RPCS3 automation setup entry point.
  ///
  /// Until a portable, device-independent Switch Control binding exists,
  /// this opens a blank Shortcut editor. The user creates the small
  /// `NeoStation+RPCS3+Start` helper and a personal automation triggered when
  /// RPCS3 opens. NeoStation itself remains on the stable standard JIT path.
  static Future<bool> openRpcs3ShortcutInstaller() async {
    if (!Platform.isIOS) return false;

    final target = hasRpcs3ShortcutInstaller
        ? Uri.parse(_rpcs3ShortcutInstallUrl)
        : Uri.parse('shortcuts://create-shortcut');

    try {
      return await launchUrl(
        target,
        mode: LaunchMode.externalApplication,
      );
    } catch (e) {
      _log.e(
        'IosShortcutJitLaunchService: failed to open RPCS3 setup: $e',
      );
      return false;
    }
  }

  /// Runs an installed Shortcut and passes an emulator game deeplink as text
  /// input. The Shortcut owns the foreground sequence so StikDebug can finish
  /// enabling JIT before it opens the game URL.
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
