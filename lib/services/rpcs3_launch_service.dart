import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Experimental RPCS3 iOS launcher for the exact RPCS3 build inspected by the
/// NeoStation project.
///
/// iOS suspends long timers once NeoStation leaves the foreground, so the old
/// timed two-pass sequence could never reliably reach its second StikDebug
/// request. Stage 6 makes the handoff deterministic:
///
/// 1. NeoStation enables Universal JIT and opens RPCS3.
/// 2. The user presses RPCS3's native Start button.
/// 3. The user returns once to NeoStation.
/// 4. NeoStation's real `resumed` lifecycle event immediately launches the
///    fingerprinted direct-title StikDebug pass and then returns to RPCS3.
///
/// This intentionally adds one app-switch while proving the private boot call
/// reliably before a future Shortcut is allowed to automate the same resume.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';
  static const String expectedCoreUuid = 'CFE15492-152B-331E-8395-9A3CF9AC8A9F';
  static const int bootGameOffset = 0x2fa18;
  static const String _assetPath = 'assets/data/rpcs3_stikdebug_launch.js';
  static const String _pendingTitleKey = 'rpcs3_pending_launch_title';
  static const String _pendingStartedKey = 'rpcs3_pending_launch_started_ms';
  static const Duration _minimumReturnDelay = Duration(seconds: 8);
  static const Duration _pendingLifetime = Duration(minutes: 10);

  static final _log = LoggerService.instance;
  static final RegExp _titleIdPattern = RegExp(r'^[A-Z0-9._-]{3,32}$');
  static _Rpcs3ResumeObserver? _observer;
  static bool _continuationInFlight = false;
  static bool _launchWasBackgrounded = false;

  static String? normalizeTitleId(String? value) {
    final titleId = value?.trim().toUpperCase() ?? '';
    return _titleIdPattern.hasMatch(titleId) ? titleId : null;
  }

  static Future<void> initialize() async {
    if (!Platform.isIOS || _observer != null) return;
    _observer = _Rpcs3ResumeObserver();
    WidgetsBinding.instance.addObserver(_observer!);
    await _discardExpiredPendingLaunch();
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

  @visibleForTesting
  static bool shouldContinuePendingForTesting({
    required DateTime now,
    required DateTime startedAt,
    required bool launchWasBackgrounded,
  }) {
    final age = now.difference(startedAt);
    return launchWasBackgrounded &&
        age >= _minimumReturnDelay &&
        age <= _pendingLifetime;
  }

  static Future<bool> launchTitle(String? rawTitleId) async {
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null || !Platform.isIOS) return false;
    await initialize();

    try {
      final prefs = await SharedPreferences.getInstance();
      final now = DateTime.now();
      await prefs.setString(_pendingTitleKey, titleId);
      await prefs.setInt(_pendingStartedKey, now.millisecondsSinceEpoch);
      _launchWasBackgrounded = false;
      _continuationInFlight = false;
      await _writeLaunchState(
        'FIRST_PASS_REQUESTED',
        titleId: titleId,
        extra: 'Return to NeoStation once after pressing Start in RPCS3.',
      );

      // This first-pass path is already proven on-device: StikDebug Universal
      // prepares JIT, and the native helper opens RPCS3 after the warm-up.
      final opened = await ExternalFolderAccess.openAppAfterJitPreflight(
        targetBaseBundleId: targetBundleId,
        warmupDelay: const Duration(seconds: 11),
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      if (opened == true) return true;

      await _clearPendingLaunch(reason: 'FIRST_PASS_FAILED');
      return false;
    } catch (e, stack) {
      await _clearPendingLaunch(reason: 'FIRST_PASS_EXCEPTION');
      _log.e(
        'Rpcs3LaunchService: could not start title $titleId',
        error: e,
        stackTrace: stack,
      );
      return false;
    }
  }

  static void handleLifecycleState(AppLifecycleState state) {
    if (!Platform.isIOS) return;
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.inactive) {
      _launchWasBackgrounded = true;
      return;
    }
    if (state == AppLifecycleState.resumed) {
      unawaited(_continuePendingLaunchOnResume());
    }
  }

  static Future<void> _continuePendingLaunchOnResume() async {
    if (_continuationInFlight || !_launchWasBackgrounded) return;

    final prefs = await SharedPreferences.getInstance();
    final titleId = normalizeTitleId(prefs.getString(_pendingTitleKey));
    final startedMs = prefs.getInt(_pendingStartedKey);
    if (titleId == null || startedMs == null) return;

    final startedAt = DateTime.fromMillisecondsSinceEpoch(startedMs);
    final now = DateTime.now();
    if (!shouldContinuePendingForTesting(
      now: now,
      startedAt: startedAt,
      launchWasBackgrounded: _launchWasBackgrounded,
    )) {
      if (now.difference(startedAt) > _pendingLifetime) {
        await _clearPendingLaunch(reason: 'PENDING_EXPIRED');
      }
      return;
    }

    _continuationInFlight = true;
    _launchWasBackgrounded = false;
    try {
      final template = await rootBundle.loadString(_assetPath);
      final script = buildScriptForTesting(template, titleId);
      final scriptData = base64Url
          .encode(utf8.encode(script))
          .replaceAll('=', '');
      await _writeLaunchState(
        'SECOND_PASS_REQUESTED',
        titleId: titleId,
        extra: 'NeoStation resumed after RPCS3 Start.',
      );

      // One short background return is much more reliable than the old chain
      // of 10+10+6 second timers. The second StikDebug request is initiated
      // while NeoStation is actually foregrounded.
      final opened = await ExternalFolderAccess.openAppAfterJitPreflight(
        targetBaseBundleId: targetBundleId,
        warmupDelay: const Duration(seconds: 5),
        scriptName: 'neostation-rpcs3-direct.js',
        scriptDataBase64Url: scriptData,
        debugFileName: 'rpcs3_launch_second_pass_debug.txt',
      );
      await _writeLaunchState(
        opened == true ? 'SECOND_PASS_OPENED' : 'SECOND_PASS_FAILED',
        titleId: titleId,
      );
    } catch (e, stack) {
      _log.e(
        'Rpcs3LaunchService: second pass failed for $titleId',
        error: e,
        stackTrace: stack,
      );
      await _writeLaunchState(
        'SECOND_PASS_EXCEPTION',
        titleId: titleId,
        extra: e.toString(),
      );
    } finally {
      await _clearPendingLaunch(reason: 'SECOND_PASS_FINISHED');
      _continuationInFlight = false;
    }
  }

  static Future<void> _discardExpiredPendingLaunch() async {
    final prefs = await SharedPreferences.getInstance();
    final startedMs = prefs.getInt(_pendingStartedKey);
    if (startedMs == null) return;
    final age = DateTime.now().difference(
      DateTime.fromMillisecondsSinceEpoch(startedMs),
    );
    if (age > _pendingLifetime) {
      await _clearPendingLaunch(reason: 'STARTUP_PENDING_EXPIRED');
    }
  }

  static Future<void> _clearPendingLaunch({required String reason}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_pendingTitleKey);
      await prefs.remove(_pendingStartedKey);
      await _writeLaunchState(reason);
    } catch (_) {}
  }

  static Future<void> _writeLaunchState(
    String state, {
    String? titleId,
    String? extra,
  }) async {
    try {
      final directory = await Directory.systemTemp.createTemp();
      // The native JIT helper writes the detailed user-visible file in
      // Documents. Dart logging here deliberately stays lightweight.
      await directory.delete(recursive: true);
      _log.i(
        'RPCS3 launch state: $state'
        '${titleId == null ? '' : ' title=$titleId'}'
        '${extra == null ? '' : ' $extra'}',
      );
    } catch (_) {}
  }
}

final class _Rpcs3ResumeObserver with WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    Rpcs3LaunchService.handleLifecycleState(state);
  }
}
