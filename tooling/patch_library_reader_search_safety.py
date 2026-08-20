from pathlib import Path

SCREEN = Path('lib/screens/library_screen/library_screen.dart')
READER = Path('lib/screens/library_screen/library_reader_screen.dart')

screen = SCREEN.read_text(encoding='utf-8')
reader = READER.read_text(encoding='utf-8')


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

# ---------------------------------------------------------------------------
# Library search / adult filter / keyboard lifecycle / initial load batching.
# ---------------------------------------------------------------------------
if "package:flutter/services.dart" not in screen:
    screen = replace_once(
        screen,
        "import 'package:flutter/material.dart';\n",
        "import 'package:flutter/material.dart';\nimport 'package:flutter/services.dart';\n",
        'flutter services import',
    )

screen = replace_once(
    screen,
    "  String _titleQuery = '';\n  bool _searchingTitles = false;\n",
    "  String _titleQuery = '';\n  bool _hideAdultContent = true;\n  bool _searchingTitles = false;\n",
    'adult filter field',
)

screen = replace_once(
    screen,
    """      if (query.isNotEmpty &&
          !entry.item.title.toLowerCase().contains(query)) {
        continue;
      }
      if (_languageFilter != 'all' &&
""",
    """      if (query.isNotEmpty &&
          !entry.item.title.toLowerCase().contains(query)) {
        continue;
      }
      if (_hideAdultContent && _isAdultOrDoujinshi(entry)) {
        continue;
      }
      if (_languageFilter != 'all' &&
""",
    'visible adult filter',
)

# First pages: load supported Aidoku providers in small concurrent batches instead
# of serially. Other/native catalogs remain unchanged.
loop_start = "    for (final addon in addons) {\n      if (addon.isAidokuRepositorySource && _aidokuNativeService.supports(addon)) {\n"
loop_end = "    if (!mounted) return;\n    setState(() {\n"
new_initial_load = """    final aidokuAddons = addons
        .where(
          (addon) =>
              addon.isAidokuRepositorySource &&
              _aidokuNativeService.supports(addon),
        )
        .toList();
    const initialCatalogConcurrency = 3;
    for (var offset = 0;
        offset < aidokuAddons.length;
        offset += initialCatalogConcurrency) {
      final batch = aidokuAddons
          .skip(offset)
          .take(initialCatalogConcurrency)
          .toList();
      final results = await Future.wait(
        batch.map((addon) async {
          try {
            final page = await _aidokuNativeService.loadCatalogPage(
              addon,
              page: 1,
            );
            return MapEntry<LibraryAddon, LibraryAidokuCatalogPage?>(
              addon,
              page,
            );
          } catch (_) {
            return MapEntry<LibraryAddon, LibraryAidokuCatalogPage?>(
              addon,
              null,
            );
          }
        }),
      );
      for (final result in results) {
        final addon = result.key;
        final page = result.value;
        if (page == null) {
          failures++;
          _aidokuExhausted.add(addon.id);
          continue;
        }
        for (final item in page.items) {
          entries.add(
            _NativeLibraryEntry(
              providerId: addon.id,
              source: addon,
              item: item,
            ),
          );
        }
        _aidokuNextPage[addon.id] = 2;
        if (!page.hasMore || page.items.isEmpty) {
          _aidokuExhausted.add(addon.id);
        }
      }
    }

    for (final addon in addons) {
      if (addon.isAidokuRepositorySource &&
          _aidokuNativeService.supports(addon)) {
        continue;
      }
      if (!addon.canBrowseOnIos) continue;
      try {
        final items = await _catalogService.loadCatalog(addon);
        for (final item in items) {
          entries.add(
            _NativeLibraryEntry(
              providerId: addon.id,
              source: addon,
              item: item,
            ),
          );
        }
      } catch (_) {
        failures++;
      }
    }

"""
if loop_start not in screen:
    raise SystemExit('anchor not found: initial addon loop start')
a = screen.index(loop_start)
b = screen.index(loop_end, a)
screen = screen[:a] + new_initial_load + screen[b:]

