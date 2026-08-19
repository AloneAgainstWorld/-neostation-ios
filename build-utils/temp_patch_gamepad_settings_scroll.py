from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one match, found {count}: {old[:100]!r}"
        )
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# System settings > System info: give the read-only tab its own controller
# and let D-pad up/down scroll it by a comfortable fraction of the viewport.
host = "lib/widgets/system_emulator_settings_dialog.dart"
replace_once(
    host,
    "  late ScrollController _generalScrollController;\n",
    "  late ScrollController _generalScrollController;\n"
    "  late ScrollController _systemInfoScrollController;\n",
)
replace_once(
    host,
    "    _generalScrollController = ScrollController();\n",
    "    _generalScrollController = ScrollController();\n"
    "    _systemInfoScrollController = ScrollController();\n",
)
replace_once(
    host,
    "    _generalScrollController.dispose();\n",
    "    _generalScrollController.dispose();\n"
    "    _systemInfoScrollController.dispose();\n",
)

info = "lib/widgets/system_emulator_settings_dialog/system_info.dart"
replace_once(
    info,
    "    return SingleChildScrollView(\n"
    "      padding: EdgeInsets.fromLTRB(12.r, 10.r, 12.r, 12.r),\n",
    "    return SingleChildScrollView(\n"
    "      controller: _systemInfoScrollController,\n"
    "      padding: EdgeInsets.fromLTRB(12.r, 10.r, 12.r, 12.r),\n",
)

nav = "lib/widgets/system_emulator_settings_dialog/gamepad_nav.dart"
replace_once(
    nav,
    "  void _navigateUp() {\n",
    """  void _scrollSystemInfo({required bool down}) {
    if (!_systemInfoScrollController.hasClients) return;
    final position = _systemInfoScrollController.position;
    final delta = position.viewportDimension * 0.72;
    final target = (
      position.pixels + (down ? delta : -delta)
    ).clamp(position.minScrollExtent, position.maxScrollExtent).toDouble();
    if ((target - position.pixels).abs() < 0.5) return;
    _systemInfoScrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
    );
  }

  void _navigateUp() {
""",
)
replace_once(
    nav,
    """    } else if (_currentTab == 2) {
      rebuild(() {
        _appearanceIndex = (_appearanceIndex - 1 + 2) % 2;
      });
      _scrollToAppearanceSelected();
    }
  }

  void _navigateDown() {
""",
    """    } else if (_currentTab == 2) {
      rebuild(() {
        _appearanceIndex = (_appearanceIndex - 1 + 2) % 2;
      });
      _scrollToAppearanceSelected();
    } else if (_currentTab == 3) {
      _scrollSystemInfo(down: false);
    }
  }

  void _navigateDown() {
""",
)
replace_once(
    nav,
    """    } else if (_currentTab == 2) {
      rebuild(() {
        _appearanceIndex = (_appearanceIndex + 1) % 2;
      });
      _scrollToAppearanceSelected();
    }
  }

  void _navigateLeft() {
""",
    """    } else if (_currentTab == 2) {
      rebuild(() {
        _appearanceIndex = (_appearanceIndex + 1) % 2;
      });
      _scrollToAppearanceSelected();
    } else if (_currentTab == 3) {
      _scrollSystemInfo(down: true);
    }
  }

  void _navigateLeft() {
""",
)

# Scraper > Media: keep the highlighted row visible as the D-pad moves below
# Box 2D toward Video / Manual.
media = "lib/screens/scraper_screen/scraper_contents/media_content.dart"
replace_once(
    media,
    "import 'package:neostation/widgets/custom_toggle_switch.dart';\n",
    "import 'package:neostation/widgets/custom_toggle_switch.dart';\n"
    "import 'package:neostation/utils/adaptive_scroll.dart';\n",
)
replace_once(
    media,
    "class MediaContentState extends State<MediaContent> {\n"
    "  static const _orderedKeys = ['fanart', 'ss', 'wheel', 'box2D', 'video', 'manuel'];\n",
    "class MediaContentState extends State<MediaContent> {\n"
    "  static const _orderedKeys = ['fanart', 'ss', 'wheel', 'box2D', 'video', 'manuel'];\n"
    "  final AdaptiveScroller _scroller = AdaptiveScroller();\n"
    "  final List<GlobalKey> _itemKeys = List.generate(\n"
    "    _orderedKeys.length,\n"
    "    (_) => GlobalKey(),\n"
    "  );\n\n"
    "  @override\n"
    "  void didUpdateWidget(covariant MediaContent oldWidget) {\n"
    "    super.didUpdateWidget(oldWidget);\n"
    "    if (widget.isContentFocused &&\n"
    "        (!oldWidget.isContentFocused ||\n"
    "            oldWidget.selectedContentIndex != widget.selectedContentIndex)) {\n"
    "      ensureVisible(widget.selectedContentIndex);\n"
    "    }\n"
    "  }\n\n"
    "  void ensureVisible(int index) {\n"
    "    WidgetsBinding.instance.addPostFrameCallback((_) {\n"
    "      if (!mounted || index < 0 || index >= _itemKeys.length) return;\n"
    "      final itemContext = _itemKeys[index].currentContext;\n"
    "      if (itemContext != null) {\n"
    "        _scroller.ensureVisible(itemContext);\n"
    "      }\n"
    "    });\n"
    "  }\n",
)
replace_once(
    media,
    "            return Container(\n              padding: EdgeInsets.only(\n",
    "            return Container(\n"
    "              key: _itemKeys[index],\n"
    "              padding: EdgeInsets.only(\n",
)

