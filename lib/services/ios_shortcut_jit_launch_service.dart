import 'dart:io';

import 'package:neostation/services/logger_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// Handles iOS Shortcut installation and JIT-assisted emulator launches.
///
/// Shortcut setup and payload construction live here so MeloNX and ARMSX2
/// share the same launch behavior.
class IosShortcutJitLaunchService {
  IosShortcutJitLaunchService._();

  static final _log = LoggerService.instance;

  /// Keep these names in sync with the shared Shortcuts. The `+` characters
  /// are part of the Shortcut names and are percent-encoded by [Uri].
  static const String melonxShortcutName = 'NeoStation+MeloNX+JIT';
  static const String armsx2ShortcutName = 'NeoStation+ARMSX2+JIT';

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

  /// Opens the shared ARMSX2 Shortcut installer.
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

  /// Opens the shared MeloNX Shortcut installer.
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

  /// Runs an installed Shortcut with an emulator game deeplink as text input.
  /// The Shortcut keeps control while StikDebug enables JIT, then opens the
  /// game URL.
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