# Continue prefetching if the user is still near the end after a page lands.
load_success_anchor = """        if (selectedIdentity != null) {
          final visible = _visibleLibraryItems;
          final index = visible.indexWhere(
            (entry) => _entryIdentity(entry) == selectedIdentity,
          );
          if (index >= 0) _librarySelectedIndex = index;
        }
      });
    } catch (_) {
"""
load_success_replacement = """        if (selectedIdentity != null) {
          final visible = _visibleLibraryItems;
          final index = visible.indexWhere(
            (entry) => _entryIdentity(entry) == selectedIdentity,
          );
          if (index >= 0) _librarySelectedIndex = index;
        }
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _onLibraryScroll();
      });
    } catch (_) {
"""
screen = replace_once(
    screen,
    load_success_anchor,
    load_success_replacement,
    'post page prefetch',
)

# Metadata-based adult/doujin filter. Aidoku source rating 2+ is NSFW; for other
# imported repository formats any non-zero explicit nsfw flag is considered adult.
metadata_marker = "  Set<String> _itemLanguageCodes(_NativeLibraryEntry entry) {\n"
metadata_helpers = r'''  bool _isAdultOrDoujinshi(_NativeLibraryEntry entry) {
    final provider = entry.source?.manifest['provider'];
    if (provider is Map) {
      final nsfw = provider['nsfw'];
      if (nsfw == true) return true;
      if (nsfw is num) {
        final isAidoku = entry.source?.isAidokuRepositorySource == true;
        if ((isAidoku && nsfw >= 2) || (!isAidoku && nsfw > 0)) {
          return true;
        }
      }
      final rating = provider['contentRating']?.toString().toLowerCase() ?? '';
      if (rating.contains('nsfw') ||
          rating.contains('pornographic') ||
          rating.contains('hentai') ||
          rating == 'adult') {
        return true;
      }
    }

    String metadata = entry.item.title.toLowerCase();
    try {
      metadata = '$metadata ${jsonEncode(entry.item.raw).toLowerCase()}';
    } catch (_) {}
    return RegExp(
      r'\b(hentai|doujinshi|doujin|pornographic)\b',
      caseSensitive: false,
    ).hasMatch(metadata);
  }

  String _contentFilterLabel() {
    final fr = Localizations.localeOf(context).languageCode == 'fr';
    if (_hideAdultContent) {
      return fr ? 'Sans Hentai/Doujinshi' : 'Hide Hentai/Doujinshi';
    }
    return fr ? 'Tout afficher' : 'Show all';
  }

'''
if metadata_helpers.strip() not in screen:
    screen = replace_once(
        screen,
        metadata_marker,
        metadata_helpers + metadata_marker,
        'adult filter helpers',
    )

screen = replace_once(
    screen,
    "final next = (_filterSelectedIndex + delta).clamp(0, 4).toInt();",
    "final next = (_filterSelectedIndex + delta).clamp(0, 5).toInt();",
    'filter navigation max',
)

screen = replace_once(
    screen,
    """        } else if (_filterSelectedIndex == 3) {
          _openSourceMenu();
        } else {
          _openTitleSearchDialog();
        }
""",
    """        } else if (_filterSelectedIndex == 3) {
          _openSourceMenu();
        } else if (_filterSelectedIndex == 4) {
          _openContentMenu();
        } else {
          _openTitleSearchDialog();
        }
""",
    'filter activation',
)

search_control = """            control(
              index: 4,
              icon: Symbols.search_rounded,
              label: locale == 'fr' ? 'Recherche' : 'Search',
              value: _titleQuery.isEmpty
                  ? (locale == 'fr' ? 'Titre' : 'Title')
                  : _titleQuery,
              action: _openTitleSearchDialog,
            ),
"""
search_control_new = """            control(
              index: 4,
              icon: Symbols.visibility_off_rounded,
              label: locale == 'fr' ? 'Contenu' : 'Content',
              value: _contentFilterLabel(),
              action: _openContentMenu,
            ),
            SizedBox(width: 8.r),
            control(
              index: 5,
              icon: Symbols.search_rounded,
              label: locale == 'fr' ? 'Recherche' : 'Search',
              value: _titleQuery.isEmpty
                  ? (locale == 'fr' ? 'Titre' : 'Title')
                  : _titleQuery,
              action: _openTitleSearchDialog,
            ),
"""
screen = replace_once(
    screen,
    search_control,
    search_control_new,
    'content control',
)

