import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// iOS launch orchestration for emulators whose first game deeplink may need
/// time to complete their existing StikDebug/JIT handoff.
///
/// NeoStation does not modify, identify, or attach to the emulator itself.
/// Instead it opens the emulator's normal game URL immediately and asks the
/// native iOS layer to retry that exact URL after a short background window.
/// The first request can trigger the emulator's existing JIT flow; the retry
/// then gives the unmodified emulator a second chance to start the selected
/// game after JIT has settled.
class IosJitLaunchService {
  IosJitLaunchService._();

  static final _log = LoggerService.instance;

  /// Initial conservative value for on-device testing. It is deliberately
  /// centralized here so MeloNX/ARMSX2 can be tuned independently later
  /// without changing the native implementation.
  static const Duration defaultRetryDelay = Duration(seconds: 7);

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
