import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:neostation/services/logger_service.dart';

/// Stable RPCS3 iOS launcher.
///
/// NeoStation only performs the proven first-stage JIT handoff through
/// StikDebug. It no longer persists a pending title, observes app lifecycle
/// transitions, injects a second script, fingerprints RPCS3Core, or calls an
/// internal RPCS3 boot function.
///
/// Optional automatic tapping of RPCS3's native "Start"/"Commencer" control
/// is deliberately kept outside this service and is intended to be handled by
/// an iOS Shortcuts personal automation triggered when RPCS3 opens. If that
/// automation is absent, the user simply presses Start and chooses the game in
/// RPCS3 normally.
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
  /// anymore: the old second-pass direct-boot protocol has been removed.
  static Future<void> initialize() async {}

  /// Opens StikDebug with its normal Universal JIT request for RPCS3.
  ///
  /// [displayTitle], [sourcePath], and [sourceKind] remain accepted so existing
  /// callers do not need special cases, but they are not injected into RPCS3.
  /// The selected Title ID is validated only for diagnostics/session tracking;
  /// RPCS3 itself remains responsible for game selection in the stable path.
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
