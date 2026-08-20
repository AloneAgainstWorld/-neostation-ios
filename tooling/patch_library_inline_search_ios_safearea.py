from pathlib import Path

LIB = Path('lib/screens/library_screen/library_screen.dart')
SETTINGS = Path('lib/screens/settings_screen/new_settings_screen.dart')

lib = LIB.read_text(encoding='utf-8')
settings = SETTINGS.read_text(encoding='utf-8')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'anchor not found: {label}')
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'start anchor not found: {label}')
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f'end anchor not found: {label}')
    return text[:a] + replacement + text[b:]

# ── Library inline search state ────────────────────────────────────────────
lib = replace_once(
    lib,
    "  String _titleQuery = '';\n  bool _hideAdultContent = true;\n",
    "  String _titleQuery = '';\n  final TextEditingController _titleSearchController = TextEditingController();\n  final FocusNode _titleSearchFocusNode =\n      FocusNode(debugLabel: 'library_inline_title_search');\n  Timer? _titleSearchDebounce;\n  bool _titleSearchMode = false;\n  bool _titleSearchFiltersExpanded = false;\n  bool _hideAdultContent = true;\n",
    'library search state',
)

lib = replace_once(
    lib,
    "    _libraryScrollController.addListener(_onLibraryScroll);\n    _loadAddons();\n",
    "    _libraryScrollController.addListener(_onLibraryScroll);\n    _titleSearchController.text = _titleQuery;\n    _loadAddons();\n",
    'init search controller',
)

lib = replace_once(
    lib,
    "    _libraryScrollController.removeListener(_onLibraryScroll);\n    _libraryScrollController.dispose();\n    super.dispose();\n",
    "    _libraryScrollController.removeListener(_onLibraryScroll);\n    _libraryScrollController.dispose();\n    _titleSearchDebounce?.cancel();\n    _titleSearchController.dispose();\n    _titleSearchFocusNode.dispose();\n    super.dispose();\n",
    'dispose search controller',
)

# Search selection opens inline mode rather than a modal dialog.
lib = lib.replace('_openTitleSearchDialog();', '_enterTitleSearchMode();')
lib = lib.replace('action: _openTitleSearchDialog,', 'action: _enterTitleSearchMode,')

# Back: first dismiss keyboard, then leave inline search mode.
lib = replace_once(
    lib,
    "  void _back() {\n    if (_view == _LibraryView.addons || _view == _LibraryView.local) {\n",
    "  void _back() {\n    if (_titleSearchMode) {\n      if (_titleSearchFocusNode.hasFocus) {\n        _titleSearchFocusNode.unfocus();\n        unawaited(_dismissSystemKeyboard());\n        return;\n      }\n      setState(() {\n        _titleSearchMode = false;\n        _titleSearchFiltersExpanded = false;\n        _hubFocus = _HubFocus.filters;\n        _filterSelectedIndex = 5;\n      });\n      return;\n    }\n\n    if (_view == _LibraryView.addons || _view == _LibraryView.local) {\n",
    'inline search back handling',
)

# Replace the entire old modal search implementation with inline-search helpers.
start = '  Future<void> _openTitleSearchDialog() async {'
end = '  void _tapHubCard(int index) {'
replacement = r'''  void _enterTitleSearchMode() {
    _titleSearchDebounce?.cancel();
    _titleSearchController.value = TextEditingValue(
      text: _titleQuery,
      selection: TextSelection.collapsed(offset: _titleQuery.length),
    );
    setState(() {
      _titleSearchMode = true;
      _titleSearchFiltersExpanded = false;
      _hubFocus = _HubFocus.filters;
      _filterSelectedIndex = 5;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _titleSearchFocusNode.requestFocus();
    });
  }

  void _leaveTitleSearchMode() {
    _titleSearchDebounce?.cancel();
    _titleSearchFocusNode.unfocus();
    unawaited(_dismissSystemKeyboard());
    setState(() {
      _titleSearchMode = false;
      _titleSearchFiltersExpanded = false;
      _hubFocus = _HubFocus.filters;
      _filterSelectedIndex = 5;
    });
  }

  void _scheduleInlineTitleSearch(String rawValue) {
    final query = rawValue.trim();
    _titleSearchDebounce?.cancel();
    final generation = ++_searchGeneration;
    setState(() {
      _titleQuery = query;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
      if (query.isEmpty) {
        _remoteSearchEntries = const [];
        _searchingTitles = false;
      } else {
        // Local titles filter immediately; remote providers fill in after the
        // short debounce below, mirroring the responsive game-search field.
        _searchingTitles = true;
      }
    });
    if (query.isEmpty) return;
    _titleSearchDebounce = Timer(const Duration(milliseconds: 420), () {
      if (!mounted || generation != _searchGeneration) return;
      unawaited(_runTitleSearch(query));
    });
  }

  Future<void> _submitInlineTitleSearch(String rawValue) async {
    _titleSearchDebounce?.cancel();
    final query = rawValue.trim();
    _titleSearchFocusNode.unfocus();
    await _dismissSystemKeyboard();
    await _runTitleSearch(query);
  }

  void _clearInlineTitleSearch() {
    _titleSearchDebounce?.cancel();
    _titleSearchController.clear();
    ++_searchGeneration;
    setState(() {
      _titleQuery = '';
      _remoteSearchEntries = const [];
      _searchingTitles = false;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
    _titleSearchFocusNode.requestFocus();
  }

  void _toggleInlineSearchFilters() {
    _titleSearchFocusNode.unfocus();
    unawaited(_dismissSystemKeyboard());
    setState(() => _titleSearchFiltersExpanded = !_titleSearchFiltersExpanded);
  }

'''
lib = replace_between(lib, start, end, replacement, 'remove modal title search')