# Insert content menu and replace the search dialog with a centered, outlined
# search field. Keyboard dismissal is explicit on every exit path and repeated
# after the route has closed to work around sticky iOS IME state.
search_start = "  Future<void> _openTitleSearchDialog() async {\n"
search_end = "  void _tapHubCard(int index) {\n"
new_search = r'''  Future<void> _openContentMenu() async {
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
                child: _hideAdultContent
                    ? Icon(Symbols.check_rounded, size: 18.r)
                    : null,
              ),
              Flexible(
                child: Text(
                  Localizations.localeOf(context).languageCode == 'fr'
                      ? 'Masquer Hentai / Doujinshi'
                      : 'Hide Hentai / Doujinshi',
                ),
              ),
            ],
          ),
        ),
        PopupMenuItem<bool>(
          value: false,
          child: Row(
            children: [
              SizedBox(
                width: 28.r,
                child: !_hideAdultContent
                    ? Icon(Symbols.check_rounded, size: 18.r)
                    : null,
              ),
              Text(
                Localizations.localeOf(context).languageCode == 'fr'
                    ? 'Tout afficher'
                    : 'Show all',
              ),
            ],
          ),
        ),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _hideAdultContent = selected;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
  }

  Future<void> _dismissSystemKeyboard() async {
    FocusManager.instance.primaryFocus?.unfocus();
    try {
      await SystemChannels.textInput.invokeMethod<void>('TextInput.hide');
    } catch (_) {}
  }

  Future<void> _openTitleSearchDialog() async {
    final controller = TextEditingController(text: _titleQuery);
    final focusNode = FocusNode(debugLabel: 'library_title_search');
    const layerId = 'library_title_search_dialog';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    String? result;
    try {
      result = await showDialog<String>(
        context: context,
        barrierDismissible: true,
        builder: (dialogContext) {
          final theme = Theme.of(dialogContext);
          final fr = Localizations.localeOf(dialogContext).languageCode == 'fr';

          Future<void> closeWith(String? value) async {
            focusNode.unfocus();
            await _dismissSystemKeyboard();
            if (dialogContext.mounted) {
              Navigator.of(dialogContext).pop(value);
            }
          }

          return Dialog(
            backgroundColor: Colors.transparent,
            insetPadding: EdgeInsets.symmetric(horizontal: 34.r, vertical: 24.r),
            child: NeoGlass(
              role: GlassSurfaceRole.card,
              borderRadius: BorderRadius.circular(18.r),
              enableBackdropBlur: true,
              showSheen: false,
              padding: EdgeInsets.fromLTRB(22.r, 20.r, 22.r, 18.r),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: 720.r),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      fr ? 'Rechercher un titre' : 'Search titles',
                      style: theme.textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    SizedBox(height: 5.r),
                    Text(
                      fr
                          ? 'Livre ou manga — la recherche interroge aussi les sources installées.'
                          : 'Book or manga — installed sources are searched too.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                      ),
                    ),
                    SizedBox(height: 16.r),
                    TextField(
                      controller: controller,
                      focusNode: focusNode,
                      autofocus: true,
                      textInputAction: TextInputAction.search,
                      textAlignVertical: TextAlignVertical.center,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                      decoration: InputDecoration(
                        isDense: true,
                        filled: true,
                        fillColor: theme.colorScheme.surfaceContainerHighest
                            .withValues(alpha: 0.38),
                        prefixIcon: Icon(
                          Symbols.search_rounded,
                          color: theme.colorScheme.primary,
                        ),
                        hintText: fr ? 'Livre, manga…' : 'Book, manga…',
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: 14.r,
                          vertical: 16.r,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(13.r),
                          borderSide: BorderSide(
                            color: theme.colorScheme.outline.withValues(alpha: 0.26),
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(13.r),
                          borderSide: BorderSide(
                            color: theme.colorScheme.outline.withValues(alpha: 0.24),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(13.r),
                          borderSide: BorderSide(
                            color: theme.colorScheme.primary,
                            width: 2.r,
                          ),
                        ),
                      ),
                      onSubmitted: (value) => closeWith(value.trim()),
                    ),
                    SizedBox(height: 17.r),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (_titleQuery.isNotEmpty) ...[
                          TextButton(
                            onPressed: () => closeWith(''),
                            child: Text(fr ? 'Effacer' : 'Clear'),
                          ),
                          SizedBox(width: 6.r),
                        ],
                        TextButton(
                          onPressed: () => closeWith(null),
                          child: Text(AppLocale.cancel.getString(dialogContext)),
                        ),
                        SizedBox(width: 8.r),
                        FilledButton.icon(
                          onPressed: () => closeWith(controller.text.trim()),
                          icon: const Icon(Symbols.search_rounded),
                          label: Text(fr ? 'Rechercher' : 'Search'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      );
    } finally {
      focusNode.unfocus();
      await _dismissSystemKeyboard();
      await Future<void>.delayed(const Duration(milliseconds: 90));
      await _dismissSystemKeyboard();
      controller.dispose();
      focusNode.dispose();
      GamepadNavigationManager.popLayer(layerId);
    }
    if (!mounted || result == null) return;
    await _runTitleSearch(result!);
  }

'''
screen = replace_between(
    screen,
    search_start,
    search_end,
    new_search,
    'search dialog replacement',
)

