import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// State-driven RPCS3 iOS launcher for the exact inspected core builds.
///
/// StikDebug itself launches/attaches the target application. NeoStation no
/// longer schedules UIApplication opens from the background. Pass one runs the
/// Universal JIT script. Once RPCS3Core is initialized and NeoStation resumes,
/// pass two immediately attaches with a script that reads the core state,
/// dispatches the selected Title ID, captures the real return code and logs the
/// resulting state/progress/error.
abstract final class Rpcs3LaunchService {
  static const String targetBundleId = 'com.xitrix.RPCS3';

  static const Map<String, Map<String, int>> supportedCoreFunctions =
      <String, Map<String, int>>{
        'CFE15492152B331E83959A3CF9AC8A9F': <String, int>{'boot': 0x2fa18},
        '5C4D64FFB79930AD879C13009838F136': <String, int>{
          'boot': 0x36224,
          'emulationState': 0x36a8c,
          'bootProgress': 0x36afc,
          'globalState': 0x37a80,
          'lastError': 0x37f34,
        },
      };

  static const String currentCoreUuid = '5C4D64FF-B799-30AD-879C-13009838F136';
  static const int currentBootGameOffset = 0x36224;
  static const String expectedCoreUuid = currentCoreUuid;
  static const int bootGameOffset = currentBootGameOffset;

  static const String _assetPath = 'assets/data/rpcs3_stikdebug_launch.js';
  static const String _pendingRequestKey = 'rpcs3_pending_launch_request_v2';
  static const Duration _pendingLifetime = Duration(minutes: 10);

  static final LoggerService _log = LoggerService.instance;
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
  static String buildScriptForTesting(
    String template,
    String titleId, {
    String displayTitle = '',
    String sourcePath = '',
    String sourceKind = '',
    String sessionId = 'test-session',
  }) {
    final normalized = normalizeTitleId(titleId);
    if (normalized == null)
      throw const FormatException('Invalid RPCS3 title ID.');
    final request = <String, String>{
      'titleId': normalized,
      'displayTitle': displayTitle,
      'sourcePath': sourcePath,
      'sourceKind': sourceKind,
      'sessionId': sessionId,
    };
    return template
        .replaceAll('__NEOSTATION_REQUEST_JSON__', jsonEncode(request))
        .replaceAll(
          '__NEOSTATION_SUPPORTED_CORES_JSON__',
          jsonEncode(supportedCoreFunctions),
        );
  }

  @visibleForTesting
  static bool shouldContinuePendingForTesting({
    required DateTime now,
    required DateTime startedAt,
    required bool launchWasBackgrounded,
  }) {
    final age = now.difference(startedAt);
    return launchWasBackgrounded && !age.isNegative && age <= _pendingLifetime;
  }

  static Future<bool> launchTitle(
    String? rawTitleId, {
    String? displayTitle,
    String? sourcePath,
    String? sourceKind,
  }) async {
    final titleId = normalizeTitleId(rawTitleId);
    if (titleId == null || !Platform.isIOS) return false;
    await initialize();

    final now = DateTime.now();
    final request = <String, dynamic>{
      'titleId': titleId,
      'displayTitle': displayTitle?.trim() ?? '',
      'sourcePath': sourcePath?.trim() ?? '',
      'sourceKind': sourceKind?.trim() ?? '',
      'sessionId': '${now.millisecondsSinceEpoch}-$titleId',
      'startedMs': now.millisecondsSinceEpoch,
    };

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_pendingRequestKey, jsonEncode(request));
      _launchWasBackgrounded = false;
      _continuationInFlight = false;
      await _writeLaunchState('FIRST_PASS_REQUESTED', request: request);

      final opened = await ExternalFolderAccess.openJitRequest(
        targetBaseBundleId: targetBundleId,
        scriptName: 'universal.js',
        debugFileName: 'rpcs3_launch_debug.txt',
      );
      if (opened == true) return true;