# Search mode gets its own page-level band, just like the normal game search.
lib = replace_once(
    lib,
    "  Widget _buildHub(BuildContext context) {\n    final theme = Theme.of(context);\n    return CustomScrollView(\n",
    "  Widget _buildHub(BuildContext context) {\n    if (_titleSearchMode) return _buildInlineTitleSearchHub(context);\n\n    final theme = Theme.of(context);\n    return CustomScrollView(\n",
    'search hub branch',
)

inline_ui = r'''
  Widget _buildInlineTitleSearchHub(BuildContext context) {
    final theme = Theme.of(context);
    return CustomScrollView(
      controller: _libraryScrollController,
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      slivers: [
        SliverToBoxAdapter(child: _buildInlineTitleSearchRow(context, theme)),
        if (_titleSearchFiltersExpanded) ...[
          SliverToBoxAdapter(child: SizedBox(height: 8.r)),
          SliverToBoxAdapter(child: _buildFilters(context, includeSearch: false)),
        ],
        SliverToBoxAdapter(child: SizedBox(height: 10.r)),
        _buildNativeLibrarySliver(context, theme),
        _buildCatalogProgressSliver(context),
        SliverToBoxAdapter(child: SizedBox(height: 42.r)),
      ],
    );
  }

  Widget _buildInlineTitleSearchRow(BuildContext context, ThemeData theme) {
    final locale = Localizations.localeOf(context).languageCode;
    final visible = _visibleLibraryItems;
    final countLabel = locale == 'fr'
        ? '${visible.length} résultat${visible.length > 1 ? 's' : ''}'
        : '${visible.length} result${visible.length == 1 ? '' : 's'}';
    final activeFilters = <bool>[
      _languageFilter != 'all',
      _sourceFilter != 'all',
      _alphabetAnchor != null,
      !_hideAdultContent,
    ].where((value) => value).length;

    return Row(
      children: [
        Expanded(
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12.r),
              border: Border.all(
                color: _titleSearchFocusNode.hasFocus
                    ? theme.colorScheme.primary
                    : Colors.transparent,
                width: 2.r,
              ),
            ),
            child: TextField(
              controller: _titleSearchController,
              focusNode: _titleSearchFocusNode,
              autofocus: true,
              textInputAction: TextInputAction.done,
              onTap: () {
                if (mounted) setState(() {});
              },
              onChanged: _scheduleInlineTitleSearch,
              onSubmitted: _submitInlineTitleSearch,
              decoration: InputDecoration(
                hintText: locale == 'fr' ? 'Rechercher…' : 'Search…',
                prefixIcon: const Icon(Symbols.search_rounded),
                suffixIcon: _titleSearchController.text.isEmpty
                    ? null
                    : IconButton(
                        tooltip: locale == 'fr' ? 'Effacer' : 'Clear',
                        onPressed: _clearInlineTitleSearch,
                        icon: const Icon(Symbols.close_rounded),
                      ),
                isDense: true,
                contentPadding: EdgeInsets.symmetric(
                  horizontal: 12.r,
                  vertical: 10.r,
                ),
                filled: true,
                fillColor: theme.colorScheme.surfaceContainerHighest
                    .withValues(alpha: 0.5),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12.r),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ),
        ),
        SizedBox(width: 10.r),
        if (_searchingTitles) ...[
          SizedBox(
            width: 14.r,
            height: 14.r,
            child: const CircularProgressIndicator(strokeWidth: 2),
          ),
          SizedBox(width: 7.r),
        ],
        Text(
          countLabel,
          style: TextStyle(
            fontSize: 12.r,
            fontWeight: FontWeight.w600,
            color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
          ),
        ),
        SizedBox(width: 10.r),
        GestureDetector(
          onTap: _toggleInlineSearchFilters,
          child: Container(
            padding: EdgeInsets.symmetric(horizontal: 12.r, vertical: 9.r),
            decoration: BoxDecoration(
              color: _titleSearchFiltersExpanded
                  ? theme.colorScheme.primary.withValues(alpha: 0.18)
                  : (activeFilters > 0
                      ? theme.colorScheme.primary.withValues(alpha: 0.10)
                      : theme.colorScheme.surface.withValues(alpha: 0.5)),
              borderRadius: BorderRadius.circular(12.r),
              border: Border.all(
                color: _titleSearchFiltersExpanded
                    ? theme.colorScheme.primary
                    : (activeFilters > 0
                        ? theme.colorScheme.primary.withValues(alpha: 0.5)
                        : Colors.transparent),
                width: 2.r,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Symbols.tune_rounded, size: 18.r),
                SizedBox(width: 6.r),
                Text(
                  locale == 'fr' ? 'Filtres' : 'Filters',
                  style: TextStyle(
                    fontSize: 13.r,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (activeFilters > 0) ...[
                  SizedBox(width: 6.r),
                  Container(
                    padding: EdgeInsets.symmetric(horizontal: 6.r, vertical: 1.r),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary,
                      borderRadius: BorderRadius.circular(8.r),
                    ),
                    child: Text(
                      '$activeFilters',
                      style: TextStyle(
                        fontSize: 11.r,
                        fontWeight: FontWeight.w800,
                        color: theme.colorScheme.onPrimary,
                      ),
                    ),
                  ),
                ],
                SizedBox(width: 4.r),
                Icon(
                  _titleSearchFiltersExpanded
                      ? Symbols.expand_less_rounded
                      : Symbols.expand_more_rounded,
                  size: 16.r,
                ),
              ],
            ),
          ),
        ),
        SizedBox(width: 6.r),
        IconButton(
          tooltip: locale == 'fr' ? 'Fermer la recherche' : 'Close search',
          onPressed: _leaveTitleSearchMode,
          icon: const Icon(Symbols.close_rounded),
        ),
      ],
    );
  }

'''
lib = replace_once(lib, '\n\n  Widget _buildFilters(BuildContext context) {', '\n' + inline_ui + '  Widget _buildFilters(BuildContext context, {bool includeSearch = true}) {', 'insert inline search UI')