screen = replace_once(
    screen,
    """    } finally {
      controller.dispose();
      GamepadNavigationManager.popLayer(layerId);
    }
  }

  Future<void> _installFromUrl() async {
""",
    """    } finally {
      await _dismissSystemKeyboard();
      controller.dispose();
      GamepadNavigationManager.popLayer(layerId);
    }
  }

  Future<void> _installFromUrl() async {
""",
    'url dialog keyboard cleanup',
)

# ---------------------------------------------------------------------------
# Page-by-page reader with landscape fit, tap navigation and bookmark page.
# ---------------------------------------------------------------------------
reader = replace_once(
    reader,
    """  bool _hasBookmark = false;
  double? _pendingBookmarkProgress;
""",
    """  bool _hasBookmark = false;
  double? _pendingBookmarkProgress;
  int _pageIndex = 0;
  bool _pageByPage = true;
""",
    'reader page fields',
)

reader = replace_once(
    reader,
    """    _gamepadNav = GamepadNavigation(
      onBack: _close,
      onFavorite: () => _saveBookmark(),
    );
""",
    """    _gamepadNav = GamepadNavigation(
      onBack: _close,
      onFavorite: () => _saveBookmark(),
      onNavigateLeft: () {
        if (widget.hasPages && _pageByPage) _previousPage();
      },
      onNavigateRight: () {
        if (widget.hasPages && _pageByPage) _nextPage();
      },
    );
""",
    'reader gamepad page nav',
)

reader = replace_once(
    reader,
    """  void _fitToScreen() {
    _transformationController.value = Matrix4.identity();
  }

  Future<void> _saveBookmark() async {
""",
    r'''  void _fitToScreen() {
    _transformationController.value = Matrix4.identity();
  }

  double get _currentScale =>
      _transformationController.value.getMaxScaleOnAxis();

  void _setPageIndex(int value) {
    if (!widget.hasPages) return;
    final next = value.clamp(0, widget.pages.length - 1).toInt();
    if (next == _pageIndex) return;
    setState(() => _pageIndex = next);
    _fitToScreen();
  }

  void _previousPage() => _setPageIndex(_pageIndex - 1);

  void _nextPage() => _setPageIndex(_pageIndex + 1);

  void _handlePageTap(TapUpDetails details, double width) {
    if (!_pageByPage || _currentScale > 1.05 || width <= 0) return;
    final x = details.localPosition.dx;
    if (x <= width * 0.42) {
      _previousPage();
    } else if (x >= width * 0.58) {
      _nextPage();
    }
  }

  void _togglePageMode() {
    if (!widget.hasPages) return;
    var nextIndex = _pageIndex;
    if (!_pageByPage && _scrollController.hasClients && widget.pages.length > 1) {
      final max = _scrollController.position.maxScrollExtent;
      if (max > 0) {
        final progress = (_scrollController.offset / max).clamp(0.0, 1.0);
        nextIndex = (progress * (widget.pages.length - 1)).round();
      }
    }
    setState(() {
      _pageByPage = !_pageByPage;
      _pageIndex = nextIndex.clamp(0, widget.pages.length - 1).toInt();
      if (!_pageByPage && widget.pages.length > 1) {
        _pendingBookmarkProgress = _pageIndex / (widget.pages.length - 1);
      }
    });
    _fitToScreen();
    if (!_pageByPage) _scheduleBookmarkRestore();
  }

  Future<void> _saveBookmark() async {
''',
    'reader page helpers',
)

