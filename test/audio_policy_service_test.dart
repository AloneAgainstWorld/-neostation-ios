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
}
