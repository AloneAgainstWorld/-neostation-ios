import 'dart:io';

import 'package:neostation/services/logger_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// Runs user-configured Apple Shortcuts used by NeoStation's iOS emulator
/// launch flow and opens their one-time installation links.
class IosShortcutJitLaunchService {
  IosShortcutJitLaunchService._();

  static final _log = LoggerService.instance;

  /// Keep this name in sync with the shared Shortcut. The `+` characters are
  /// part of the actual Shortcut name and are percent-encoded by [Uri] below.
  static const String melonxShortcutName = 'NeoStation+MeloNX+JIT';
  static const String armsx2ShortcutName = 'NeoStation+ARMSX2+JIT';

  /// One-time installer for the exact NeoStation MeloNX launch Shortcut.
  ///
  /// Replace the placeholder with the iCloud sharing URL copied from the
  /// Shortcuts app before shipping the patch. Keeping the URL here gives the
  /// settings card one stable place to manage the installer.
  static const String _melonxShortcutInstallUrl =
      'https://www.icloud.com/shortcuts/84b9d0fbdd714c6c9596ba2e3c699031';

  static bool get hasMeloNXShortcutInstaller =>
      _melonxShortcutInstallUrl.startsWith(
        'https://www.icloud.com/shortcuts/',
      );

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