      await _clearPendingLaunch(reason: 'FIRST_PASS_FAILED');
      return false;
    } catch (error, stack) {
      await _clearPendingLaunch(reason: 'FIRST_PASS_EXCEPTION');
      _log.e(
        'Rpcs3LaunchService: could not start title $titleId',
        error: error,
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
    final request = await _loadPendingRequest();
    if (request == null) return;

    final startedAt = DateTime.fromMillisecondsSinceEpoch(
      request['startedMs'] as int,
    );
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
      final script = buildScriptForTesting(
        template,
        request['titleId'] as String,
        displayTitle: request['displayTitle'] as String,
        sourcePath: request['sourcePath'] as String,
        sourceKind: request['sourceKind'] as String,
        sessionId: request['sessionId'] as String,
      );
      final scriptData = base64Url
          .encode(utf8.encode(script))
          .replaceAll('=', '');
      await _writeLaunchState('SECOND_PASS_REQUESTED', request: request);

      final opened = await ExternalFolderAccess.openJitRequest(
        targetBaseBundleId: targetBundleId,
        scriptName: 'neostation-rpcs3-stateful.js',
        scriptDataBase64Url: scriptData,
        debugFileName: 'rpcs3_launch_second_pass_debug.txt',
      );
      await _writeLaunchState(
        opened == true ? 'SECOND_PASS_OPENED' : 'SECOND_PASS_FAILED',
        request: request,
      );
    } catch (error, stack) {
      _log.e(
        'Rpcs3LaunchService: stateful second pass failed',
        error: error,
        stackTrace: stack,
      );
      await _writeLaunchState(
        'SECOND_PASS_EXCEPTION',
        request: request,
        extra: error.toString(),
      );
    } finally {
      await _clearPendingLaunch(reason: 'SECOND_PASS_FINISHED');
      _continuationInFlight = false;
    }
  }

  static Future<Map<String, dynamic>?> _loadPendingRequest() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_pendingRequestKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      final request = Map<String, dynamic>.from(decoded);
      final titleId = normalizeTitleId(request['titleId']?.toString());
      final startedMs = int.tryParse(request['startedMs']?.toString() ?? '');
      if (titleId == null || startedMs == null) return null;
      request['titleId'] = titleId;
      request['startedMs'] = startedMs;
      request['displayTitle'] = request['displayTitle']?.toString() ?? '';
      request['sourcePath'] = request['sourcePath']?.toString() ?? '';
      request['sourceKind'] = request['sourceKind']?.toString() ?? '';
      request['sessionId'] = request['sessionId']?.toString() ?? '';
      return request;
    } catch (_) {
      return null;
    }
  }

  static Future<void> _discardExpiredPendingLaunch() async {
    final request = await _loadPendingRequest();
    if (request == null) return;
    final startedAt = DateTime.fromMillisecondsSinceEpoch(
      request['startedMs'] as int,
    );
    if (DateTime.now().difference(startedAt) > _pendingLifetime) {
      await _clearPendingLaunch(reason: 'STARTUP_PENDING_EXPIRED');
    }
  }

  static Future<void> _clearPendingLaunch({required String reason}) async {
    try {
      final request = await _loadPendingRequest();
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_pendingRequestKey);
      await _writeLaunchState(reason, request: request);
    } catch (_) {}
  }

  static Future<void> _writeLaunchState(
    String state, {
    Map<String, dynamic>? request,
    String? extra,
  }) async {
    final line = <String>[
      '${DateTime.now().toIso8601String()} STATE=$state',
      if (request != null) 'session=${request['sessionId']}',
      if (request != null) 'titleId=${request['titleId']}',
      if (request != null) 'title=${request['displayTitle']}',
      if (request != null) 'sourceKind=${request['sourceKind']}',
      if (request != null) 'sourcePath=${request['sourcePath']}',
      if (extra != null) 'extra=$extra',
    ].join(' | ');
    _log.i('RPCS3 launch protocol: $line');
    try {
      final documents = await getApplicationDocumentsDirectory();
      await File(
        path.join(documents.path, 'rpcs3_launch_protocol_debug.txt'),
      ).writeAsString('$line\n', mode: FileMode.append, flush: true);
    } catch (_) {}
  }
}

final class _Rpcs3ResumeObserver with WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    Rpcs3LaunchService.handleLifecycleState(state);
  }
}
