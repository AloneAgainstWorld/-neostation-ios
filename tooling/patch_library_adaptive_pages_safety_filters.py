from pathlib import Path

SCREEN = Path('lib/screens/library_screen/library_screen.dart')
READER = Path('lib/screens/library_screen/library_reader_screen.dart')
AIDOKU = Path('lib/services/library_aidoku_native_service.dart')

screen = SCREEN.read_text(encoding='utf-8')
reader = READER.read_text(encoding='utf-8')
aidoku = AIDOKU.read_text(encoding='utf-8')


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
# Library filters: explicit single-column labels + stronger adult filtering.
# ---------------------------------------------------------------------------
old = """      return Expanded(
        child: _FilterControl(
          selected: _hubFocus == _HubFocus.filters && _filterSelectedIndex == index,
          icon: icon,
          label: label,
          value: value,
          onTap: () {
            setState(() {
              _hubFocus = _HubFocus.filters;
              _filterSelectedIndex = index;
            });
            action();
          },
        ),
      );
"""
new = """      return Expanded(
        child: SizedBox(
          height: 190.r,
          child: _FilterControl(
            selected: _hubFocus == _HubFocus.filters && _filterSelectedIndex == index,
            icon: icon,
            label: label,
            value: value,
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = index;
              });
              action();
            },
          ),
        ),
      );
"""
screen = replace_once(screen, old, new, 'fixed filter control height')

adult_start = '  bool _isAdultOrDoujinshi(_NativeLibraryEntry entry) {\n'
adult_end = '  String _contentFilterLabel() {\n'
new_adult = r'''  bool _isAdultOrDoujinshi(_NativeLibraryEntry entry) {
    bool explicitFlag(dynamic value) {
      if (value == true) return true;
      if (value is num) return value > 0;
      final raw = value?.toString().trim().toLowerCase() ?? '';
      if (raw.isEmpty) return false;
      return raw == 'true' ||
          raw == 'yes' ||
          raw == '1' ||
          raw.contains('nsfw') ||
          raw.contains('adult') ||
          raw.contains('explicit') ||
          raw.contains('porn') ||
          raw.contains('hentai');
    }

    final provider = entry.source?.manifest['provider'];
    if (provider is Map) {
      if (explicitFlag(provider['nsfw']) ||
          explicitFlag(provider['adult']) ||
          explicitFlag(provider['explicit'])) {
        return true;
      }
      final rating = provider['contentRating']?.toString().toLowerCase() ?? '';
      if (RegExp(
        r'(nsfw|porn|hentai|adult|explicit|mature|erotic|smut|18\+|r-?18)',
        caseSensitive: false,
      ).hasMatch(rating)) {
        return true;
      }
    }

    final raw = entry.item.raw;
    if (explicitFlag(raw['explicitContent']) ||
        explicitFlag(raw['nsfw']) ||
        explicitFlag(raw['adult']) ||
        explicitFlag(raw['isAdult'])) {
      return true;
    }

    String metadata = <String>[
      entry.item.title,
      entry.item.subtitle,
      entry.item.description,
      entry.source?.name ?? '',
    ].join(' ').toLowerCase();
    try {
      metadata = '$metadata ${jsonEncode(raw).toLowerCase()}';
    } catch (_) {}

    return RegExp(
      r'(^|[^a-z0-9])(hentai|doujinshi|doujin|porn|pornographic|xxx|nsfw|r-?18|18\+|adult(?:s)?[ -]?only|explicit|uncensored|smut|erotic|erotica|ecchi|sexual[ -]?content|hardcore|fetish)([^a-z0-9]|$)',
      caseSensitive: false,
    ).hasMatch(metadata);
  }

'''
screen = replace_between(screen, adult_start, adult_end, new_adult, 'adult filter')

