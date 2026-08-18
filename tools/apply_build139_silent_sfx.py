from pathlib import Path

sfx_path = Path('lib/services/sfx_service.dart')
sfx = sfx_path.read_text(encoding='utf-8')

handles_anchor = """  final List<SoundHandle> _activeHandles = <SoundHandle>[];\n\n"""
serial_field = """  /// Serializes every UI voice start. Rapid input can otherwise create two\n  /// SoLoud voices while the iOS audio session is being reasserted, leaving a\n  /// tiny audible window under the wrong session category.\n  Future<void> _sfxStartSerial = Future<void>.value();\n\n"""
if '_sfxStartSerial' not in sfx:
    if handles_anchor not in sfx:
        raise SystemExit('SFX active-handles anchor not found')
    sfx = sfx.replace(handles_anchor, handles_anchor + serial_field, 1)

old_play = """  /// Initiates playback for a pre-loaded source identified by its [path].\n  Future<void> _play(String path) async {\n    final source = _sources[path];\n    if (source == null) {\n      _log.w('[SfxService] Source not found for: $path');\n      return;\n    }\n    try {\n      await AudioPolicyService().prepareForPlayback('sfx');\n      final handle = SoLoud.instance.play(source, volume: _volume);\n      _activeHandles.add(handle);\n      _activeHandles.removeWhere(\n        (candidate) => !SoLoud.instance.getIsValidVoiceHandle(candidate),\n      );\n      await AudioPolicyService().afterPlaybackStarted('sfx');\n    } catch (e) {\n      _log.w('[SfxService] Playback error for $path: $e');\n    }\n  }\n"""

new_play = """  /// Initiates playback for a pre-loaded source identified by its [path].\n  ///\n  /// The complete voice-start transaction is serialized. More importantly, a\n  /// voice is created paused and at zero volume. Starting/unpausing SoLoud can\n  /// reactivate its iOS audio backend, so NeoStation reapplies the `.ambient`\n  /// session *after* each of those operations while the voice is still muted.\n  /// Only then is the configured SFX volume restored. This closes the brief\n  /// audible race that rapid menu presses could expose with the Ring/Silent\n  /// switch enabled.\n  Future<void> _play(String path) {\n    _sfxStartSerial = _sfxStartSerial.catchError((Object _) {}).then(\n      (_) => _playSerially(path),\n    );\n    return _sfxStartSerial;\n  }\n\n  Future<void> _playSerially(String path) async {\n    final source = _sources[path];\n    if (source == null) {\n      _log.w('[SfxService] Source not found for: $path');\n      return;\n    }\n    if (!_enabled ||\n        !_isInitialized ||\n        !SoLoud.instance.isInitialized) {\n      return;\n    }\n\n    SoundHandle? handle;\n    try {\n      // Navigation sounds are intentionally non-overlapping. Besides sounding\n      // cleaner during rapid input, this guarantees that no previous SFX voice\n      // is audible while a new SoLoud voice may reactivate the audio backend.\n      await stopAllSounds();\n      if (!_enabled || !SoLoud.instance.isInitialized) return;\n\n      await AudioPolicyService().prepareForPlayback('sfx');\n      if (!_enabled || !SoLoud.instance.isInitialized) return;\n\n      // Never create an audible voice. `play` itself can wake the native audio\n      // device, so the first policy reassertion happens while it is paused.\n      handle = SoLoud.instance.play(\n        source,\n        volume: 0.0,\n        paused: true,\n      );\n      _activeHandles.add(handle);\n      await AudioPolicyService().afterPlaybackStarted('sfx-paused');\n\n      if (!_enabled ||\n          !SoLoud.instance.isInitialized ||\n          !SoLoud.instance.getIsValidVoiceHandle(handle)) {\n        await _stopHandleIfValid(handle);\n        return;\n      }\n\n      // Unpause at zero volume first. Waking the device must also complete\n      // before `.ambient` is asserted for the final time.\n      SoLoud.instance.setPause(handle, false);\n      await AudioPolicyService().ensureSilentCompatibleSession(\n        reason: 'sfx-unpaused-zero-volume',\n      );\n\n      if (!_enabled ||\n          !SoLoud.instance.isInitialized ||\n          !SoLoud.instance.getIsValidVoiceHandle(handle)) {\n        await _stopHandleIfValid(handle);\n        return;\n      }\n\n      // This is the first point at which the voice can become audible. The\n      // native session is already `.ambient`, so iOS remains authoritative for\n      // the physical Ring/Silent switch.\n      SoLoud.instance.setVolume(handle, _volume);\n      _activeHandles.removeWhere(\n        (candidate) => !SoLoud.instance.getIsValidVoiceHandle(candidate),\n      );\n    } catch (e) {\n      if (handle != null) await _stopHandleIfValid(handle);\n      _log.w('[SfxService] Playback error for $path: $e');\n    }\n  }\n\n  Future<void> _stopHandleIfValid(SoundHandle handle) async {\n    _activeHandles.remove(handle);\n    if (!SoLoud.instance.isInitialized) return;\n    try {\n      if (SoLoud.instance.getIsValidVoiceHandle(handle)) {\n        await SoLoud.instance.stop(handle);\n      }\n    } catch (_) {}\n  }\n"""

