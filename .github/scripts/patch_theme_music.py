from pathlib import Path
import re


general_path = Path('lib/screens/settings_screen/new_settings_options/general_settings_content.dart')
themes_path = Path('lib/screens/settings_screen/new_settings_options/themes_settings_content.dart')

general = general_path.read_text(encoding='utf-8')
themes = themes_path.read_text(encoding='utf-8')

if 'class _HomeMusicCard extends StatelessWidget' in themes:
    print('Theme menu music UI already patched.')
    raise SystemExit(0)

for line in [
    "import 'package:neostation/l10n/home_music_locale.dart';\n",
    "import 'package:neostation/services/home_music_service.dart';\n",
]:
    if line not in general:
        raise SystemExit(f'Missing expected General import: {line.strip()}')
    general = general.replace(line, '', 1)

init_block = """    HomeMusicService().addListener(_onHomeMusicChanged);\n    HomeMusicService().init().then((_) {\n      if (mounted) setState(() {});\n    });\n"""
if init_block not in general:
    raise SystemExit('Missing HomeMusic init block in General settings')
general = general.replace(init_block, '', 1)

listener_method = """  void _onHomeMusicChanged() {\n    if (mounted) setState(() {});\n  }\n\n"""
if listener_method not in general:
    raise SystemExit('Missing HomeMusic listener method in General settings')
general = general.replace(listener_method, '', 1)

dispose_line = "    HomeMusicService().removeListener(_onHomeMusicChanged);\n"
if dispose_line not in general:
    raise SystemExit('Missing HomeMusic dispose line in General settings')
general = general.replace(dispose_line, '', 1)

count_line = "    count++; // Main-menu music\n"
if count_line not in general:
    raise SystemExit('Missing menu music item count in General settings')
general = general.replace(count_line, '', 1)

select_block = """    // Protocol: Fork main-menu ambience.\n    if (index == currentItemIndex) {\n      final music = HomeMusicService();\n      music.setEnabled(!music.enabled);\n      return;\n    }\n    currentItemIndex++;\n\n"""
if select_block not in general:
    raise SystemExit('Missing menu music selection block in General settings')
general = general.replace(select_block, '', 1)

general, removed = re.subn(
    r"\n\s*// Setting: Main-menu ambience\.\n.*?(?=\n\s*// Setting: 12-Hour Clock Format\.)",
    "\n",
    general,
    count=1,
    flags=re.S,
)
if removed != 1:
    raise SystemExit('Could not remove menu music row from General settings')

import_anchor = "import 'package:neostation/l10n/custom_background_locale.dart';\n"
if import_anchor not in themes:
    raise SystemExit('Missing custom background import anchor')
themes = themes.replace(
    import_anchor,
    import_anchor + "import 'package:neostation/l10n/home_music_locale.dart';\n",
    1,
)

service_anchor = "import 'package:neostation/services/sfx_service.dart';\n"
if service_anchor not in themes:
    raise SystemExit('Missing SFX import anchor')
themes = themes.replace(
    service_anchor,
    service_anchor + "import 'package:neostation/services/home_music_service.dart';\n",
    1,
)

init_anchor = """  void initState() {\n    super.initState();\n    _initializeKeys();\n  }\n\n"""
init_replacement = """  void initState() {\n    super.initState();\n    _initializeKeys();\n    HomeMusicService().addListener(_onHomeMusicChanged);\n    HomeMusicService().init().then((_) {\n      if (mounted) setState(() {});\n    });\n  }\n\n  void _onHomeMusicChanged() {\n    if (mounted) setState(() {});\n  }\n\n"""
if init_anchor not in themes:
    raise SystemExit('Missing Themes initState anchor')
themes = themes.replace(init_anchor, init_replacement, 1)

old_count = '    final count = themeProvider.getThemeList().length + 3;\n'
if old_count not in themes:
    raise SystemExit('Missing Themes key count')
themes = themes.replace(old_count, '    final count = themeProvider.getThemeList().length + 4;\n', 1)

dispose_anchor = """  void dispose() {\n    _scrollController.dispose();\n    super.dispose();\n  }\n"""
dispose_replacement = """  void dispose() {\n    HomeMusicService().removeListener(_onHomeMusicChanged);\n    _scrollController.dispose();\n    super.dispose();\n  }\n"""
if dispose_anchor not in themes:
    raise SystemExit('Missing Themes dispose anchor')
themes = themes.replace(dispose_anchor, dispose_replacement, 1)

old_item_count = '    return themeProvider.getThemeList().length + 3;\n'
if old_item_count not in themes:
    raise SystemExit('Missing Themes item count')
