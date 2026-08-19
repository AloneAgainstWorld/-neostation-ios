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

  test('RPCS3 launch uses the basic Universal JIT handoff', () {
    final service = File(
      'lib/services/rpcs3_launch_service.dart',
    ).readAsStringSync();
    expect(service, contains('openJitRequest'));
    expect(service, contains("scriptName: 'universal.js'"));
    expect(service, contains('rpcs3_launch_debug.txt'));
    expect(service, isNot(contains('openAppAfterJitPreflight')));
    expect(service, isNot(contains('openUrlAfterJitPreflight')));
    expect(service, isNot(contains('buildRunUri')));
    expect(service, isNot(contains('rpcs3ShortcutName')));
  });

  test('RPCS3 experimental Shortcut helper keeps its historical name', () {
    expect(
      IosShortcutJitLaunchService.rpcs3ShortcutName,
      'NeoStation+RPCS3+Start',
    );

    final shortcutService = File(
      'lib/services/ios_shortcut_jit_launch_service.dart',
    ).readAsStringSync();
    expect(shortcutService, contains('shortcuts://create-shortcut'));
    expect(shortcutService, contains('openRpcs3ShortcutInstaller'));
  });

  test('RPCS3 documentation describes the stable basic launch', () {
    final doc = File(
      'docs/RPCS3_SHORTCUT_SWITCH_CONTROL.md',
    ).readAsStringSync();
    expect(doc, contains('stable basic launch'));
    expect(doc, contains('RPCS3 handles Start and game selection'));
    expect(doc, contains('disabled or removed'));
    expect(doc, contains('deep link'));
  });
}
