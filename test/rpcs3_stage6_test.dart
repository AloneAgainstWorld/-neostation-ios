import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:neostation/services/rpcs3_title_catalog_service.dart';

void main() {
  group('RPCS3 Stage 6 reliability', () {
    test(
      'cached raw serial receives GameDB title even without live folder',
      () async {
        final enriched = await Rpcs3LibraryService.applyTitleCatalogForTesting(
          const <Rpcs3LibraryGame>[
            Rpcs3LibraryGame(
              titleId: 'BLES00412',
              title: 'BLES00412',
              version: '',
              category: '',
              sourcePath: '/unavailable/RPCS3/Data/game.iso',
              sourceKind: 'games.yml',
            ),
          ],
          const <String, String>{
            'BLES00412': 'The Lord of the Rings: Conquest',
          },
        );
        expect(enriched.single.title, 'The Lord of the Rings: Conquest');
      },
    );

    test('GameDB normalization accepts dashed PS3 serials', () {
      expect(
        Rpcs3TitleCatalogService.normalizeTitleId('BLES-00412'),
        'BLES00412',
      );
    });

    test(
      'resume pass arms from a real background transition without a timer',
      () {
        final started = DateTime.utc(2026, 8, 18, 12);
        expect(
          Rpcs3LaunchService.shouldContinuePendingForTesting(
            now: started.add(const Duration(seconds: 3)),
            startedAt: started,
            launchWasBackgrounded: true,
          ),
          isTrue,
        );
        expect(
          Rpcs3LaunchService.shouldContinuePendingForTesting(
            now: started.add(const Duration(seconds: 12)),
            startedAt: started,
            launchWasBackgrounded: true,
          ),
          isTrue,
        );
        expect(
          Rpcs3LaunchService.shouldContinuePendingForTesting(
            now: started.add(const Duration(seconds: 12)),
            startedAt: started,
            launchWasBackgrounded: false,
          ),
          isFalse,
        );
      },
    );

    test('direct-launch template receives exact request and function map', () {
      const template =
          'request=__NEOSTATION_REQUEST_JSON__ '
          'cores=__NEOSTATION_SUPPORTED_CORES_JSON__';
      final rendered = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00412',
      );
      expect(rendered, contains(jsonEncode('BLES00412')));
      expect(rendered, contains('5C4D64FFB79930AD879C13009838F136'));
      expect(rendered, isNot(contains('__NEOSTATION_')));
    });
  });
}
