from pathlib import Path

SERVICE = Path('lib/services/library_aidoku_native_service.dart')
SCREEN = Path('lib/screens/library_screen/library_screen.dart')
MANGADEX = Path('lib/services/library_mangadex_service.dart')
TEST = Path('test/library_aidoku_native_service_test.dart')

service = SERVICE.read_text(encoding='utf-8')
screen = SCREEN.read_text(encoding='utf-8')
mangadex = MANGADEX.read_text(encoding='utf-8')
test = TEST.read_text(encoding='utf-8')


def between(text: str, start: str, end: str, replacement: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[:a] + replacement + text[b:]

# ---------------------------------------------------------------------------
# Aidoku native service: page-aware catalog loading and remote title search.
# ---------------------------------------------------------------------------
if 'class LibraryAidokuCatalogPage {' not in service:
    marker = 'enum _AidokuWebKind { madara, mangaStream, lelscan, phenix }\n'
    insert = '''class LibraryAidokuCatalogPage {
  const LibraryAidokuCatalogPage({
    required this.items,
    required this.page,
    required this.hasMore,
  });

  final List<LibraryCatalogItem> items;
  final int page;
  final bool hasMore;
}

class _AidokuPageLoad {
  const _AidokuPageLoad(this.items, this.hasMore);

  final List<LibraryCatalogItem> items;
  final bool hasMore;
}

'''
    assert marker in service
    service = service.replace(marker, insert + marker, 1)

start = '  Future<List<LibraryCatalogItem>> loadCatalog(\n'
end = '  Future<LibraryCatalogItem> loadDetails(\n'
new_catalog_api = '''  Future<LibraryAidokuCatalogPage> loadCatalogPage(
    LibraryAddon addon, {
    int page = 1,
    String query = '',
  }) async {
    final config = _config(addon);
    final safePage = page < 1 ? 1 : page;
    final normalizedQuery = query.trim();
    final result = switch (config.kind) {
      _AidokuWebKind.madara =>
        await _loadMadaraCatalog(config, safePage, normalizedQuery),
      _AidokuWebKind.mangaStream =>
        await _loadMangaStreamCatalog(config, safePage, normalizedQuery),
      _AidokuWebKind.lelscan =>
        await _loadLelscanCatalog(config, safePage, normalizedQuery),
      _AidokuWebKind.phenix =>
        await _loadPhenixCatalog(config, safePage, normalizedQuery),
    };
    return LibraryAidokuCatalogPage(
      items: List<LibraryCatalogItem>.unmodifiable(result.items),
      page: safePage,
      hasMore: result.hasMore,
    );
  }

  Future<List<LibraryCatalogItem>> loadCatalog(
    LibraryAddon addon, {
    int limit = 24,
  }) async {
    final page = await loadCatalogPage(addon);
    final safeLimit = limit.clamp(1, 100).toInt();
    return List<LibraryCatalogItem>.unmodifiable(page.items.take(safeLimit));
  }

'''
service = between(service, start, end, new_catalog_api)

madara_start = '  Future<List<LibraryCatalogItem>> _loadMadaraCatalog(\n'
ms_start = '  Future<List<LibraryCatalogItem>> _loadMangaStreamCatalog(\n'
lel_start = '  Future<List<LibraryCatalogItem>> _loadLelscanCatalog(\n'
phenix_start = '  Future<List<LibraryCatalogItem>> _loadPhenixCatalog(\n'
parse_start = '  List<LibraryCatalogItem> _parseListingNodes(\n'

new_madara = '''  Future<_AidokuPageLoad> _loadMadaraCatalog(
    _AidokuWebConfig config,
    int page,
    String query,
  ) async {
    Document document;
    List<Element> nodes;

    if (query.isNotEmpty) {
      final uri = Uri.parse(config.baseUrl).replace(
        queryParameters: <String, String>{
          's': query,
          'post_type': 'wp-manga',
          if (page > 1) 'paged': page.toString(),
        },
      );
      document = html_parser.parse(await _getText(uri));
      nodes = document.querySelectorAll(
        'div.c-tabs-item__content, div.row.c-tabs-item__content, div.page-item-detail',
      );
    } else {
      final uri = Uri.parse('${config.baseUrl}/wp-admin/admin-ajax.php');
      final response = await _postForm(
        uri,
        <String, String>{
          'action': 'madara_load_more',
          'page': (page - 1).toString(),
          'template': 'madara-core/content/content-archive',
          'vars[paged]': page.toString(),
          'vars[orderby]': 'meta_value_num',
          'vars[template]': 'archive',
          'vars[sidebar]': 'full',
          'vars[post_type]': 'wp-manga',
          'vars[post_status]': 'publish',
          'vars[meta_key]': '_latest_update',
          'vars[order]': 'desc',
          'vars[meta_query][relation]': 'OR',
          'vars[manga_archives_item_layout]': 'big_thumbnail',
        },
        referer: config.baseUrl,
      );
      document = html_parser.parse(response);
      nodes = document.querySelectorAll('div.page-item-detail');

      if (nodes.isEmpty) {
        final fallbackUri = page <= 1
            ? Uri.parse('${config.baseUrl}/${config.sourcePath}/')
            : Uri.parse('${config.baseUrl}/${config.sourcePath}/page/$page/');
        document = html_parser.parse(await _getText(fallbackUri));
        nodes = document.querySelectorAll(
          'div.page-item-detail, div.c-tabs-item__content',
        );
      }
    }

    final items = _parseListingNodes(
      config,
      nodes,
      titleSelectors: const ['h3.h5 > a', 'h3 a', 'a'],
    );
    return _AidokuPageLoad(items, items.isNotEmpty);
  }

'''
service = between(service, madara_start, ms_start, new_madara)

new_ms = '''  Future<_AidokuPageLoad> _loadMangaStreamCatalog(
    _AidokuWebConfig config,
    int page,
    String query,
  ) async {
    final Uri uri;
    if (query.isNotEmpty) {
      uri = Uri.parse(
        '${config.baseUrl}/${config.traversePath}/page/$page',
      ).replace(queryParameters: <String, String>{'s': query});
    } else if (page <= 1) {
      uri = Uri.parse(
        '${config.baseUrl}/${config.traversePath}/?order=update',
      );
    } else {
      uri = Uri.parse(
        '${config.baseUrl}/${config.traversePath}/?page=$page&order=update',
      );
    }
    final document = html_parser.parse(await _getText(uri));
    final nodes = document.querySelectorAll('.listupd .bsx');
    final items = _parseListingNodes(
      config,
      nodes,
      titleSelectors: const ['a'],
    );
    return _AidokuPageLoad(items, items.isNotEmpty);
  }

'''
service = between(service, ms_start, lel_start, new_ms)

new_lel = '''  Future<_AidokuPageLoad> _loadLelscanCatalog(
    _AidokuWebConfig config,
    int page,
    String query,
  ) async {
    final uri = Uri.parse('${config.baseUrl}/manga').replace(
      queryParameters: <String, String>{
        'page': page.toString(),
        if (query.isNotEmpty) 'title': query,
      },
    );
    final document = html_parser.parse(await _getText(uri));
    final items = <LibraryCatalogItem>[];
    for (final node in document.querySelectorAll('div[id="card-real"]')) {
      final link = node.querySelector('a');
      final href = link?.attributes['href']?.trim() ?? '';
      final title = node.querySelector('h2')?.text.trim() ?? '';
      final id = _mangaIdFromUrl(config, href);
      if (title.isEmpty || id.isEmpty) continue;
      final cover = _resolveHttps(
        config.baseUrl,
        node.querySelector('img')?.attributes['data-src'] ??
            node.querySelector('img')?.attributes['src'],
      );
      items.add(_catalogItem(config, id, title, href, coverUrl: cover));
    }
    final nextDisabled =
        document.querySelector('.pagination-disabled[aria-label*="Next"]') != null;
    return _AidokuPageLoad(items, items.isNotEmpty && !nextDisabled);
  }

'''
service = between(service, lel_start, phenix_start, new_lel)

new_phenix = '''  Future<_AidokuPageLoad> _loadPhenixCatalog(
    _AidokuWebConfig config,
    int page,
    String query,
  ) async {
    final Uri uri;
    if (query.isNotEmpty) {
      uri = Uri.parse('https://api.phenix-scans.com/front/manga/search').replace(
        queryParameters: <String, String>{'query': query},
      );
    } else {
      uri = Uri.parse('https://api.phenix-scans.com/front/manga').replace(
        queryParameters: <String, String>{
          'sort': 'updatedAt',
          'page': page.toString(),
          'limit': '30',
        },
      );
    }
    final decoded = await _getJson(uri);
    final rawMangas = decoded['mangas'];
    if (rawMangas is! List) return const _AidokuPageLoad([], false);
    final items = <LibraryCatalogItem>[];
    for (final raw in rawMangas) {
      if (raw is! Map) continue;
      final manga = Map<String, dynamic>.from(raw);
      final id = manga['slug']?.toString().trim() ?? '';
      final title = manga['title']?.toString().trim() ?? '';
      if (id.isEmpty || id == 'unknown' || title.isEmpty) continue;
      final coverPath = manga['coverImage']?.toString().trim();
      final cover = coverPath == null || coverPath.isEmpty
          ? null
          : _resolveHttps('https://api.phenix-scans.com', coverPath);
      items.add(
        _catalogItem(
          config,
          id,
          title,
          '${config.baseUrl}/manga/$id',
          coverUrl: cover,
          description: manga['synopsis']?.toString().trim() ?? '',
        ),
      );
    }
    if (query.isNotEmpty) return _AidokuPageLoad(items, false);
    final pagination = decoded['pagination'];
    final hasMore = pagination is Map && pagination['hasNextPage'] == true;
    return _AidokuPageLoad(items, hasMore);
  }

'''
service = between(service, phenix_start, parse_start, new_phenix)

# ---------------------------------------------------------------------------
# MangaDex: remote title search so unloaded MangaDex titles are discoverable.
# ---------------------------------------------------------------------------
if 'Future<List<LibraryCatalogItem>> searchTitles(' not in mangadex:
    marker = '  Future<List<LibraryMangaDexChapter>> loadChapters(\n'
    method = '''  Future<List<LibraryCatalogItem>> searchTitles(
    String query, {
    int limit = 40,
  }) async {
    final normalized = query.trim();
    if (normalized.isEmpty) return const [];
    final safeLimit = limit.clamp(1, 100).toInt();
    final uri = Uri.https(_apiHost, '/manga', <String, dynamic>{
      'title': normalized,
      'limit': safeLimit.toString(),
      'includes[]': <String>['cover_art', 'author'],
      'contentRating[]': <String>['safe'],
      'hasAvailableChapters': 'true',
    });
    final decoded = await _getJson(uri);
    final data = decoded['data'];
    if (data is! List) return const [];
    final items = <LibraryCatalogItem>[];
    for (final raw in data) {
      if (raw is! Map) continue;
      final item = _parseManga(Map<String, dynamic>.from(raw));
      if (item != null) items.add(item);
    }
    return List<LibraryCatalogItem>.unmodifiable(items);
  }

'''
    assert marker in mangadex
    mangadex = mangadex.replace(marker, method + marker, 1)

# ---------------------------------------------------------------------------
# Library screen: virtualized grid, progressive pagination, title search.
# ---------------------------------------------------------------------------
if "import 'dart:async';" not in screen:
    screen = screen.replace("import 'dart:convert';\n", "import 'dart:async';\nimport 'dart:convert';\n", 1)

field_marker = '  List<_NativeLibraryEntry> _libraryItems = const [];\n\n  int get _addonSelectionCount'
field_insert = '''  List<_NativeLibraryEntry> _libraryItems = const [];
  List<_NativeLibraryEntry> _remoteSearchEntries = const [];
  final Map<String, int> _aidokuNextPage = <String, int>{};
  final Set<String> _aidokuExhausted = <String>{};
  final Set<String> _aidokuLoading = <String>{};
  int _aidokuRoundRobinCursor = 0;
  String _titleQuery = '';
  bool _searchingTitles = false;
  int _searchGeneration = 0;

  bool get _loadingMoreCatalogs => _aidokuLoading.isNotEmpty;

  int get _addonSelectionCount'''
assert field_marker in screen
screen = screen.replace(field_marker, field_insert, 1)

visible_start = '  List<_NativeLibraryEntry> get _visibleLibraryItems {\n'
language_start = '  List<String> get _languageOptions {\n'
new_visible = '''  String _entryIdentity(_NativeLibraryEntry entry) =>
      '${entry.providerId}|${entry.item.id}';

  List<_NativeLibraryEntry> get _visibleLibraryItems {
    final query = _titleQuery.trim().toLowerCase();
    final seen = <String>{};
    final items = <_NativeLibraryEntry>[];
    for (final entry in <_NativeLibraryEntry>[
      ..._libraryItems,
      ..._remoteSearchEntries,
    ]) {
      if (!seen.add(_entryIdentity(entry))) continue;
      if (query.isNotEmpty &&
          !entry.item.title.toLowerCase().contains(query)) {
        continue;
      }
      if (_languageFilter != 'all' &&
          !_itemLanguageCodes(entry).contains(_languageFilter)) {
        continue;
      }
      if (_sourceFilter != 'all' && entry.providerId != _sourceFilter) {
        continue;
      }
      items.add(entry);
    }
    items.sort((a, b) {
      final comparison = a.item.title.toLowerCase().compareTo(
        b.item.title.toLowerCase(),
      );
      return _sortAscending ? comparison : -comparison;
    });
    return items;
  }

'''
screen = between(screen, visible_start, language_start, new_visible)

source_start = '  Map<String, String> get _sourceOptions {\n'
label_start = '  String _sourceLabel(String id) {\n'
new_sources = '''  Map<String, String> get _sourceOptions {
    final options = <String, String>{
      'all': 'all',
      LibraryMangaDexService.providerId: 'MangaDex',
    };
    for (final addon in _addons) {
      if (addon.isAidokuRepositorySource && _aidokuNativeService.supports(addon)) {
        options[addon.id] = addon.name;
      } else if (addon.canBrowseOnIos) {
        options[addon.id] = addon.name;
      }
    }
    for (final entry in _libraryItems) {
      final label = entry.isMangaDex
          ? 'MangaDex'
          : (entry.source?.name.trim().isNotEmpty == true
              ? entry.source!.name.trim()
              : entry.providerId);
      options[entry.providerId] = label;
    }
    final pairs = options.entries.where((entry) => entry.key != 'all').toList()
      ..sort((a, b) => a.value.toLowerCase().compareTo(b.value.toLowerCase()));
    return <String, String>{
      'all': 'all',
      for (final entry in pairs) entry.key: entry.value,
    };
  }

'''
screen = between(screen, source_start, label_start, new_sources)

old_init = '''  @override
  void initState() {
    super.initState();
    LibraryScreen._currentState = this;
    _loadAddons();
  }
'''
new_init = '''  @override
  void initState() {
    super.initState();
    LibraryScreen._currentState = this;
    _libraryScrollController.addListener(_onLibraryScroll);
    _loadAddons();
  }
'''
assert old_init in screen
screen = screen.replace(old_init, new_init, 1)

old_dispose = '''    _libraryScrollController.dispose();
    super.dispose();
'''
new_dispose = '''    _libraryScrollController.removeListener(_onLibraryScroll);
    _libraryScrollController.dispose();
    super.dispose();
'''
assert old_dispose in screen
screen = screen.replace(old_dispose, new_dispose, 1)

refresh_start = '  Future<void> _refreshNativeLibrary([List<LibraryAddon>? installed]) async {\n'
item_lang_start = '  Set<String> _itemLanguageCodes(_NativeLibraryEntry entry) {\n'
new_refresh = '''  Future<void> _refreshNativeLibrary([List<LibraryAddon>? installed]) async {
    final addons = installed ?? _addons;
    if (mounted) {
      setState(() {
        _loadingLibrary = true;
        _catalogFailures = 0;
        _remoteSearchEntries = const [];
        _aidokuNextPage.clear();
        _aidokuExhausted.clear();
        _aidokuLoading.clear();
      });
    }

    final entries = <_NativeLibraryEntry>[];
    var failures = 0;

    try {
      final nativeItems = await _mangaDexService.loadPopular();
      for (final item in nativeItems) {
        entries.add(
          _NativeLibraryEntry(
            providerId: LibraryMangaDexService.providerId,
            item: item,
          ),
        );
      }
    } catch (_) {
      failures++;
    }

    for (final addon in addons) {
      if (addon.isAidokuRepositorySource && _aidokuNativeService.supports(addon)) {
        try {
          final page = await _aidokuNativeService.loadCatalogPage(addon, page: 1);
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
        } catch (_) {
          failures++;
          _aidokuExhausted.add(addon.id);
        }
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

    if (!mounted) return;
    setState(() {
      _libraryItems = List<_NativeLibraryEntry>.unmodifiable(entries);
      _catalogFailures = failures;
      _loadingLibrary = false;
      _alphabetAnchor = null;
      if (_sourceFilter != 'all' &&
          !_sourceOptions.containsKey(_sourceFilter)) {
        _sourceFilter = 'all';
      }
      final visible = _visibleLibraryItems;
      if (visible.isEmpty) {
        _librarySelectedIndex = 0;
        if (_hubFocus == _HubFocus.books) _hubFocus = _HubFocus.filters;
      } else if (_librarySelectedIndex >= visible.length) {
        _librarySelectedIndex = visible.length - 1;
      }
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _onLibraryScroll();
    });
    if (_titleQuery.trim().isNotEmpty) {
      unawaited(_runTitleSearch(_titleQuery));
    }
  }

  void _onLibraryScroll() {
    if (!mounted ||
        _loadingLibrary ||
        _titleQuery.trim().isNotEmpty ||
        !_libraryScrollController.hasClients) {
      return;
    }
    final position = _libraryScrollController.position;
    final threshold = position.viewportDimension * 2.2;
    if (position.extentAfter <= (threshold < 900 ? 900 : threshold)) {
      unawaited(_loadMoreAidokuCatalogs());
    }
  }

  Future<void> _loadMoreAidokuCatalogs({String? preferredSourceId}) async {
    if (!mounted || _loadingLibrary || _titleQuery.trim().isNotEmpty) return;
    final capacity = 2 - _aidokuLoading.length;
    if (capacity <= 0) return;

    var candidates = _addons.where((addon) {
      return addon.isAidokuRepositorySource &&
          _aidokuNativeService.supports(addon) &&
          !_aidokuExhausted.contains(addon.id) &&
          !_aidokuLoading.contains(addon.id);
    }).toList();
    if (candidates.isEmpty) return;

    final preferred = preferredSourceId ??
        (_sourceFilter == 'all' ? null : _sourceFilter);
    if (preferred != null) {
      final matching = candidates.where((addon) => addon.id == preferred).toList();
      if (matching.isNotEmpty) candidates = matching;
    } else if (candidates.length > 1) {
      final offset = _aidokuRoundRobinCursor % candidates.length;
      candidates = <LibraryAddon>[
        ...candidates.skip(offset),
        ...candidates.take(offset),
      ];
      _aidokuRoundRobinCursor = (_aidokuRoundRobinCursor + capacity) % candidates.length;
    }

    final selected = candidates.take(capacity).toList();
    if (selected.isEmpty) return;
    setState(() {
      for (final addon in selected) {
        _aidokuLoading.add(addon.id);
      }
    });
    await Future.wait(selected.map(_loadAidokuPage));
  }

  Future<void> _loadAidokuPage(LibraryAddon addon) async {
    final pageNumber = _aidokuNextPage[addon.id] ?? 2;
    try {
      final page = await _aidokuNativeService.loadCatalogPage(
        addon,
        page: pageNumber,
      );
      if (!mounted) return;
      final selectedVisible = _visibleLibraryItems;
      final selectedIdentity = _librarySelectedIndex >= 0 &&
              _librarySelectedIndex < selectedVisible.length
          ? _entryIdentity(selectedVisible[_librarySelectedIndex])
          : null;
      final existing = _libraryItems
          .map(_entryIdentity)
          .toSet();
      final additions = <_NativeLibraryEntry>[];
      for (final item in page.items) {
        final entry = _NativeLibraryEntry(
          providerId: addon.id,
          source: addon,
          item: item,
        );
        if (existing.add(_entryIdentity(entry))) additions.add(entry);
      }

      setState(() {
        if (additions.isNotEmpty) {
          _libraryItems = List<_NativeLibraryEntry>.unmodifiable(
            <_NativeLibraryEntry>[..._libraryItems, ...additions],
          );
          _aidokuNextPage[addon.id] = pageNumber + 1;
        }
        if (!page.hasMore || additions.isEmpty) {
          _aidokuExhausted.add(addon.id);
        }
        _aidokuLoading.remove(addon.id);

        if (selectedIdentity != null) {
          final visible = _visibleLibraryItems;
          final index = visible.indexWhere(
            (entry) => _entryIdentity(entry) == selectedIdentity,
          );
          if (index >= 0) _librarySelectedIndex = index;
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _aidokuLoading.remove(addon.id);
        _aidokuExhausted.add(addon.id);
        _catalogFailures++;
      });
    }
  }

  Future<void> _runTitleSearch(String rawQuery) async {
    final query = rawQuery.trim();
    final generation = ++_searchGeneration;
    if (!mounted) return;
    setState(() {
      _titleQuery = query;
      _remoteSearchEntries = const [];
      _searchingTitles = query.isNotEmpty;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
    if (query.isEmpty) return;

    final futures = <Future<List<_NativeLibraryEntry>>>[
      () async {
        try {
          final items = await _mangaDexService.searchTitles(query);
          return items
              .map(
                (item) => _NativeLibraryEntry(
                  providerId: LibraryMangaDexService.providerId,
                  item: item,
                ),
              )
              .toList();
        } catch (_) {
          return <_NativeLibraryEntry>[];
        }
      }(),
      for (final addon in _addons.where(
        (addon) =>
            addon.isAidokuRepositorySource &&
            _aidokuNativeService.supports(addon),
      ))
        () async {
          try {
            final page = await _aidokuNativeService.loadCatalogPage(
              addon,
              page: 1,
              query: query,
            );
            return page.items
                .map(
                  (item) => _NativeLibraryEntry(
                    providerId: addon.id,
                    source: addon,
                    item: item,
                  ),
                )
                .toList();
          } catch (_) {
            return <_NativeLibraryEntry>[];
          }
        }(),
    ];

    final groups = await Future.wait(futures);
    if (!mounted || generation != _searchGeneration || _titleQuery != query) return;
    final seen = <String>{};
    final results = <_NativeLibraryEntry>[];
    for (final group in groups) {
      for (final entry in group) {
        if (seen.add(_entryIdentity(entry))) results.add(entry);
      }
    }
    setState(() {
      _remoteSearchEntries = List<_NativeLibraryEntry>.unmodifiable(results);
      _searchingTitles = false;
      final visible = _visibleLibraryItems;
      _librarySelectedIndex = visible.isEmpty ? 0 : 0;
    });
  }

'''
screen = between(screen, refresh_start, item_lang_start, new_refresh)

screen = screen.replace('final next = (_filterSelectedIndex + delta).clamp(0, 3).toInt();',
                        'final next = (_filterSelectedIndex + delta).clamp(0, 4).toInt();', 1)

old_activate = '''        } else if (_filterSelectedIndex == 2) {
          _openIndexMenu();
        } else {
          _openSourceMenu();
        }
'''
new_activate = '''        } else if (_filterSelectedIndex == 2) {
          _openIndexMenu();
        } else if (_filterSelectedIndex == 3) {
          _openSourceMenu();
        } else {
          _openTitleSearchDialog();
        }
'''
assert old_activate in screen
screen = screen.replace(old_activate, new_activate, 1)

source_menu_end = '''    setState(() {
      _sourceFilter = selected;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
  }

  void _tapHubCard(int index) {
'''
source_menu_new = '''    setState(() {
      _sourceFilter = selected;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
    if (selected != 'all') {
      unawaited(_loadMoreAidokuCatalogs(preferredSourceId: selected));
    }
  }

  Future<void> _openTitleSearchDialog() async {
    final controller = TextEditingController(text: _titleQuery);
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
        builder: (dialogContext) => AlertDialog(
          title: Text(
            Localizations.localeOf(dialogContext).languageCode == 'fr'
                ? 'Rechercher un titre'
                : 'Search titles',
          ),
          content: SizedBox(
            width: 520.r,
            child: TextField(
              controller: controller,
              autofocus: true,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                prefixIcon: const Icon(Symbols.search_rounded),
                hintText: Localizations.localeOf(dialogContext).languageCode == 'fr'
                    ? 'Livre, manga…'
                    : 'Book, manga…',
              ),
              onSubmitted: (value) => Navigator.of(dialogContext).pop(value),
            ),
          ),
          actions: [
            if (_titleQuery.isNotEmpty)
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(''),
                child: Text(
                  Localizations.localeOf(dialogContext).languageCode == 'fr'
                      ? 'Effacer'
                      : 'Clear',
                ),
              ),
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(AppLocale.cancel.getString(dialogContext)),
            ),
            FilledButton.icon(
              onPressed: () => Navigator.of(dialogContext).pop(controller.text),
              icon: const Icon(Symbols.search_rounded),
              label: Text(
                Localizations.localeOf(dialogContext).languageCode == 'fr'
                    ? 'Rechercher'
                    : 'Search',
              ),
            ),
          ],
        ),
      );
    } finally {
      controller.dispose();
      GamepadNavigationManager.popLayer(layerId);
    }
    if (!mounted || result == null) return;
    await _runTitleSearch(result!);
  }

  void _tapHubCard(int index) {
'''
assert source_menu_end in screen
screen = screen.replace(source_menu_end, source_menu_new, 1)

# Replace the four-filter row with five controls + separate count/status line.
filters_start = '  Widget _buildFilters(BuildContext context) {\n'
native_start = '  Widget _buildNativeLibrary(BuildContext context, ThemeData theme) {\n'
new_filters = '''  Widget _buildFilters(BuildContext context) {
    final locale = Localizations.localeOf(context).languageCode;
    final visible = _visibleLibraryItems;
    final countLabel = _titleQuery.isNotEmpty
        ? (locale == 'fr'
            ? '${visible.length} résultat${visible.length > 1 ? 's' : ''}'
            : '${visible.length} result${visible.length == 1 ? '' : 's'}')
        : (locale == 'fr'
            ? '${visible.length} titre${visible.length > 1 ? 's' : ''}'
            : '${visible.length} title${visible.length == 1 ? '' : 's'}');

    Widget control({
      required int index,
      required IconData icon,
      required String label,
      required String value,
      required VoidCallback action,
    }) {
      return Expanded(
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
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            control(
              index: 0,
              icon: Symbols.translate_rounded,
              label: locale == 'fr' ? 'Langue' : 'Language',
              value: _languageLabel(_languageFilter),
              action: _openLanguageMenu,
            ),
            SizedBox(width: 8.r),
            control(
              index: 1,
              icon: Symbols.sort_by_alpha_rounded,
              label: locale == 'fr' ? 'Tri' : 'Sort',
              value: _sortAscending ? 'A → Z' : 'Z → A',
              action: _openSortMenu,
            ),
            SizedBox(width: 8.r),
            control(
              index: 2,
              icon: Symbols.abc_rounded,
              label: 'Index',
              value: _alphabetAnchor == null ? 'A–Z' : _alphabetAnchor!,
              action: _openIndexMenu,
            ),
            SizedBox(width: 8.r),
            control(
              index: 3,
              icon: Symbols.source_rounded,
              label: 'Source',
              value: _sourceLabel(_sourceFilter),
              action: _openSourceMenu,
            ),
            SizedBox(width: 8.r),
            control(
              index: 4,
              icon: Symbols.search_rounded,
              label: locale == 'fr' ? 'Recherche' : 'Search',
              value: _titleQuery.isEmpty
                  ? (locale == 'fr' ? 'Titre' : 'Title')
                  : _titleQuery,
              action: _openTitleSearchDialog,
            ),
          ],
        ),
        SizedBox(height: 7.r),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            if (_searchingTitles) ...[
              SizedBox(
                width: 13.r,
                height: 13.r,
                child: const CircularProgressIndicator(strokeWidth: 2),
              ),
              SizedBox(width: 7.r),
              Text(
                locale == 'fr' ? 'Recherche dans les sources…' : 'Searching sources…',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              SizedBox(width: 12.r),
            ],
            Text(
              countLabel,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.58),
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ],
    );
  }

'''
screen = between(screen, filters_start, native_start, new_filters)

# Virtualize the catalog with a SliverGrid in the existing single CustomScrollView.
addons_start = '  Widget _buildAddons(BuildContext context) {\n'
new_native = '''  Widget _buildNativeLibrarySliver(BuildContext context, ThemeData theme) {
    if (_loadingLibrary) {
      return SliverToBoxAdapter(
        child: SizedBox(
          height: 220.r,
          child: const Center(child: CircularProgressIndicator()),
        ),
      );
    }

    final visible = _visibleLibraryItems;
    if (visible.isEmpty) {
      final hasContent = _libraryItems.isNotEmpty || _remoteSearchEntries.isNotEmpty;
      return SliverToBoxAdapter(
        child: SizedBox(
          height: 220.r,
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_searchingTitles)
                  const CircularProgressIndicator()
                else
                  Icon(
                    Symbols.collections_bookmark_rounded,
                    size: 38.r,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.35),
                  ),
                SizedBox(height: 8.r),
                Text(
                  _searchingTitles
                      ? (Localizations.localeOf(context).languageCode == 'fr'
                          ? 'Recherche dans les catalogues…'
                          : 'Searching catalogs…')
                      : hasContent
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
        ),
      );
    }

    return SliverLayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.crossAxisExtent >= 1200 ? 6 : 5;
        _libraryColumns = columns;
        final spacing = 12.r;
        final totalSpacing = (columns - 1) * spacing;
        final cardWidth = (constraints.crossAxisExtent - totalSpacing) / columns;
        final cardHeight = cardWidth / 0.68;
        _libraryRowExtent = cardHeight + spacing;

        return SliverGrid(
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            crossAxisSpacing: spacing,
            mainAxisSpacing: spacing,
            childAspectRatio: 0.68,
          ),
          delegate: SliverChildBuilderDelegate(
            (context, index) {
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
            },
            childCount: visible.length,
            addAutomaticKeepAlives: false,
          ),
        );
      },
    );
  }

  Widget _buildCatalogProgressSliver(BuildContext context) {
    if (!_loadingMoreCatalogs || _titleQuery.isNotEmpty) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }
    return SliverToBoxAdapter(
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: 20.r),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: 18.r,
              height: 18.r,
              child: const CircularProgressIndicator(strokeWidth: 2.2),
            ),
            SizedBox(width: 10.r),
            Text(
              Localizations.localeOf(context).languageCode == 'fr'
                  ? 'Chargement de la suite du catalogue…'
                  : 'Loading more catalog titles…',
            ),
          ],
        ),
      ),
    );
  }

'''
screen = between(screen, native_start, addons_start, new_native)

old_hub = '''        SliverToBoxAdapter(child: SizedBox(height: 12.r)),
        SliverToBoxAdapter(child: _buildNativeLibrary(context, theme)),
        SliverToBoxAdapter(child: SizedBox(height: 42.r)),
'''
new_hub = '''        SliverToBoxAdapter(child: SizedBox(height: 12.r)),
        _buildNativeLibrarySliver(context, theme),
        _buildCatalogProgressSliver(context),
        SliverToBoxAdapter(child: SizedBox(height: 42.r)),
'''
assert old_hub in screen
screen = screen.replace(old_hub, new_hub, 1)

# ---------------------------------------------------------------------------
# Tests: keep the new paging model covered and compile the page API.
# ---------------------------------------------------------------------------
if "catalog page model preserves pagination metadata" not in test:
    insert_before = '\n}\n'
    addition = '''

  test('catalog page model preserves pagination metadata', () {
    const page = LibraryAidokuCatalogPage(
      items: <dynamic>[],
      page: 3,
      hasMore: true,
    );
    expect(page.page, 3);
    expect(page.hasMore, isTrue);
    expect(page.items, isEmpty);
  });
'''
    # dynamic list cannot satisfy List<LibraryCatalogItem>; use const [] inference.
    addition = addition.replace('items: <dynamic>[]', 'items: []')
    pos = test.rfind(insert_before)
    assert pos >= 0
    test = test[:pos] + addition + test[pos:]

SERVICE.write_text(service, encoding='utf-8')
SCREEN.write_text(screen, encoding='utf-8')
MANGADEX.write_text(mangadex, encoding='utf-8')
TEST.write_text(test, encoding='utf-8')
