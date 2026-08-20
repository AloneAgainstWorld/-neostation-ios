from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'lib/screens/library_screen/library_screen.dart'
GENERAL = ROOT / 'lib/screens/settings_screen/new_settings_options/general_settings_content.dart'
READER = ROOT / 'lib/screens/library_screen/library_reader_screen.dart'


def replace_function(source: str, marker: str, replacement: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise SystemExit(f'Function marker not found: {marker}')
    brace = source.find('{', start)
    if brace < 0:
        raise SystemExit(f'Opening brace not found: {marker}')
    depth = 0
    end = None
    for index in range(brace, len(source)):
        char = source[index]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise SystemExit(f'Closing brace not found: {marker}')
    return source[:start] + replacement.rstrip() + '\n' + source[end:]


reader = r'''import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../l10n/app_locale.dart';
import '../../services/gamepad/gamepad_navigation_manager.dart';
import '../../themes/chrome_surface.dart';
import '../../utils/gamepad_nav.dart';
import '../../widgets/neo_glass.dart';

/// Full-screen Library reader using the same navigation contract as the game
/// manual reader: it owns a modal gamepad layer, so B always closes it.
/// The reading surface is wrapped in InteractiveViewer for touch pinch zoom.
class LibraryReaderScreen extends StatefulWidget {
  const LibraryReaderScreen({
    super.key,
    required this.title,
    this.subtitle = '',
    this.coverUrl,
    this.text,
    this.pages = const [],
  });

  final String title;
  final String subtitle;
  final String? coverUrl;
  final String? text;
  final List<String> pages;

  bool get hasPages => pages.isNotEmpty;

  @override
  State<LibraryReaderScreen> createState() => _LibraryReaderScreenState();
}

class _LibraryReaderScreenState extends State<LibraryReaderScreen> {
  late final GamepadNavigation _gamepadNav;
  final TransformationController _transformationController =
      TransformationController();
  late final String _layerId;

  @override
  void initState() {
    super.initState();
    _layerId = 'library_reader_${identityHashCode(this)}';
    _gamepadNav = GamepadNavigation(onBack: _close);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(_layerId);
    _gamepadNav.dispose();
    _transformationController.dispose();
    super.dispose();
  }

  void _close() {
    if (mounted) Navigator.of(context).pop();
  }

  void _resetZoom() {
    _transformationController.value = Matrix4.identity();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: widget.hasPages ? _buildPageReader(theme) : _buildTextReader(theme),
            ),
            Positioned(
              left: 12.r,
              right: 12.r,
              top: 8.r,
              child: _buildChrome(theme),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChrome(ThemeData theme) {
    return NeoGlass(
      role: GlassSurfaceRole.chrome,
      borderRadius: BorderRadius.circular(12.r),
      padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 7.r),
      child: Row(
        children: [
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: _close,
              borderRadius: BorderRadius.circular(8.r),
              child: Padding(
                padding: EdgeInsets.all(4.r),
                child: Icon(
                  Symbols.arrow_back_rounded,
                  size: 18.r,
                  color: theme.colorScheme.onSurface,
                ),
              ),
            ),
          ),
          SizedBox(width: 8.r),
          if (widget.coverUrl != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(5.r),
              child: SizedBox(
                width: 28.r,
                height: 38.r,
                child: Image.network(
                  widget.coverUrl!,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
            ),
            SizedBox(width: 8.r),
          ] else ...[
            Icon(
              Symbols.menu_book_rounded,
              size: 18.r,
              color: theme.colorScheme.primary,
            ),
            SizedBox(width: 7.r),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  widget.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 11.r,
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.onSurface,
                  ),
                ),
                if (widget.subtitle.isNotEmpty)
                  Text(
                    widget.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 8.5.r,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                    ),
                  ),
              ],
            ),
          ),
          Text(
            AppLocale.pinchToZoom.getString(context),
            style: TextStyle(
              fontSize: 8.r,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
            ),
          ),
          SizedBox(width: 8.r),
          IconButton(
            tooltip: 'Reset zoom',
            onPressed: _resetZoom,
            icon: Icon(Symbols.fit_screen_rounded, size: 18.r),
          ),
        ],
      ),
    );
  }

  Widget _buildTextReader(ThemeData theme) {
    return LayoutBuilder(
      builder: (context, constraints) => InteractiveViewer(
        transformationController: _transformationController,
        minScale: 1.0,
        maxScale: 4.0,
        boundaryMargin: EdgeInsets.all(180.r),
        panEnabled: true,
        scaleEnabled: true,
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: EdgeInsets.fromLTRB(28.r, 72.r, 28.r, 42.r),
          child: ConstrainedBox(
            constraints: BoxConstraints(minWidth: constraints.maxWidth - 56.r),
            child: SelectableText(
              widget.text ?? '',
              style: theme.textTheme.bodyLarge?.copyWith(
                height: 1.62,
                fontSize: 16.r.clamp(14.0, 21.0),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPageReader(ThemeData theme) {
    return InteractiveViewer(
      transformationController: _transformationController,
      minScale: 1.0,
      maxScale: 4.0,
      boundaryMargin: EdgeInsets.all(180.r),
      panEnabled: true,
      scaleEnabled: true,
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: EdgeInsets.fromLTRB(16.r, 68.r, 16.r, 32.r),
        child: Column(
          children: [
            for (var index = 0; index < widget.pages.length; index++) ...[
              Image.network(
                widget.pages[index],
                fit: BoxFit.contain,
                loadingBuilder: (context, child, progress) {
                  if (progress == null) return child;
                  return SizedBox(
                    height: 300.r,
                    child: const Center(child: CircularProgressIndicator()),
                  );
                },
                errorBuilder: (_, __, ___) => SizedBox(
                  height: 160.r,
                  child: const Center(child: Icon(Symbols.broken_image_rounded)),
                ),
              ),
              if (index + 1 < widget.pages.length) SizedBox(height: 10.r),
            ],
          ],
        ),
      ),
    );
  }
}
'''
READER.write_text(reader, encoding='utf-8')

source = LIBRARY.read_text(encoding='utf-8')
if "import 'library_reader_screen.dart';" not in source:
    anchor = "import 'package:neostation/widgets/neo_glass.dart';\n"
    source = source.replace(anchor, anchor + "\nimport 'library_reader_screen.dart';\n")

source = replace_function(
    source,
    '  Future<void> _showTextReader(',
    r'''  Future<void> _showTextReader(LibraryCatalogItem item, String text) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryReaderScreen(
          title: item.title,
          subtitle: item.subtitle,
          coverUrl: item.coverUrl,
          text: text,
        ),
      ),
    );
  }''',
)

source = replace_function(
    source,
    '  Future<void> _showPageReader(',
    r'''  Future<void> _showPageReader(
    String title,
    List<String> pages, {
    String subtitle = '',
  }) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryReaderScreen(
          title: title,
          subtitle: subtitle,
          pages: pages,
        ),
      ),
    );
  }''',
)

source = replace_function(
    source,
    '  Widget _buildHub(',
    r'''  Widget _buildHub(BuildContext context) {
    final theme = Theme.of(context);
    return CustomScrollView(
      controller: _libraryScrollController,
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      slivers: [
        SliverToBoxAdapter(child: _buildHeader(context)),
        SliverToBoxAdapter(child: SizedBox(height: 20.r)),
        SliverToBoxAdapter(
          child: Row(
            children: [
              Expanded(
                child: _LibraryEntryCard(
                  selected:
                      _hubFocus == _HubFocus.shortcuts && _hubSelectedIndex == 0,
                  icon: Symbols.extension_rounded,
                  title: AppLocale.libraryAddons.getString(context),
                  subtitle: AppLocale.libraryAddonsSubtitle.getString(context),
                  onTap: () => _tapHubCard(0),
                ),
              ),
              SizedBox(width: 14.r),
              Expanded(
                child: _LibraryEntryCard(
                  selected:
                      _hubFocus == _HubFocus.shortcuts && _hubSelectedIndex == 1,
                  icon: Symbols.folder_open_rounded,
                  title: AppLocale.libraryLocal.getString(context),
                  subtitle: AppLocale.libraryLocalSubtitle.getString(context),
                  onTap: () => _tapHubCard(1),
                ),
              ),
            ],
          ),
        ),
        SliverToBoxAdapter(child: SizedBox(height: 12.r)),
        SliverToBoxAdapter(child: _buildFilters(context)),
        SliverToBoxAdapter(child: SizedBox(height: 12.r)),
        SliverToBoxAdapter(child: _buildNativeLibrary(context, theme)),
        SliverToBoxAdapter(child: SizedBox(height: 42.r)),
      ],
    );
  }''',
)

source = replace_function(
    source,
    '  Widget _buildFilters(',
    r'''  Widget _buildFilters(BuildContext context) {
    final locale = Localizations.localeOf(context).languageCode;
    final visible = _visibleLibraryItems;
    final countLabel = locale == 'fr'
        ? '${visible.length} titre${visible.length > 1 ? 's' : ''}'
        : '${visible.length} title${visible.length == 1 ? '' : 's'}';

    return Row(
      children: [
        Expanded(
          child: _FilterControl(
            selected:
                _hubFocus == _HubFocus.filters && _filterSelectedIndex == 0,
            icon: Symbols.translate_rounded,
            label: locale == 'fr' ? 'Langue' : 'Language',
            value: _languageLabel(_languageFilter),
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = 0;
              });
              _openLanguageMenu();
            },
          ),
        ),
        SizedBox(width: 10.r),
        Expanded(
          child: _FilterControl(
            selected:
                _hubFocus == _HubFocus.filters && _filterSelectedIndex == 1,
            icon: Symbols.sort_by_alpha_rounded,
            label: locale == 'fr' ? 'Tri' : 'Sort',
            value: _sortAscending ? 'A → Z' : 'Z → A',
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = 1;
              });
              _openSortMenu();
            },
          ),
        ),
        SizedBox(width: 10.r),
        Expanded(
          child: _FilterControl(
            selected:
                _hubFocus == _HubFocus.filters && _filterSelectedIndex == 2,
            icon: Symbols.abc_rounded,
            label: 'Index',
            value: _alphabetAnchor == null ? 'A–Z' : _alphabetAnchor!,
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = 2;
              });
              _openIndexMenu();
            },
          ),
        ),
        SizedBox(width: 12.r),
        Text(
          countLabel,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.58),
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }''',
)

source = replace_function(
    source,
    '  Widget _buildNativeLibrary(',
    r'''  Widget _buildNativeLibrary(BuildContext context, ThemeData theme) {
    if (_loadingLibrary) {
      return SizedBox(
        height: 220.r,
        child: const Center(child: CircularProgressIndicator()),
      );
    }

    final visible = _visibleLibraryItems;
    if (visible.isEmpty) {
      final hasContent = _libraryItems.isNotEmpty;
      return SizedBox(
        height: 220.r,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Symbols.collections_bookmark_rounded,
                size: 38.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.35),
              ),
              SizedBox(height: 8.r),
              Text(
                hasContent
                    ? (Localizations.localeOf(context).languageCode == 'fr'
                          ? 'Aucun livre pour ce filtre'
                          : 'No books match this filter')
                    : AppLocale.libraryEmptyTitle.getString(context),
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (_catalogFailures > 0) ...[
                SizedBox(height: 5.r),
                Text(
                  '$_catalogFailures catalogue(s) n’ont pas pu être chargés.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.error.withValues(alpha: 0.85),
                  ),
                ),
              ],
            ],
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 1200 ? 6 : 5;
        _libraryColumns = columns;
        final spacing = 12.r;
        final totalSpacing = (columns - 1) * spacing;
        final cardWidth = (constraints.maxWidth - totalSpacing) / columns;
        final cardHeight = cardWidth / 0.68;
        _libraryRowExtent = cardHeight + spacing;
        final rowCount = (visible.length + columns - 1) ~/ columns;

        return Column(
          children: [
            for (var row = 0; row < rowCount; row++) ...[
              if (row > 0) SizedBox(height: spacing),
              SizedBox(
                height: cardHeight,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (var column = 0; column < columns; column++) ...[
                      if (column > 0) SizedBox(width: spacing),
                      Expanded(
                        child: () {
                          final index = row * columns + column;
                          if (index >= visible.length) {
                            return const SizedBox.shrink();
                          }
                          final entry = visible[index];
                          final languages = _itemLanguageCodes(entry);
                          final languageLabel = languages.isEmpty
                              ? ''
                              : languages
                                    .map((code) => code.toUpperCase())
                                    .take(2)
                                    .join(' • ');
                          return KeyedSubtree(
                            key: _keyForBook(entry),
                            child: _LibraryCatalogCard(
                              item: entry.item,
                              languageLabel: languageLabel,
                              selected:
                                  _hubFocus == _HubFocus.books &&
                                  _librarySelectedIndex == index,
                              onTap: () {
                                SfxService().playNavSound();
                                setState(() {
                                  _hubFocus = _HubFocus.books;
                                  _librarySelectedIndex = index;
                                });
                                _openCatalogItem(entry);
                              },
                            ),
                          );
                        }(),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ],
        );
      },
    );
  }''',
)

old_filter_action = r'''      if (_hubFocus == _HubFocus.filters) {
        if (_filterSelectedIndex == 0) {
          _cycleLanguageFilter();
        } else if (_filterSelectedIndex == 1) {
          _toggleAlphabeticalSort();
        } else {
          _jumpToNextLetter();
        }
        return;
      }'''
new_filter_action = r'''      if (_hubFocus == _HubFocus.filters) {
        if (_filterSelectedIndex == 0) {
          _openLanguageMenu();
        } else if (_filterSelectedIndex == 1) {
          _openSortMenu();
        } else {
          _openIndexMenu();
        }
        return;
      }'''
if old_filter_action not in source:
    raise SystemExit('Filter action block not found')
source = source.replace(old_filter_action, new_filter_action, 1)

menu_methods = r'''
  RelativeRect _popupPosition() {
    final size = MediaQuery.sizeOf(context);
    final left = 24.r;
    final top = 190.r;
    final right = (size.width - 360.r).clamp(24.0, size.width - 48.0);
    return RelativeRect.fromLTRB(left, top, right, 0);
  }

  Future<void> _openLanguageMenu() async {
    final options = _languageOptions;
    if (options.isEmpty) return;
    final selected = await showMenu<String>(
      context: context,
      position: _popupPosition(),
      items: [
        for (final code in options)
          PopupMenuItem<String>(
            value: code,
            child: Row(
              children: [
                SizedBox(
                  width: 28.r,
                  child: code == _languageFilter
                      ? Icon(Symbols.check_rounded, size: 18.r)
                      : null,
                ),
                Text(_languageLabel(code)),
              ],
            ),
          ),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _languageFilter = selected;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
  }

  Future<void> _openSortMenu() async {
    final selected = await showMenu<bool>(
      context: context,
      position: _popupPosition(),
      items: [
        PopupMenuItem<bool>(
          value: true,
          child: Row(
            children: [
              SizedBox(
                width: 28.r,
                child: _sortAscending
                    ? Icon(Symbols.check_rounded, size: 18.r)
                    : null,
              ),
              const Text('A → Z'),
            ],
          ),
        ),
        PopupMenuItem<bool>(
          value: false,
          child: Row(
            children: [
              SizedBox(
                width: 28.r,
                child: !_sortAscending
                    ? Icon(Symbols.check_rounded, size: 18.r)
                    : null,
              ),
              const Text('Z → A'),
            ],
          ),
        ),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _sortAscending = selected;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
  }

  Future<void> _openIndexMenu() async {
    final visible = _visibleLibraryItems;
    if (visible.isEmpty) return;
    final letters = visible
        .map((entry) => _firstLetter(entry.item.title))
        .where((letter) => letter.isNotEmpty)
        .toSet()
        .toList()
      ..sort();
    if (letters.isEmpty) return;

    final selected = await showMenu<String>(
      context: context,
      position: _popupPosition(),
      items: [
        for (final letter in letters)
          PopupMenuItem<String>(
            value: letter,
            child: Row(
              children: [
                SizedBox(
                  width: 28.r,
                  child: letter == _alphabetAnchor
                      ? Icon(Symbols.check_rounded, size: 18.r)
                      : null,
                ),
                Text(letter),
              ],
            ),
          ),
      ],
    );
    if (!mounted || selected == null) return;
    final itemIndex = visible.indexWhere(
      (entry) => _firstLetter(entry.item.title) == selected,
    );
    if (itemIndex < 0) return;
    setState(() {
      _alphabetAnchor = selected;
      _hubFocus = _HubFocus.books;
      _librarySelectedIndex = itemIndex;
    });
    _ensureSelectedBookVisible();
  }
'''
anchor = '  void _tapHubCard(int index) {'
if '_openLanguageMenu() async' not in source:
    if anchor not in source:
        raise SystemExit('tapHubCard anchor not found')
    source = source.replace(anchor, menu_methods + '\n' + anchor, 1)

LIBRARY.write_text(source, encoding='utf-8')

settings = GENERAL.read_text(encoding='utf-8')
settings = settings.replace(
    '    count++; // Auto-update App\n    count++; // Auto-update Systems\n',
    '',
)
settings, removed_select = re.subn(
    r"\n    // Protocol: Auto-update App\..*?\n    // Protocol: Interface Sound Effects\.",
    "\n    // Protocol: Interface Sound Effects.",
    settings,
    count=1,
    flags=re.S,
)
if removed_select != 1:
    raise SystemExit('Could not remove auto-update selection handlers')
settings, removed_rows = re.subn(
    r"\n                // Setting: Auto-update App\..*?\n                // Setting: SFX Feedback\.",
    "\n                // Setting: SFX Feedback.",
    settings,
    count=1,
    flags=re.S,
)
if removed_rows != 1:
    raise SystemExit('Could not remove auto-update setting rows')
GENERAL.write_text(settings, encoding='utf-8')

print('Library UI, reader, and General Settings patch applied.')
