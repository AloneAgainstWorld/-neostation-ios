import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/logger_service.dart';

/// Stable RPCS3 iOS launcher.
///
/// NeoStation starts RPCS3's normal StikDebug Universal JIT flow, then the
/// native iOS helper foregrounds RPCS3 itself after the JIT warm-up. Opening
/// RPCS3 is the event used by the user's device-local Personal Automation,
/// which runs `NeoStation+RPCS3+Start` while RPCS3 is already foregrounded.
///
/// This avoids trying to open Apple's Shortcuts URL scheme from NeoStation's
/// background execution window. It also keeps the retired RPCS3Core memory
/// injection / second-pass protocol out of the stable launch path.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';
  static const Duration _rpcs3WarmupDelay = Duration(seconds: 8);

  static final LoggerService _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  /// Kept as a no-op compatibility hook because older application startup
  /// code calls [initialize]. There is intentionally no lifecycle observer
  /// and no second-pass RPCS3Core injection anymore.
  static Future<void> initialize() async {}

  /// Starts StikDebug with the normal Universal JIT request for RPCS3, waits
  /// for the bounded warm-up window, then asks StikDebug to foreground RPCS3.
  ///
  /// The app-open transition is deliberately the final native handoff. The
  /// user's iOS Personal Automation observes "RPCS3 is opened" and runs the
  /// `NeoStation+RPCS3+Start` Shortcut from that event, so the Switch Control
  /// gesture executes against RPCS3 instead of against the Shortcuts app.
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
      'RPCS3 automation launch: titleId=$titleId '
      'title=${displayTitle?.trim() ?? ''} '
      'sourceKind=${sourceKind?.trim() ?? ''} '
      'sourcePath=${sourcePath?.trim() ?? ''}',
    );

    try {
      final opened = await ExternalFolderAccess.openAppAfterJitPreflight(
        targetBaseBundleId: targetBundleId,
        warmupDelay: _rpcs3WarmupDelay,
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_automation_launch_debug.txt',
      );
      return opened == true;
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: JIT + RPCS3 foreground handoff failed for $titleId',
        error: error,
        stackTrace: stack,
      );
      return false;
    }
  }
}