# Hide the redundant Search tile when the inline search page has its top band.
old_search_control = r'''            SizedBox(width: 8.r),
            control(
              index: 5,
              icon: Symbols.search_rounded,
              label: locale == 'fr' ? 'Recherche' : 'Search',
              value: _titleQuery.isEmpty
                  ? (locale == 'fr' ? 'Titre' : 'Title')
                  : _titleQuery,
              action: _enterTitleSearchMode,
            ),'''
new_search_control = r'''            if (includeSearch) ...[
              SizedBox(width: 8.r),
              control(
                index: 5,
                icon: Symbols.search_rounded,
                label: locale == 'fr' ? 'Recherche' : 'Search',
                value: _titleQuery.isEmpty
                    ? (locale == 'fr' ? 'Titre' : 'Title')
                    : _titleQuery,
                action: _enterTitleSearchMode,
              ),
            ],'''
lib = replace_once(lib, old_search_control, new_search_control, 'optional search filter tile')

# ── Generic iOS safe area for Settings body only ───────────────────────────
settings = replace_once(
    settings,
    "import 'package:flutter/material.dart';\n",
    "import 'dart:io';\n\nimport 'package:flutter/foundation.dart';\nimport 'package:flutter/material.dart';\n",
    'settings platform imports',
)
settings = replace_once(
    settings,
    "  Widget build(BuildContext context) {\n    final theme = Theme.of(context);\n\n    // Rebuild the side menu",
    "  Widget build(BuildContext context) {\n    final theme = Theme.of(context);\n    final safePadding = MediaQuery.viewPaddingOf(context);\n    // Keep the settings body clear of any iPhone notch / Dynamic Island in\n    // landscape without moving the global header/tab strip. viewPadding tracks\n    // whichever side owns the cutout after rotation, so this is device-agnostic.\n    final iosSafeLeft = !kIsWeb && Platform.isIOS ? safePadding.left : 0.0;\n    final iosSafeRight = !kIsWeb && Platform.isIOS ? safePadding.right : 0.0;\n\n    // Rebuild the side menu",
    'settings safe area variables',
)
settings = replace_once(
    settings,
    "      padding: EdgeInsets.only(top: 46.r),\n",
    "      padding: EdgeInsets.fromLTRB(iosSafeLeft, 46.r, iosSafeRight, 0),\n",
    'settings body side safe area',
)

LIB.write_text(lib, encoding='utf-8')
SETTINGS.write_text(settings, encoding='utf-8')
print('patched library inline search + generic iOS settings safe area')
