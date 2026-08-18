import 'package:flutter_test/flutter_test.dart';
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
  });
}