filter_start = 'class _FilterControl extends StatelessWidget {\n'
filter_end = 'class _LibraryCatalogCard extends StatelessWidget {\n'
new_filter = r'''class _FilterControl extends StatelessWidget {
  const _FilterControl({
    required this.selected,
    required this.icon,
    required this.label,
    required this.value,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String label;
  final String value;
  final VoidCallback onTap;

  List<String> get _verticalCharacters =>
      label.trim().runes.map(String.fromCharCode).toList(growable: false);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);
    final characters = _verticalCharacters;
    return Tooltip(
      message: '$label : $value',
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 130),
        decoration: BoxDecoration(
          borderRadius: radius,
          border: Border.all(
            color: selected
                ? theme.colorScheme.primary
                : theme.colorScheme.outline.withValues(alpha: 0.16),
            width: selected ? 2.r : 1.r,
          ),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            borderRadius: radius,
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 7.r, vertical: 9.r),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(icon, size: 20.r, color: theme.colorScheme.primary),
                  SizedBox(height: 7.r),
                  Expanded(
                    child: Center(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            for (final character in characters)
                              SizedBox(
                                height: 14.r,
                                width: 18.r,
                                child: Center(
                                  child: Text(
                                    character,
                                    maxLines: 1,
                                    softWrap: false,
                                    textAlign: TextAlign.center,
                                    style: theme.textTheme.labelSmall?.copyWith(
                                      height: 1,
                                      fontWeight: FontWeight.w700,
                                      color: theme.colorScheme.onSurface
                                          .withValues(alpha: 0.72),
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  SizedBox(height: 5.r),
                  SizedBox(
                    width: double.infinity,
                    height: 18.r,
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        value,
                        maxLines: 1,
                        softWrap: false,
                        textAlign: TextAlign.center,
                        style: theme.textTheme.labelSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: theme.colorScheme.onSurface
                              .withValues(alpha: 0.62),
                        ),
                      ),
                    ),
                  ),
                  Icon(
                    Symbols.expand_more_rounded,
                    size: 17.r,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

'''
screen = replace_between(screen, filter_start, filter_end, new_filter, 'filter control widget')

# ---------------------------------------------------------------------------
# Aidoku listing metadata: expose genres/explicit badges before opening a title.
# ---------------------------------------------------------------------------
old = """      final image = node.querySelector('img');
      final cover = _resolveHttps(
        config.baseUrl,
        image?.attributes['data-src'] ??
            image?.attributes['data-lazy-src'] ??
            image?.attributes['src'],
      );
      items.add(_catalogItem(config, id, title, href, coverUrl: cover));
"""
new = """      final image = node.querySelector('img');
      final cover = _resolveHttps(
        config.baseUrl,
        image?.attributes['data-src'] ??
            image?.attributes['data-lazy-src'] ??
            image?.attributes['src'],
      );
      final categories = _listingCategories(node);
      items.add(
        _catalogItem(
          config,
          id,
          title,
          href,
          coverUrl: cover,
          categories: categories,
          explicitContent: _listingLooksExplicit(node, categories),
        ),
      );
"""
aidoku = replace_once(aidoku, old, new, 'generic listing safety metadata')

old = """      items.add(_catalogItem(config, id, title, href, coverUrl: cover));
    }
    final nextDisabled =
"""
new = """      final categories = _listingCategories(node);
      items.add(
        _catalogItem(
          config,
          id,
          title,
          href,
          coverUrl: cover,
          categories: categories,
          explicitContent: _listingLooksExplicit(node, categories),
        ),
      );
    }
    final nextDisabled =
"""
aidoku = replace_once(aidoku, old, new, 'lelscan listing safety metadata')

old = """      items.add(
        _catalogItem(
          config,
          id,
          title,
          '${config.baseUrl}/manga/$id',
          coverUrl: cover,
          description: manga['synopsis']?.toString().trim() ?? '',
        ),
      );
"""
new = """      final categories = <String>[];
      final rawGenres = manga['genres'];
      if (rawGenres is List) {
        for (final rawGenre in rawGenres) {
          if (rawGenre is Map) {
            final name = rawGenre['name']?.toString().trim() ?? '';
            if (name.isNotEmpty) categories.add(name);
          } else {
            final name = rawGenre?.toString().trim() ?? '';
            if (name.isNotEmpty) categories.add(name);
          }
        }
      }
      final explicitContent =
          manga['nsfw'] == true ||
          manga['adult'] == true ||
          manga['isAdult'] == true ||
          RegExp(
            r'(hentai|doujin|porn|nsfw|adult|explicit|smut|erotic|ecchi|18\\+|r-?18)',
            caseSensitive: false,
          ).hasMatch(<String>[
            title,
            manga['contentRating']?.toString() ?? '',
            ...categories,
          ].join(' '));
      items.add(
        _catalogItem(
          config,
          id,
          title,
          '${config.baseUrl}/manga/$id',
          coverUrl: cover,
          description: manga['synopsis']?.toString().trim() ?? '',
          categories: categories,
          explicitContent: explicitContent,
        ),
      );
"""
aidoku = replace_once(aidoku, old, new, 'phenix safety metadata')

