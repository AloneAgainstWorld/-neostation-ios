import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/rpcs3_launch_service.dart';

void main() {
  test('existing synthetic RPCS3 metadata resolves to PARAM.SFO title', () {
    final resolved = GameModel.resolveDatabaseNamesForDisplay(
      DatabaseGameModel(
        filename: 'BLES00412',
        romPath: 'rpcs3-library://game?title-id=BLES00412',
        titleId: 'BLES00412',
        titleName: 'The Lord of the Rings: Conquest™',
        realName: 'BLES00412',
        screenscraperRealName: 'BLES00412',
      ),
    );
    expect(resolved.displayName, 'The Lord of the Rings: Conquest™');
    expect(resolved.realName, 'The Lord of the Rings: Conquest™');
    expect(resolved.hasMeaningfulScrapedName, isFalse);
  });

  test(
    'RPCS3 protocol is immediate and records real return/state diagnostics',
    () {
      final service = File('lib/services/rpcs3_launch_service.dart')
          .readAsStringSync();
      final script = File('assets/data/rpcs3_stikdebug_launch.js')
          .readAsStringSync();
      expect(service, contains('openJitRequest'));
      expect(service, isNot(contains('warmupDelay:')));
      expect(script, contains('NEOSTATION_RPC_STATE_BEFORE'));
      expect(script, contains('NEOSTATION_RPC_BOOT_RESULT'));
      expect(script, contains('NEOSTATION_RPC_LAST_ERROR'));
      expect(script, contains('NEOSTATION_RPC_PROGRESS_AFTER'));
      expect(script, contains('p0;thread:'));
    },
  );

  test('generated script contains the inspected RPCS3 0.2 function map', () {
    final template = File('assets/data/rpcs3_stikdebug_launch.js')
        .readAsStringSync();
    final script = Rpcs3LaunchService.buildScriptForTesting(
      template,
      'BLES00412',
      displayTitle: 'The Lord of the Rings: Conquest™',
      sourcePath: '/Data/games/discImgs/BLES00412',
      sourceKind: 'disc-image',
      sessionId: 'session-1',
    );
    expect(script, contains('223884'));
    expect(script, contains('223996'));
    expect(script, contains('227968'));
    expect(script, contains('229172'));
    expect(script, isNot(contains('__NEOSTATION_')));
  });
}
