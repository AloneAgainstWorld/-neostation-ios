import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// Native iOS launch orchestration for external emulators that need JIT.
///
/// Two strategies are intentionally kept for compatibility:
/// - [launchAfterPreflight]: new MeloNX flow. StikDebug/JIT is requested first,
///   then the game deeplink is opened after a warm-up delay.
/// - [launchWithRetry]: legacy ARMSX2 flow. The normal game deeplink is opened
///   immediately and retried after a short delay.
///
/// Keeping both methods lets MeloNX be tested progressively without changing
/// the current ARMSX2 behaviour at the same time.
class IosJitLaunchService {
  IosJitLaunchService._();

  static final _log = LoggerService.instance;

  static const Duration defaultWarmupDelay = Duration(seconds: 8);
  static const Duration defaultRetryDelay = Duration(seconds: 7);

  /// New pre-JIT flow currently used by MeloNX.
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

  /// Compatibility flow still used by ARMSX2.
  ///
  /// This method existed before the MeloNX preflight experiment. Re-adding it
  /// prevents ARMSX2 from being changed while MeloNX is being validated.
  static Future<bool> launchWithRetry(
    Uri launchUri, {
    Duration retryDelay = defaultRetryDelay,
    String debugFileName = 'jit_launch_debug.txt',
  }) async {
    if (!Platform.isIOS) {
      return launchUrl(launchUri, mode: LaunchMode.externalApplication);
    }

    try {
      final scheduled = await ExternalFolderAccess.openUrlWithDelayedRetry(
        launchUri.toString(),
        retryDelay: retryDelay,
        debugFileName: debugFileName,
      );
      return scheduled ?? false;
    } catch (e) {
      _log.e('IosJitLaunchService: delayed launch failed for $launchUri: $e');
      return false;
    }
  }
}
