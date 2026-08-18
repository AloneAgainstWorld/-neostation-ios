import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';
import 'package:neostation/services/screenscraper_service.dart';

void main() {
  group('RPCS3 stage 3', () {
    test('ScreenScraper lookup carries the PS3 serial number', () {
      final params = ScreenScraperService.buildGameLookupParametersForTesting(
        systemId: '59',
        romName: 'BLES00113',
        serialNumber: ' BLES00113 ',
      );
      expect(params['systemeid'], '59');
      expect(params['romnom'], 'BLES00113');
      expect(params['serialnum'], 'BLES00113');
    });

    test('RPCS3 launch script is fingerprinted and title-specific', () {
      const template =
          'id=__NEOSTATION_TITLE_ID_JSON__; '
          'uuid=__NEOSTATION_CORE_UUID_JSON__; '
          'offset=0x__NEOSTATION_BOOT_OFFSET_HEX__';
      final script = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00113',
      );
      expect(script, contains('"BLES00113"'));
      expect(script, contains(Rpcs3LaunchService.expectedCoreUuid));
      expect(
        script,
        contains(Rpcs3LaunchService.bootGameOffset.toRadixString(16)),
      );
      expect(script, isNot(contains('__NEOSTATION_')));
    });

    test('invalid RPCS3 title IDs are rejected', () {
      expect(Rpcs3LaunchService.normalizeTitleId('../bad'), isNull);
      expect(Rpcs3LaunchService.normalizeTitleId('BLES00113'), 'BLES00113');
    });

    test('scraped RPCS3 name replaces the raw Title ID', () {
      final game = GameModel.fromDatabaseModel(
        DatabaseGameModel(
          filename: 'BLES00113',
          romPath: 'rpcs3-library://game?title-id=BLES00113',
          titleId: 'BLES00113',
          titleName: 'BLES00113',
          screenscraperRealName: 'LittleBigPlanet',
        ),
      );

      expect(game.name, 'LittleBigPlanet');
      expect(game.realname, 'LittleBigPlanet');
      expect(game.titleId, 'BLES00113');
    });

    test('regular games keep their internal-title precedence', () {
      final game = GameModel.fromDatabaseModel(
        DatabaseGameModel(
          filename: 'game.iso',
          romPath: '/roms/ps3/game.iso',
          titleName: 'Internal Header Title',
          screenscraperRealName: 'Scraped Name',
        ),
      );

      expect(game.name, 'Internal Header Title');
    });
  });
}
