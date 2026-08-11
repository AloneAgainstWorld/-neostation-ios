import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// Native iOS launch orchestration for external emulators that need JIT.
///
/// The preferred flow is now a *preflight* rather than a retry:
///   NeoStation -> StikDebug/JIT -> short warm-up -> emulator game deeplink.
///
/// This matters for iOS 26-style JIT where StikDebug's universal.js script must
/// be attached before a demanding title starts allocating/compiling heavily.
/// NeoStation never modifies the emulator or StikDebug itself.
class IosJitLaunchService {
  IosJitLaunchService._();

  static final _log = LoggerService.instance;

  static const Duration defaultWarmupDelay = Duration(seconds: 8);

  static Future<bool> launchAfterPreflight(
    Uri launchUri, {
    required String targetBaseBundleId,
    Duration warmupDelay = defaultWarmupDelay,
    String scriptName = 'universal.js',
    String debugFileName = 'jit_preflight_debug.txt',
  }) async {
    if (!Platform.isIOS) {
      return launchUrl(launchUri, mode: LaunchMode.externalApplication);
    }

    try {
      final scheduled = await ExternalFolderAccess.openUrlAfterJitPreflight(
        launchUri.toString(),
        targetBaseBundleId: targetBaseBundleId,
        warmupDelay: warmupDelay,
        scriptName: scriptName,
        debugFileName: debugFileName,
      );
      return scheduled ?? false;
    } catch (e) {
      _log.e('IosJitLaunchService: JIT preflight failed for $launchUri: $e');
      return false;
    }
  }
}