themes = themes.replace(old_item_count, '    return themeProvider.getThemeList().length + 4;\n', 1)

select_old = """    final themes = themeProvider.getThemeList();\n    final customBackgroundIndex = themes.length + 1;\n\n    if (index == 0) {\n      await themeProvider.setTheme('system');\n    } else if (index - 1 < themes.length) {\n      await themeProvider.setTheme(themes[index - 1]['name']!);\n    } else if (index == customBackgroundIndex) {\n      await _pickCustomBackground();\n      return;\n    } else {\n      await _importTheme();\n      return;\n    }\n"""
select_new = """    final themes = themeProvider.getThemeList();\n    final customBackgroundIndex = themes.length + 1;\n    final menuMusicIndex = themes.length + 2;\n\n    if (index == 0) {\n      await themeProvider.setTheme('system');\n    } else if (index - 1 < themes.length) {\n      await themeProvider.setTheme(themes[index - 1]['name']!);\n    } else if (index == customBackgroundIndex) {\n      await _pickCustomBackground();\n      return;\n    } else if (index == menuMusicIndex) {\n      await _toggleHomeMusic();\n      return;\n    } else {\n      await _importTheme();\n      return;\n    }\n"""
if select_old not in themes:
    raise SystemExit('Missing Themes selectItem block')
themes = themes.replace(select_old, select_new, 1)

music_methods = """  Future<void> _toggleHomeMusic() async {\n    final music = HomeMusicService();\n    if (music.hasMusic) {\n      await music.setEnabled(!music.enabled);\n    } else {\n      await music.chooseMusic();\n    }\n    if (mounted) setState(() {});\n  }\n\n  Future<void> _pickHomeMusic() async {\n    await HomeMusicService().chooseMusic();\n    if (mounted) setState(() {});\n  }\n\n  Future<void> _clearHomeMusic() async {\n    await HomeMusicService().clearMusic();\n    if (mounted) setState(() {});\n  }\n\n"""
background_method_anchor = '  Future<void> _pickCustomBackground() async {\n'
if background_method_anchor not in themes:
    raise SystemExit('Missing custom background method anchor')
themes = themes.replace(background_method_anchor, music_methods + background_method_anchor, 1)

delete_old = """    final themes = themeProvider.getThemeList();\n    final customBackgroundIndex = themes.length + 1;\n\n    if (index == customBackgroundIndex) {\n      if (themeProvider.hasCustomBackground) _clearCustomBackground();\n      return;\n    }\n\n    final themeIndex = index - 1;\n"""
delete_new = """    final themes = themeProvider.getThemeList();\n    final customBackgroundIndex = themes.length + 1;\n    final menuMusicIndex = themes.length + 2;\n\n    if (index == customBackgroundIndex) {\n      if (themeProvider.hasCustomBackground) _clearCustomBackground();\n      return;\n    }\n    if (index == menuMusicIndex) {\n      if (HomeMusicService().hasMusic) _clearHomeMusic();\n      return;\n    }\n\n    final themeIndex = index - 1;\n"""
if delete_old not in themes:
    raise SystemExit('Missing deleteFocusedTheme block')
themes = themes.replace(delete_old, delete_new, 1)

indices_old = """    final customBackgroundIndex = allThemes.length;\n    final importIndex = allThemes.length + 1;\n    final itemCount = allThemes.length + 2;\n"""
indices_new = """    final customBackgroundIndex = allThemes.length;\n    final menuMusicIndex = allThemes.length + 1;\n    final importIndex = allThemes.length + 2;\n    final itemCount = allThemes.length + 3;\n"""
if indices_old not in themes:
    raise SystemExit('Missing Themes build index block')
themes = themes.replace(indices_old, indices_new, 1)

import_card_anchor = "              if (index == importIndex) {\n"
music_card_block = """              if (index == menuMusicIndex) {\n                final music = HomeMusicService();\n                final fileName = music.selectedFileName;\n                final musicSubtitle = music.hasMusic\n                    ? '${music.enabled ? HomeMusicLocale.active(context) : HomeMusicLocale.disabled(context)} · ${fileName ?? ''}'\n                    : HomeMusicLocale.subtitle(context);\n\n                return Container(\n                  key: _itemKeys[index],\n                  child: _HomeMusicCard(\n                    label: HomeMusicLocale.title(context),\n                    subtitle: musicSubtitle,\n                    hasMusic: music.hasMusic,\n                    enabled: music.enabled,\n                    isFocused: isFocused,\n                    onTap: () {\n                      SfxService().playNavSound();\n                      widget.onSelectionChanged?.call(index);\n                      _toggleHomeMusic();\n                    },\n                    onReplace: music.hasMusic\n                        ? () {\n                            SfxService().playNavSound();\n                            _pickHomeMusic();\n                          }\n                        : null,\n                    onDelete: music.hasMusic ? _clearHomeMusic : null,\n                    replaceTooltip: HomeMusicLocale.replace(context),\n                  ),\n                );\n              }\n\n"""
if import_card_anchor not in themes:
    raise SystemExit('Missing Import card anchor')
