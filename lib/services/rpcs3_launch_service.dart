import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/logger_service.dart';

/// Stable RPCS3 iOS launcher.
///
/// NeoStation only performs the proven first-stage JIT handoff through
/// StikDebug. It does not schedule a delayed app foreground, invoke an Apple
/// Shortcut, depend on a Personal Automation, inject a second script,
/// fingerprint RPCS3Core, or call an internal RPCS3 boot function.
///
/// RPCS3 remains responsible for its native Start/Commencer screen and game
/// selection. This is deliberately the conservative fallback until RPCS3 (or
/// another PS3 emulator) exposes a supported deep link/App Intent/direct-launch
/// interface that NeoStation can call reliably.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';

  static final LoggerService _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  /// Kept as a no-op compatibility hook because older application startup
  /// code calls [initialize]. There is intentionally no lifecycle observer
  /// anymore: the old second-pass/direct-automation experiments are retired.
  static Future<void> initialize() async {}

  /// Opens StikDebug with its normal Universal JIT request for RPCS3.
  ///
  /// [displayTitle], [sourcePath], and [sourceKind] remain accepted so existing
  /// callers do not need special cases, but they are not injected into RPCS3.
  /// The selected Title ID is validated only for diagnostics/session tracking;
  /// RPCS3 itself remains responsible for pressing Start and choosing the game.
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
      'RPCS3 standard launch: titleId=$titleId '
      'title=${displayTitle?.trim() ?? ''} '
      'sourceKind=${sourceKind?.trim() ?? ''} '
      'sourcePath=${sourcePath?.trim() ?? ''}',
    );

    try {
      final opened = await ExternalFolderAccess.openJitRequest(
        targetBaseBundleId: targetBundleId,
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      return opened == true;
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: standard JIT handoff failed for $titleId',
        error: error,
        stackTrace: stack,
      );
      return false;
    }
  }
}
