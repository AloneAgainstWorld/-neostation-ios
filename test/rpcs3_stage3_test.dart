import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_database_service.dart';
import 'package:neostation/l10n/rpcs3_library_locale.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';
import 'package:neostation/services/screenscraper/media_downloader.dart';
import 'package:neostation/services/screenscraper_service.dart';

void main() {
  group('RPCS3 persistence, media and launch', () {
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

    test('all URI-backed emulator rows survive physical scans', () {
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath(
          'rpcs3-library://game?title-id=BLES00113',
        ),
        isTrue,
      );
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath('melonx://game'),
        isTrue,
      );
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath('armsx2://game'),
        isTrue,
      );
      expect(
        SqliteDatabaseService.isPersistentExternalLibraryPath('/roms/game.iso'),
        isFalse,
      );
    });

    test('ScreenScraper text statuses are rejected as media', () {
      for (final status in ['NOMEDIA', 'CRCOK', 'MD5OK', 'SHA1OK']) {
        expect(
          ScreenscraperMediaDownloader.isValidMediaPayload(
            utf8.encode(status),
            mediaType: 'video',
          ),
          isFalse,
        );
      }
    });

    test('MP4 and PNG signatures are accepted', () {
      expect(
        ScreenscraperMediaDownloader.isValidMediaPayload(const [
          0,
          0,
          0,
          24,
          0x66,
          0x74,
          0x79,
          0x70,
          0x69,
          0x73,
          0x6f,
          0x6d,
        ], mediaType: 'video'),
        isTrue,
      );
      expect(
        ScreenscraperMediaDownloader.isValidMediaPayload(const [
          0x89,
          0x50,
          0x4e,
          0x47,
          0x0d,
          0x0a,
          0x1a,
          0x0a,
        ], mediaType: 'box2D'),
        isTrue,
      );
    });

    test('RPCS3 launch script waits through the native Start gate', () {
      final template = File('assets/data/rpcs3_stikdebug_launch.js')
          .readAsStringSync();
      final script = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00113',
      );
      expect(script, contains('"BLES00113"'));
      expect(script, contains(Rpcs3LaunchService.expectedCoreUuid));
      expect(script, contains('NEOSTATION_RPC_WAITING_FOR_START'));
      expect(script, contains('NEOSTATION_RPC_CORE_DISCOVERED'));
      expect(script, contains('NEOSTATION_RPC_BOOT_COMPLETED'));
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
          screenscraperRealName: 'Bladestorm: The Hundred Years’ War',
        ),
      );
      expect(game.name, 'Bladestorm: The Hundred Years’ War');
      expect(game.realname, 'Bladestorm: The Hundred Years’ War');
      expect(game.titleId, 'BLES00113');
    });

    test('French RPCS3 status uses natural singular and plural', () {
      expect(
        Rpcs3LibraryLocale.statusSyncedForLocale('fr', 1),
        'RPCS3 synchronisé — 1 jeu PS3.',
      );
      expect(
        Rpcs3LibraryLocale.statusSyncedForLocale('fr', 2),
        'RPCS3 synchronisé — 2 jeux PS3.',
      );
    });
  });
}
