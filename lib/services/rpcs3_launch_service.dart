import 'dart:convert';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:neostation/services/logger_service.dart';

/// Experimental RPCS3 iOS launcher for the exact RPCS3 build inspected by the
/// NeoStation project.
///
/// RPCS3 currently has no public game deeplink. This launcher therefore asks
/// StikDebug to run a derivative of its Universal script. The script remains
/// attached across RPCS3's native Start gate, waits for the fingerprinted core
/// to load, then calls `rpcs3_ios_boot_game(title_id)`, restores the stopped
/// thread's register state and detaches. The user may still need to press Start,
/// but no second game selection should be required.
///
/// The UUID/offset guard makes the experiment fail closed when RPCS3 changes.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';
  static const String expectedCoreUuid = 'CFE15492-152B-331E-8395-9A3CF9AC8A9F';
  static const int bootGameOffset = 0x2fa18;
  static const String _assetPath = 'assets/data/rpcs3_stikdebug_launch.js';

  static final _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  @visibleForTesting
  static String buildScriptForTesting(String template, String titleId) {
    final normalized = normalizeTitleId(titleId);
    if (normalized == null) {
      throw const FormatException('Invalid RPCS3 title ID.');
    }
    return template
        .replaceAll('__NEOSTATION_TITLE_ID_JSON__', jsonEncode(normalized))
        .replaceAll(
          '__NEOSTATION_CORE_UUID_JSON__',
          jsonEncode(expectedCoreUuid),
        )
        .replaceAll(
          '__NEOSTATION_BOOT_OFFSET_HEX__',
          bootGameOffset.toRadixString(16),
        );
  }

  static Future<bool> launchTitle(String? rawTitleId) async {
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null) return false;

    try {
      final template = await rootBundle.loadString(_assetPath);
      final script = buildScriptForTesting(template, titleId);
      final scriptData = base64Url
          .encode(utf8.encode(script))
          .replaceAll('=', '');

      final opened = await ExternalFolderAccess.openAppAfterJitPreflight(
        targetBaseBundleId: targetBundleId,
        warmupDelay: const Duration(seconds: 14),
        scriptName: 'neostation-rpcs3.js',
        scriptDataBase64Url: scriptData,
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      return opened == true;
    } catch (e, stack) {
      _log.e(
        'Rpcs3LaunchService: could not start title $titleId',
        error: e,
        stackTrace: stack,
      );
      return false;
    }
  }
}
