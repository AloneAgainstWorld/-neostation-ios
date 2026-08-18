from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'test/rpcs3_stage3_test.dart'
text = path.read_text(encoding='utf-8')
old = '''    test('RPCS3 direct script is fingerprinted and state-aware', () {
      final template = File('assets/data/rpcs3_stikdebug_launch.js')
          .readAsStringSync();
      final script = Rpcs3LaunchService.buildScriptForTesting(
        template,
        'bles00412',
      );
      expect(script, contains('"BLES00412"'));
      expect(script, contains('5C4D64FFB79930AD879C13009838F136'));
      expect(script, contains('221732'));
      expect(script, contains('CFE15492152B331E83959A3CF9AC8A9F'));
      expect(script, contains('NEOSTATION_RPC_STATE_BEFORE'));
      expect(script, contains('NEOSTATION_RPC_BOOT_RESULT'));
      expect(script, contains('NEOSTATION_RPC_LAST_ERROR'));
      expect(script, isNot(contains('__NEOSTATION_')));
    });

'''
new = '''    test('RPCS3 launch keeps only the stable single-pass JIT path', () {
      final source = File('lib/services/rpcs3_launch_service.dart')
          .readAsStringSync();
      expect(source, contains('SINGLE_PASS_JIT'));
      expect(source, contains('openJitRequest'));
      expect(source, isNot(contains('supportedCoreFunctions')));
      expect(source, isNot(contains('SECOND_PASS')));
      expect(source, isNot(contains('buildScriptForTesting')));
      expect(File('assets/data/rpcs3_stikdebug_launch.js').existsSync(), isFalse);
    });

'''
if text.count(old) != 1:
    raise SystemExit('Expected obsolete direct-script test exactly once')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('Stage3 direct-script regression retired for Build 140.')