old = """    String? coverUrl,
    String description = '',
    String? subtitle,
  }) {
"""
new = """    String? coverUrl,
    String description = '',
    String? subtitle,
    List<String> categories = const <String>[],
    bool explicitContent = false,
  }) {
"""
aidoku = replace_once(aidoku, old, new, 'catalog item safety args')

old = """        'language': 'fr',
        'imageHeaders': <String, String>{
"""
new = """        'language': 'fr',
        if (categories.isNotEmpty) 'categories': List<String>.unmodifiable(categories),
        if (explicitContent) 'explicitContent': true,
        'imageHeaders': <String, String>{
"""
aidoku = replace_once(aidoku, old, new, 'catalog raw safety metadata')

insert_anchor = """  String _mangaIdFromUrl(_AidokuWebConfig config, String rawUrl) {
"""
helpers = r'''  List<String> _listingCategories(Element node) {
    final categories = <String>{};
    for (final element in node.querySelectorAll(
      '.genres a, .mgen a, .seriestugenre a, [class*="genre"] a, '
      '.post-content_item .summary-content a',
    )) {
      final value = element.text.trim();
      if (value.isNotEmpty && value.length <= 80) categories.add(value);
    }
    return categories.toList(growable: false);
  }

  bool _listingLooksExplicit(Element node, List<String> categories) {
    if (node.querySelector(
          '.adult, .nsfw, .manga-title-badges.adult, [class*="adult"], '
          '[class*="nsfw"], [data-content-rating="adult"]',
        ) !=
        null) {
      return true;
    }
    final metadata = <String>[
      node.attributes['class'] ?? '',
      node.text,
      ...categories,
    ].join(' ');
    return RegExp(
      r'(^|[^a-z0-9])(hentai|doujinshi|doujin|porn|pornographic|xxx|nsfw|r-?18|18\+|adult(?:s)?[ -]?only|explicit|uncensored|smut|erotic|erotica|ecchi|sexual[ -]?content|hardcore|fetish)([^a-z0-9]|$)',
      caseSensitive: false,
    ).hasMatch(metadata);
  }

'''
if helpers.strip() not in aidoku:
    aidoku = replace_once(aidoku, insert_anchor, helpers + insert_anchor, 'listing safety helpers')

# ---------------------------------------------------------------------------
# Reader: adaptive fitting for extreme vertical/webtoon pages.
# ---------------------------------------------------------------------------
old = """  int _pageIndex = 0;
  bool _pageByPage = true;
"""
new = """  int _pageIndex = 0;
  bool _pageByPage = true;
  bool _currentPageIsLong = false;
"""
reader = replace_once(reader, old, new, 'long page state')

old = """    if (next == _pageIndex) return;
    setState(() => _pageIndex = next);
    _fitToScreen();
"""
new = """    if (next == _pageIndex) return;
    setState(() {
      _pageIndex = next;
      _currentPageIsLong = false;
    });
    _fitToScreen();
"""
reader = replace_once(reader, old, new, 'reset long page state')

old = """  void _handlePageTap(TapUpDetails details, double width) {
    if (!_pageByPage || _currentScale > 1.05 || width <= 0) return;
"""
new = """  void _handlePageTap(TapUpDetails details, double width) {
    if (!_pageByPage ||
        _currentPageIsLong ||
        _currentScale > 1.05 ||
        width <= 0) {
      return;
    }
"""
reader = replace_once(reader, old, new, 'disable tap flip for long page')

paged_start = '  Widget _buildPagedPageReader(ThemeData theme) {\n'
paged_end = '  Widget _buildContinuousPageReader(ThemeData theme) {\n'
new_paged = r'''  Widget _buildPagedPageReader(ThemeData theme) {
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
                child: _AdaptivePagedImage(
                  key: ValueKey<String>(currentPage),
                  url: currentPage,
                  headers: widget.imageHeaders,
                  transformationController: _transformationController,
                  theme: theme,
                  onLongPageChanged: (isLong) {
                    if (!mounted || _currentPageIsLong == isLong) return;
                    setState(() => _currentPageIsLong = isLong);
                  },
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
                      color: theme.colorScheme.surface.withValues(alpha: 0.72),
                      borderRadius: BorderRadius.circular(9.r),
                    ),
                    child: Text(
                      _currentPageIsLong
                          ? '${_pageIndex + 1} / ${widget.pages.length} • ${_isFrench ? 'défilement vertical' : 'vertical scroll'}'
                          : '${_pageIndex + 1} / ${widget.pages.length}',
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

'''
reader = replace_between(reader, paged_start, paged_end, new_paged, 'paged reader')

