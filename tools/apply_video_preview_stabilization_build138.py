from pathlib import Path
import re

ROOT = Path('.')


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding='utf-8')


# Bump build number.
pubspec = read('pubspec.yaml')
pubspec, count = re.subn(
    r'^version:\s*0\.9\.9\+\d+\s*$',
    'version: 0.9.9+138',
    pubspec,
    count=1,
    flags=re.MULTILINE,
)
if count != 1:
    raise SystemExit('Could not update build number to 138')
write('pubspec.yaml', pubspec)

# Declare the user-requested 2 second stabilization window in one place.
host_path = 'lib/screens/game_screen/my_games_list.dart'
host = read(host_path)
if '_videoStartDelay' not in host:
    marker = '  Future<void> _videoTransition = Future<void>.value();\n'
    if marker not in host:
        raise SystemExit('Video transition field marker not found')
    host = host.replace(
        marker,
        marker
        + '  static const Duration _videoStartDelay = Duration(seconds: 2);\n',
        1,
    )
write(host_path, host)

# Reintroduce a deliberate, cancellable 2 second preview stabilization window.
# Unlike the old blind delay, the timer captures both the current generation and
# selected game, is cancelled on every invalidation, and cannot start stale media.
media_path = 'lib/screens/game_screen/my_games_list/secondary_display.dart'
media = read(media_path)
old = '''  void _startVideoTimer() {
    _videoTimer?.cancel();
    _videoTimer = null;
    if (!mounted || _isGameLaunching) return;

    final generation = _videoGeneration;
    final scheduledGame = _selectedGame;
    if (scheduledGame == null) return;

    unawaited(
      _startVideoPreviewForSelection(scheduledGame, generation: generation),
    );
  }
'''
new = '''  void _startVideoTimer() {
    _videoTimer?.cancel();
    _videoTimer = null;
    if (!mounted || _isGameLaunching) return;

    final generation = _videoGeneration;
    final scheduledGame = _selectedGame;
    if (scheduledGame == null) return;

    // Keep the artwork/details stable for two seconds before AVPlayer is even
    // created. Rapid navigation therefore only resets this cancellable timer;
    // stale selections never initialize an audio/video pipeline.
    if (!_isVideoLoading) {
      rebuild(() => _isVideoLoading = true);
    }
    _videoTimer = Timer(_SystemGamesListState._videoStartDelay, () {
      _videoTimer = null;
      if (!mounted ||
          _isGameLaunching ||
          generation != _videoGeneration ||
          _selectedGame != scheduledGame) {
        if (mounted && generation == _videoGeneration) {
          rebuild(() => _isVideoLoading = false);
        }
        return;
      }

      unawaited(
        _startVideoPreviewForSelection(scheduledGame, generation: generation),
      );
    });
  }
'''
if new not in media:
    if old not in media:
        raise SystemExit('Current _startVideoTimer implementation not found')
    media = media.replace(old, new, 1)
write(media_path, media)

# Strengthen the regression test so the timer cannot become an unguarded delay.
test_path = 'test/video_preview_lifecycle_test.dart'
test = read(test_path)
if "two second stabilization window is cancellable" not in test:
    insertion = '''\n  test('two second stabilization window is cancellable and generation guarded', () {
    final host = File(
      'lib/screens/game_screen/my_games_list.dart',
    ).readAsStringSync();
    final media = File(
      'lib/screens/game_screen/my_games_list/secondary_display.dart',
    ).readAsStringSync();

    expect(host, contains('Duration(seconds: 2)'));
    expect(host, contains('_videoStartDelay'));
    expect(media, contains('_videoTimer?.cancel()'));
    expect(media, contains('Timer(_SystemGamesListState._videoStartDelay'));
    expect(media, contains('generation != _videoGeneration'));
    expect(media, contains('_selectedGame != scheduledGame'));
    expect(media, contains('_startVideoPreviewForSelection'));
  });\n'''
    closing = '\n}\n'
    if not test.endswith(closing):
        raise SystemExit('Unexpected video preview test structure')
    test = test[:-len(closing)] + insertion + closing
write(test_path, test)

print('Build 138 video preview stabilization patch applied.')