reader = replace_once(
    reader,
    """    final progress = _scrollController.hasClients && maxScrollExtent > 0
        ? (_scrollController.offset / maxScrollExtent).clamp(0.0, 1.0)
        : 0.0;

    final payload = <String, dynamic>{
      'progress': progress,
      'matrix': _transformationController.value.storage.toList(),
      'savedAt': DateTime.now().toIso8601String(),
    };
""",
    """    final progress = widget.hasPages && _pageByPage
        ? (widget.pages.length <= 1
              ? 0.0
              : _pageIndex / (widget.pages.length - 1))
        : (_scrollController.hasClients && maxScrollExtent > 0
              ? (_scrollController.offset / maxScrollExtent).clamp(0.0, 1.0)
              : 0.0);

    final payload = <String, dynamic>{
      'progress': progress,
      'pageIndex': _pageIndex,
      'pageByPage': _pageByPage,
      'matrix': _transformationController.value.storage.toList(),
      'savedAt': DateTime.now().toIso8601String(),
    };
""",
    'reader bookmark page payload',
)

reader = replace_once(
    reader,
    """      final progressValue = decoded['progress'];
      if (progressValue is num) {
        _pendingBookmarkProgress = progressValue.toDouble().clamp(0.0, 1.0);
      }

      setState(() => _hasBookmark = true);
""",
    """      final progressValue = decoded['progress'];
      if (progressValue is num) {
        _pendingBookmarkProgress = progressValue.toDouble().clamp(0.0, 1.0);
      }
      final pageModeValue = decoded['pageByPage'];
      if (pageModeValue is bool && widget.hasPages) {
        _pageByPage = pageModeValue;
      }
      final pageIndexValue = decoded['pageIndex'];
      if (pageIndexValue is num && widget.hasPages) {
        _pageIndex = pageIndexValue
            .toInt()
            .clamp(0, widget.pages.length - 1)
            .toInt();
      } else if (widget.hasPages &&
          _pageByPage &&
          _pendingBookmarkProgress != null &&
          widget.pages.length > 1) {
        _pageIndex = (_pendingBookmarkProgress! * (widget.pages.length - 1))
            .round()
            .clamp(0, widget.pages.length - 1)
            .toInt();
      }

      setState(() => _hasBookmark = true);
""",
    'reader bookmark restore page',
)

reader = replace_once(
    reader,
    """  void _applyBookmarkProgress() {
    if (!mounted || _pendingBookmarkProgress == null) return;
    if (!_scrollController.hasClients) return;
""",
    """  void _applyBookmarkProgress() {
    if (!mounted || _pendingBookmarkProgress == null) return;
    if (widget.hasPages && _pageByPage) {
      if (widget.pages.length > 1) {
        final index = (_pendingBookmarkProgress! * (widget.pages.length - 1))
            .round()
            .clamp(0, widget.pages.length - 1)
            .toInt();
        if (index != _pageIndex) setState(() => _pageIndex = index);
      }
      _pendingBookmarkProgress = null;
      return;
    }
    if (!_scrollController.hasClients) return;
""",
    'reader apply legacy page progress',
)

# Page indicator and mode toggle in the reader chrome.
reader = replace_once(
    reader,
    """          IconButton(
            tooltip: _isFrench
                ? (_hasBookmark
""",
    """          if (widget.hasPages) ...[
            if (_pageByPage)
              Padding(
                padding: EdgeInsets.symmetric(horizontal: 5.r),
                child: Text(
                  '${_pageIndex + 1} / ${widget.pages.length}',
                  style: TextStyle(
                    fontSize: 9.r,
                    fontWeight: FontWeight.w700,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                  ),
                ),
              ),
            IconButton(
              tooltip: _pageByPage
                  ? (_isFrench ? 'Défilement continu' : 'Continuous scroll')
                  : (_isFrench ? 'Page par page' : 'Page by page'),
              onPressed: _togglePageMode,
              icon: Icon(
                _pageByPage
                    ? Symbols.view_stream_rounded
                    : Symbols.view_carousel_rounded,
                size: 18.r,
              ),
            ),
          ],
          IconButton(
            tooltip: _isFrench
                ? (_hasBookmark
""",
    'reader chrome page mode',
)

page_start = "  Widget _buildPageReader(ThemeData theme) {\n"
page_end = "}\n"
# Need the final class-closing brace: replace from page reader start to last brace.
a = reader.find(page_start)
if a < 0:
    raise SystemExit('start anchor not found: reader page builder')
# _buildPageReader is currently the last method in the class; preserve final class brace.
last = reader.rfind('\n}')
if last < a:
    raise SystemExit('end anchor not found: reader class end')