if new_play not in sfx:
    if old_play not in sfx:
        raise SystemExit('Existing SFX _play implementation not found')
    sfx = sfx.replace(old_play, new_play, 1)

sfx_path.write_text(sfx, encoding='utf-8')

pubspec_path = Path('pubspec.yaml')
pubspec = pubspec_path.read_text(encoding='utf-8')
if 'version: 0.9.9+139' not in pubspec:
    if 'version: 0.9.9+138' not in pubspec:
        raise SystemExit('Unexpected NeoStation build number')
    pubspec = pubspec.replace('version: 0.9.9+138', 'version: 0.9.9+139', 1)
pubspec_path.write_text(pubspec, encoding='utf-8')

test_path = Path('test/audio_policy_service_test.dart')
test = test_path.read_text(encoding='utf-8')
marker = """  test('SFX retains and can stop active handles', () {\n    final source = File('lib/services/sfx_service.dart').readAsStringSync();\n    expect(source, contains('_activeHandles'));\n    expect(source, contains('stopAllSounds'));\n    expect(source, contains('getIsValidVoiceHandle'));\n  });\n"""
addition = """\n\n  test('rapid SFX starts stay muted until ambient policy is reasserted', () {\n    final source = File('lib/services/sfx_service.dart').readAsStringSync();\n\n    expect(source, contains('_sfxStartSerial'));\n    expect(source, contains('await stopAllSounds()'));\n    expect(source, contains('volume: 0.0'));\n    expect(source, contains('paused: true'));\n    expect(source, contains('setPause(handle, false)'));\n    expect(source, contains("reason: 'sfx-unpaused-zero-volume'"));\n    expect(source, contains('setVolume(handle, _volume)'));\n\n    final createMuted = source.indexOf('volume: 0.0');\n    final unpause = source.indexOf('setPause(handle, false)');\n    final finalPolicy = source.indexOf("reason: 'sfx-unpaused-zero-volume'");\n    final audibleVolume = source.indexOf('setVolume(handle, _volume)');\n    expect(createMuted, greaterThanOrEqualTo(0));\n    expect(unpause, greaterThan(createMuted));\n    expect(finalPolicy, greaterThan(unpause));\n    expect(audibleVolume, greaterThan(finalPolicy));\n  });\n"""
if 'rapid SFX starts stay muted until ambient policy is reasserted' not in test:
    if marker not in test:
        raise SystemExit('Audio policy test insertion marker not found')
    test = test.replace(marker, marker + addition, 1)
test_path.write_text(test, encoding='utf-8')

print('Build 139 silent SFX race fix applied.')