themes = themes.replace(import_card_anchor, music_card_block + import_card_anchor, 1)

home_music_card = r'''

class _HomeMusicCard extends StatelessWidget {
  const _HomeMusicCard({
    required this.label,
    required this.subtitle,
    required this.hasMusic,
    required this.enabled,
    required this.isFocused,
    required this.onTap,
    required this.replaceTooltip,
    this.onReplace,
    this.onDelete,
  });

  final String label;
  final String subtitle;
  final bool hasMusic;
  final bool enabled;
  final bool isFocused;
  final VoidCallback onTap;
  final VoidCallback? onReplace;
  final VoidCallback? onDelete;
  final String replaceTooltip;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = theme.colorScheme.primary;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AspectRatio(
          aspectRatio: 4 / 3,
          child: Container(
            margin: EdgeInsets.symmetric(vertical: 4.h),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface.withValues(alpha: 0.35),
              borderRadius: BorderRadius.circular(8.r),
              border: Border.all(
                color: isFocused
                    ? accent
                    : theme.colorScheme.onSurface.withValues(alpha: 0.25),
                width: 2.r,
              ),
              boxShadow: isFocused
                  ? [
                      BoxShadow(
                        color: accent.withValues(alpha: 0.3),
                        blurRadius: 8.r,
                        spreadRadius: 1.r,
                      ),
                    ]
                  : null,
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(6.r),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          hasMusic
                              ? (enabled
                                    ? Icons.volume_up_rounded
                                    : Icons.volume_off_rounded)
                              : Icons.music_note_rounded,
                          color: isFocused
                              ? accent
                              : theme.colorScheme.onSurface.withValues(alpha: 0.55),
                          size: 40.r,
                        ),
                        if (hasMusic) ...[
                          SizedBox(height: 6.r),
                          Icon(
                            enabled
                                ? Icons.play_arrow_rounded
                                : Icons.pause_rounded,
                            color: enabled
                                ? accent
                                : theme.colorScheme.onSurface.withValues(alpha: 0.45),
                            size: 18.r,
                          ),
                        ],
                      ],
                    ),
                  ),
                  Positioned.fill(
                    child: Material(
                      color: Colors.transparent,
                      child: InkWell(
                        canRequestFocus: false,
                        onTap: onTap,
                      ),
                    ),
                  ),
                  if (onDelete != null)
                    Positioned(
                      top: 4.r,
                      right: 4.r,
                      child: Material(
                        color: Colors.black.withValues(alpha: 0.55),
                        shape: const CircleBorder(),
                        clipBehavior: Clip.antiAlias,
                        child: InkWell(
                          canRequestFocus: false,
                          onTap: onDelete,
                          child: Padding(
                            padding: EdgeInsets.all(3.r),
                            child: Icon(
                              Icons.close_rounded,
                              color: Colors.white,
                              size: 16.r,
                            ),
                          ),
                        ),
                      ),
                    ),
                  if (onReplace != null)
                    Positioned(
                      bottom: 4.r,
                      right: 4.r,
                      child: Tooltip(
                        message: replaceTooltip,
                        child: Material(
                          color: Colors.black.withValues(alpha: 0.55),
                          shape: const CircleBorder(),
                          clipBehavior: Clip.antiAlias,
                          child: InkWell(
                            canRequestFocus: false,
                            onTap: onReplace,
                            child: Padding(
                              padding: EdgeInsets.all(4.r),
                              child: Icon(
                                Icons.folder_open_rounded,
                                color: Colors.white,
                                size: 17.r,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
        SizedBox(height: 4.r),
        Text(
          label,
          textAlign: TextAlign.center,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: isFocused
                ? theme.colorScheme.onSurface
                : theme.colorScheme.onSurface.withValues(alpha: 0.7),
            fontWeight: isFocused ? FontWeight.bold : FontWeight.normal,
            fontSize: 12.r,
          ),
        ),
        Text(
          subtitle,
          textAlign: TextAlign.center,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
            fontSize: 8.r,
          ),
        ),
      ],
    );
  }
}
'''

themes = themes.rstrip() + home_music_card + '\n'

general_path.write_text(general, encoding='utf-8')
themes_path.write_text(themes, encoding='utf-8')