adaptive_widget = r'''

class _AdaptivePagedImage extends StatefulWidget {
  const _AdaptivePagedImage({
    super.key,
    required this.url,
    required this.headers,
    required this.transformationController,
    required this.theme,
    required this.onLongPageChanged,
  });

  final String url;
  final Map<String, String>? headers;
  final TransformationController transformationController;
  final ThemeData theme;
  final ValueChanged<bool> onLongPageChanged;

  @override
  State<_AdaptivePagedImage> createState() => _AdaptivePagedImageState();
}

class _AdaptivePagedImageState extends State<_AdaptivePagedImage> {
  ImageStream? _imageStream;
  ImageStreamListener? _imageListener;
  bool _resolved = false;
  bool _isLongPage = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _resolveDimensions());
  }

  @override
  void didUpdateWidget(covariant _AdaptivePagedImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url || oldWidget.headers != widget.headers) {
      _detachImageListener();
      _resolved = false;
      _isLongPage = false;
      WidgetsBinding.instance.addPostFrameCallback((_) => _resolveDimensions());
    }
  }

  @override
  void dispose() {
    _detachImageListener();
    super.dispose();
  }

  void _detachImageListener() {
    if (_imageStream != null && _imageListener != null) {
      _imageStream!.removeListener(_imageListener!);
    }
    _imageStream = null;
    _imageListener = null;
  }

  void _resolveDimensions() {
    if (!mounted) return;
    final provider = NetworkImage(widget.url, headers: widget.headers);
    final stream = provider.resolve(createLocalImageConfiguration(context));
    late final ImageStreamListener listener;
    listener = ImageStreamListener(
      (info, _) {
        final width = info.image.width.toDouble();
        final height = info.image.height.toDouble();
        final isLong = width > 0 && height / width >= 2.35;
        if (!mounted) return;
        setState(() {
          _resolved = true;
          _isLongPage = isLong;
        });
        widget.onLongPageChanged(isLong);
      },
      onError: (_, __) {
        if (!mounted) return;
        setState(() {
          _resolved = true;
          _isLongPage = false;
        });
        widget.onLongPageChanged(false);
      },
    );
    _imageStream = stream;
    _imageListener = listener;
    stream.addListener(listener);
  }

  Widget _networkImage({required BoxFit fit}) {
    return Image.network(
      widget.url,
      headers: widget.headers,
      fit: fit,
      alignment: _isLongPage ? Alignment.topCenter : Alignment.center,
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return const Center(child: CircularProgressIndicator());
      },
      errorBuilder: (_, __, ___) => Center(
        child: Icon(
          Symbols.broken_image_rounded,
          size: 42.r,
          color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.45),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (_resolved && _isLongPage) {
          var readableWidth = constraints.maxWidth * 0.74;
          final maximumWidth = constraints.maxWidth - 76.r;
          if (maximumWidth > 260.r && readableWidth > maximumWidth) {
            readableWidth = maximumWidth;
          }
          if (readableWidth < constraints.maxWidth * 0.58) {
            readableWidth = constraints.maxWidth * 0.58;
          }

          return InteractiveViewer(
            transformationController: widget.transformationController,
            constrained: false,
            clipBehavior: Clip.none,
            minScale: 0.35,
            maxScale: 5.0,
            boundaryMargin: EdgeInsets.symmetric(
              horizontal: constraints.maxWidth * 0.42,
              vertical: constraints.maxHeight * 1.2,
            ),
            alignment: Alignment.topCenter,
            panEnabled: true,
            scaleEnabled: true,
            child: Padding(
              padding: EdgeInsets.only(top: 68.r, bottom: 28.r),
              child: SizedBox(
                width: readableWidth,
                child: _networkImage(fit: BoxFit.fitWidth),
              ),
            ),
          );
        }

        return InteractiveViewer(
          transformationController: widget.transformationController,
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
              child: _networkImage(fit: BoxFit.contain),
            ),
          ),
        );
      },
    );
  }
}
'''
if 'class _AdaptivePagedImage extends StatefulWidget' not in reader:
    reader = reader.rstrip() + adaptive_widget + '\n'

SCREEN.write_text(screen, encoding='utf-8')
READER.write_text(reader, encoding='utf-8')
AIDOKU.write_text(aidoku, encoding='utf-8')
