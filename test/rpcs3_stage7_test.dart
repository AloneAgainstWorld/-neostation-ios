import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/database_game_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/ios_shortcut_jit_launch_service.dart';

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

  test('RPCS3 launch foregrounds the app after Universal JIT', () {
    final service = File(
      'lib/services/rpcs3_launch_service.dart',
    ).readAsStringSync();
    expect(service, contains('openAppAfterJitPreflight'));
    expect(service, contains("scriptName: 'universal.js'"));
    expect(service, contains('_rpcs3WarmupDelay'));
    expect(service, contains('rpcs3_automation_launch_debug.txt'));
    expect(service, isNot(contains('buildRunUri')));
    expect(service, isNot(contains('rpcs3ShortcutName')));
    expect(service, isNot(contains('openUrlAfterJitPreflight('));
    expect(service, isNot(contains('openJitRequest')));
    expect(service, isNot(contains('rpcs3_stikdebug_launch.js')));
    expect(service, isNot(contains('bootGameOffset')));
    expect(service, isNot(contains('expectedCoreUuid')));
    expect(service, isNot(contains('SECOND_PASS')));
  });

  test('RPCS3 Shortcut setup keeps the exact helper name', () {
    expect(
      IosShortcutJitLaunchService.rpcs3ShortcutName,
      'NeoStation+RPCS3+Start',
    );

    final shortcutService = File(
      'lib/services/ios_shortcut_jit_launch_service.dart',
    ).readAsStringSync();
    expect(shortcutService, contains('shortcuts://create-shortcut'));
    expect(shortcutService, contains('openRpcs3ShortcutInstaller'));
    expect(shortcutService, contains('Personal Automation'));
  });

  test('RPCS3 Switch Control documentation requires app-open automation', () {
    final doc = File(
      'docs/RPCS3_SHORTCUT_SWITCH_CONTROL.md',
    ).readAsStringSync();
    expect(doc, contains('NeoStation+RPCS3+Start'));
    expect(doc, contains('NeoStation RPCS3'));
    expect(doc, contains('Full Screen'));
    expect(doc, contains('Personal Automation'));
    expect(doc, contains('Run Immediately'));
    expect(doc, contains('Do **not** add **Open App -> RPCS3**'));
  });

  test('obsolete RPCS3 direct injection asset is removed', () {
    expect(File('assets/data/rpcs3_stikdebug_launch.js').existsSync(), isFalse);
  });
}
