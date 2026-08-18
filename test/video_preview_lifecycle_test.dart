import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'primary preview serializes replacement and rejects stale generations',
    () {
      final host = File('lib/screens/game_screen/my_games_list.dart')
          .readAsStringSync();
      final media = File(
        'lib/screens/game_screen/my_games_list/secondary_display.dart',
      ).readAsStringSync();
      expect(host, contains('_videoGeneration'));
      expect(host, contains('_videoTransition'));
      expect(media, contains('generation != _videoGeneration'));
      expect(media, contains('await controller.dispose()'));
      expect(media, contains("reason: 'replacement'"));
      expect(media, contains("reason: 'stale-initialize'"));
      expect(media, contains('await controller.setVolume(0.0)'));
    },
  );
}
