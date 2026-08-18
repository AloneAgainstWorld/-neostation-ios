import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('all NeoStation audio clients use the central audio policy', () {
    final policy = File(
      'lib/services/audio_policy_service.dart',
    ).readAsStringSync();
    expect(policy, contains('class AudioPolicyService'));
    expect(policy, contains('ensureSilentCompatibleSession'));

    for (final file in <String>[
      'lib/services/sfx_service.dart',
      'lib/services/home_music_service.dart',
      'lib/services/music_player_service.dart',
      'lib/screens/game_screen/my_games_list/secondary_display.dart',
      'lib/screens/secondary_screen/secondary_screen.dart',
      'lib/widgets/shaders/shader_gif_widget.dart',
    ]) {
      expect(
        File(file).readAsStringSync(),
        contains('AudioPolicyService'),
        reason: file,
      );
    }
  });

  test('SFX retains and can stop active handles', () {
    final source = File('lib/services/sfx_service.dart').readAsStringSync();
    expect(source, contains('_activeHandles'));
    expect(source, contains('stopAllSounds'));
    expect(source, contains('getIsValidVoiceHandle'));
  });

  test('rapid SFX starts stay muted until ambient policy is reasserted', () {
    final source = File('lib/services/sfx_service.dart').readAsStringSync();

    expect(source, contains('_sfxStartSerial'));
    expect(source, contains('await stopAllSounds()'));
    expect(source, contains('volume: 0.0'));
    expect(source, contains('paused: true'));
    expect(source, contains('setPause(handle, false)'));
    expect(source, contains("reason: 'sfx-unpaused-zero-volume'"));
    expect(source, contains('setVolume(handle, _volume)'));

    final createMuted = source.indexOf('volume: 0.0');
    final unpause = source.indexOf('setPause(handle, false)');
    final finalPolicy = source.indexOf("reason: 'sfx-unpaused-zero-volume'");
    final audibleVolume = source.indexOf('setVolume(handle, _volume)');
    expect(createMuted, greaterThanOrEqualTo(0));
    expect(unpause, greaterThan(createMuted));
    expect(finalPolicy, greaterThan(unpause));
    expect(audibleVolume, greaterThan(finalPolicy));
  });
}
