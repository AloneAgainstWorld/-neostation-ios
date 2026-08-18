import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/ios_shortcut_jit_launch_service.dart';
import 'package:neostation/services/logger_service.dart';

/// Stable RPCS3 iOS launcher.
///
/// NeoStation starts RPCS3's normal StikDebug Universal JIT flow, then the
/// native iOS helper keeps a short background task alive and invokes the
/// user-configured `NeoStation+RPCS3+Start` Shortcut after the JIT warm-up.
/// The Shortcut owns the device-local Switch Control gesture that presses
/// RPCS3's native Start/Commencer control.
///
/// This keeps the RPCS3Core memory-injection / second-pass protocol retired
/// while directly linking NeoStation to the Shortcut. A separate Personal
/// Automation triggered by RPCS3 opening is no longer required.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';
  static const Duration _shortcutWarmupDelay = Duration(seconds: 8);

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

  /// Starts StikDebug with the normal Universal JIT request for RPCS3 and then
  /// invokes `NeoStation+RPCS3+Start` through Apple's Shortcuts URL scheme.
  ///
  /// The native preflight helper schedules the Shortcut handoff rather than a
  /// Dart timer so the handoff still has a chance to run after NeoStation has
  /// moved to the background. The selected Title ID is passed as text input for
  /// diagnostics/future Shortcut revisions; the current helper may ignore it.
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
      'RPCS3 Shortcut launch: titleId=$titleId '
      'title=${displayTitle?.trim() ?? ''} '
      'sourceKind=${sourceKind?.trim() ?? ''} '
      'sourcePath=${sourcePath?.trim() ?? ''}',
    );

    final shortcutUri = IosShortcutJitLaunchService.buildRunUri(
      shortcutName: IosShortcutJitLaunchService.rpcs3ShortcutName,
      input: titleId,
    );

    try {
      final opened = await ExternalFolderAccess.openUrlAfterJitPreflight(
        shortcutUri.toString(),
        targetBaseBundleId: targetBundleId,
        warmupDelay: _shortcutWarmupDelay,
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_shortcut_launch_debug.txt',
      );
      return opened == true;
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: JIT + Shortcut handoff failed for $titleId',
        error: error,
        stackTrace: stack,
      );
      return false;
    }
  }
}
