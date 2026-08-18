import 'dart:async';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/widgets.dart';

import 'logger_service.dart';

/// Central owner of NeoStation's native audio-session policy.
///
/// iOS deliberately does not expose a public API that reports the hardware
/// Ring/Silent switch. The supported way to honour it is to keep the entire app
/// on an `AVAudioSession.Category.ambient` session. Every audio backend in
/// NeoStation calls this service after it creates, reloads or starts a player,
/// preventing SoLoud or AVPlayer from silently replacing the shared session
/// with a category that ignores the switch.
class AudioPolicyService with WidgetsBindingObserver {
  AudioPolicyService._internal();

  static final AudioPolicyService _instance = AudioPolicyService._internal();
  factory AudioPolicyService() => _instance;

  final LoggerService _log = LoggerService.instance;

  bool _initialized = false;
  Future<void> _serial = Future<void>.value();
  int _applicationCount = 0;

  bool get isInitialized => _initialized;
  int get applicationCountForTesting => _applicationCount;

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    WidgetsBinding.instance.addObserver(this);
    await ensureSilentCompatibleSession(reason: 'application-start');
  }

  /// Reasserts the single native session policy in a serialized queue.
  ///
  /// Serializing these calls matters because SoLoud asset loads and AVPlayer
  /// initialization can complete concurrently during rapid menu navigation.
  Future<void> ensureSilentCompatibleSession({required String reason}) {
    if (!Platform.isIOS) return Future<void>.value();

    final completer = Completer<void>();
    _serial = _serial.catchError((Object _) {}).then((_) async {
      try {
        final applied =
            await ExternalFolderAccess.configureAudioSessionForSilentMode();
        if (applied != true) {
          _log.w(
            '[AudioPolicy] Native ambient session was not applied: $reason',
          );
        } else {
          _applicationCount++;
        }
        completer.complete();
      } catch (error, stack) {
        _log.e(
          '[AudioPolicy] Failed to apply ambient session: $reason',
          error: error,
          stackTrace: stack,
        );
        completer.complete();
      }
    });
    return completer.future;
  }

  Future<void> prepareForPlayback(String client) =>
      ensureSilentCompatibleSession(reason: '$client:prepare');

  Future<void> afterPlaybackStarted(String client) =>
      ensureSilentCompatibleSession(reason: '$client:started');

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(ensureSilentCompatibleSession(reason: 'application-resumed'));
    }
  }
}