new_page_builders = r'''  Widget _buildPageReader(ThemeData theme) {
    return _pageByPage
        ? _buildPagedPageReader(theme)
        : _buildContinuousPageReader(theme);
  }

  Widget _buildPagedPageReader(ThemeData theme) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final currentPage = widget.pages[_pageIndex];
        return Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTapUp: (details) =>
                    _handlePageTap(details, constraints.maxWidth),
                child: InteractiveViewer(
                  transformationController: _transformationController,
                  minScale: 0.35,
                  maxScale: 5.0,
                  boundaryMargin: EdgeInsets.all(360.r),
                  alignment: Alignment.center,
                  panEnabled: true,
                  scaleEnabled: true,
                  child: SizedBox(
                    width: constraints.maxWidth,
                    height: constraints.maxHeight,
                    child: Padding(
                      padding: EdgeInsets.fromLTRB(18.r, 66.r, 18.r, 24.r),
                      child: Image.network(
                        currentPage,
                        headers: widget.imageHeaders,
                        fit: BoxFit.contain,
                        alignment: Alignment.center,
                        loadingBuilder: (context, child, progress) {
                          if (progress == null) return child;
                          return const Center(
                            child: CircularProgressIndicator(),
                          );
                        },
                        errorBuilder: (_, __, ___) => Center(
                          child: Icon(
                            Symbols.broken_image_rounded,
                            size: 42.r,
                            color: theme.colorScheme.onSurface
                                .withValues(alpha: 0.45),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
            if (_pageIndex > 0)
              Positioned(
                left: 5.r,
                top: constraints.maxHeight * 0.48,
                child: IconButton(
                  tooltip: _isFrench ? 'Page précédente' : 'Previous page',
                  onPressed: _previousPage,
                  icon: Icon(
                    Symbols.chevron_left_rounded,
                    size: 28.r,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                  ),
                ),
              ),
            if (_pageIndex + 1 < widget.pages.length)
              Positioned(
                right: 5.r,
                top: constraints.maxHeight * 0.48,
                child: IconButton(
                  tooltip: _isFrench ? 'Page suivante' : 'Next page',
                  onPressed: _nextPage,
                  icon: Icon(
                    Symbols.chevron_right_rounded,
                    size: 28.r,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                  ),
                ),
              ),
            Positioned(
              bottom: 7.r,
              left: 0,
              right: 0,
              child: IgnorePointer(
                child: Center(
                  child: Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: 9.r,
                      vertical: 4.r,
                    ),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surface
                          .withValues(alpha: 0.72),
                      borderRadius: BorderRadius.circular(9.r),
                    ),
                    child: Text(
                      '${_pageIndex + 1} / ${widget.pages.length}',
                      style: TextStyle(
                        fontSize: 9.r,
                        fontWeight: FontWeight.w700,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildContinuousPageReader(ThemeData theme) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final availableHeight = constraints.maxHeight - 96.r;
        final pageHeight = availableHeight > 180.r
            ? availableHeight
            : constraints.maxHeight;
        final availableWidth = constraints.maxWidth - 28.r;
        final pageWidth = availableWidth > 180.r
            ? availableWidth
            : constraints.maxWidth;

        return InteractiveViewer(
          transformationController: _transformationController,
          minScale: 0.35,
          maxScale: 5.0,
          boundaryMargin: EdgeInsets.all(360.r),
          alignment: Alignment.topCenter,
          panEnabled: true,
          scaleEnabled: true,
          child: SingleChildScrollView(
            controller: _scrollController,
            physics: const BouncingScrollPhysics(),
            padding: EdgeInsets.fromLTRB(14.r, 68.r, 14.r, 28.r),
            child: Column(
              children: [
                for (var index = 0; index < widget.pages.length; index++) ...[
                  SizedBox(
                    width: pageWidth,
                    height: pageHeight,
                    child: Image.network(
                      widget.pages[index],
                      headers: widget.imageHeaders,
                      fit: BoxFit.contain,
                      loadingBuilder: (context, child, progress) {
                        if (progress == null) return child;
                        return const Center(child: CircularProgressIndicator());
                      },
                      errorBuilder: (_, __, ___) => Center(
                        child: Icon(
                          Symbols.broken_image_rounded,
                          size: 42.r,
                          color: theme.colorScheme.onSurface
                              .withValues(alpha: 0.45),
                        ),
                      ),
                    ),
                  ),
                  if (index + 1 < widget.pages.length) SizedBox(height: 12.r),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
'''
reader = reader[:a] + new_page_builders + reader[last:]

SCREEN.write_text(screen, encoding='utf-8')
READER.write_text(reader, encoding='utf-8')
print('Library search/keyboard/content filter and page-by-page reader patch applied.')