scraper = "lib/screens/scraper_screen/new_scraper_options_screen.dart"
p = Path(scraper)
text = p.read_text(encoding="utf-8")
old = """        // Asegurar scroll para Language
        if (selectedKey == AppLocale.language) {
          _languageKey.currentState?.ensureVisible(_selectedContentIndex);
        }
"""
new = """        // Keep the gamepad cursor visible in scrollable content panels.
        if (selectedKey == AppLocale.language) {
          _languageKey.currentState?.ensureVisible(_selectedContentIndex);
        } else if (selectedKey == AppLocale.media) {
          _mediaKey.currentState?.ensureVisible(_selectedContentIndex);
        }
"""
if text.count(old) != 2:
    raise SystemExit(
        f"{scraper}: expected two language scroll blocks, found {text.count(old)}"
    )
p.write_text(text.replace(old, new), encoding="utf-8")

# App settings > Directories: ListView.builder does not construct distant ROM
# rows, so GlobalKey.ensureVisible can have no context. First move the viewport
# in the requested direction; once the row is built, refine with ensureVisible.
directories = (
    "lib/screens/settings_screen/new_settings_options/"
    "directories_settings_content.dart"
)
replace_once(
    directories,
    "  final List<GlobalKey> _itemKeys = [];\n",
    "  final List<GlobalKey> _itemKeys = [];\n"
    "  int _lastScrollIndex = 0;\n",
)
replace_once(
    directories,
    """  void scrollToIndex(int index) {
    // Use the focused row's own key so scrolling tracks its real height —
    // section headers and path-chip cards aren't a uniform height, so a
    // fixed per-row estimate drifts and overshoots as the list scrolls.
    if (index >= 0 && index < _itemKeys.length) {
      final ctx = _itemKeys[index].currentContext;
      if (ctx != null) {
        _scroller.ensureVisible(ctx);
      }
    }
  }
""",
    """  void scrollToIndex(int index) {
    if (index < 0 || index >= _directoryItems.length) return;
    _ensureKeys(_directoryItems.length);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final itemContext = _itemKeys[index].currentContext;
      if (itemContext != null) {
        _lastScrollIndex = index;
        _scroller.ensureVisible(itemContext);
        return;
      }

      // ListView.builder lazily omits off-screen ROM-folder rows. Move one
      // viewport in the requested direction so the target gets built, then
      // finish with ensureVisible using its real rendered height.
      if (!_scrollController.hasClients) return;
      final position = _scrollController.position;
      final direction = index >= _lastScrollIndex ? 1.0 : -1.0;
      _lastScrollIndex = index;
      final target = (
        position.pixels + direction * position.viewportDimension * 0.72
      ).clamp(position.minScrollExtent, position.maxScrollExtent).toDouble();

      _scrollController
          .animateTo(
            target,
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOutCubic,
          )
          .then((_) {
            if (!mounted || index >= _itemKeys.length) return;
            final builtContext = _itemKeys[index].currentContext;
            if (builtContext != null) {
              _scroller.ensureVisible(builtContext);
            }
          });
    });
  }
""",
)

# Source-regression tests match the project's existing iOS gamepad tests and
# guard the three behaviors against accidental removal.
test = Path("test/gamepad_settings_scrolling_test.dart")
test.write_text(
    r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('system info tab is scrollable with D-pad navigation', () {
    final host = File(
      'lib/widgets/system_emulator_settings_dialog.dart',
    ).readAsStringSync();
    final nav = File(
      'lib/widgets/system_emulator_settings_dialog/gamepad_nav.dart',
    ).readAsStringSync();
    final info = File(
      'lib/widgets/system_emulator_settings_dialog/system_info.dart',
    ).readAsStringSync();

    expect(host, contains('_systemInfoScrollController = ScrollController()'));
    expect(host, contains('_systemInfoScrollController.dispose()'));
    expect(info, contains('controller: _systemInfoScrollController'));
    expect(nav, contains('void _scrollSystemInfo({required bool down})'));
    expect(nav, contains('_scrollSystemInfo(down: false)'));
    expect(nav, contains('_scrollSystemInfo(down: true)'));
  });

  test('scraper media keeps the selected option visible', () {
    final media = File(
      'lib/screens/scraper_screen/scraper_contents/media_content.dart',
    ).readAsStringSync();
    final screen = File(
      'lib/screens/scraper_screen/new_scraper_options_screen.dart',
    ).readAsStringSync();

    expect(media, contains('final List<GlobalKey> _itemKeys'));
    expect(media, contains('void ensureVisible(int index)'));
    expect(media, contains('key: _itemKeys[index]'));
    expect(screen, contains('_mediaKey.currentState?.ensureVisible'));
  });

  test('directory gamepad scrolling handles lazily built ROM rows', () {
    final directories = File(
      'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart',
    ).readAsStringSync();

    expect(directories, contains('position.viewportDimension * 0.72'));
    expect(directories, contains('_lastScrollIndex'));
    expect(directories, contains('_scroller.ensureVisible(builtContext)'));
  });
}
''',
    encoding="utf-8",
)
