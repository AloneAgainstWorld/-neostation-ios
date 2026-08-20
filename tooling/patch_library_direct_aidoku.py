from pathlib import Path

screen_path = Path('lib/screens/library_screen/library_screen.dart')
reader_path = Path('lib/screens/library_screen/library_reader_screen.dart')

screen = screen_path.read_text(encoding='utf-8')
reader = reader_path.read_text(encoding='utf-8')

# Import native Aidoku web bridge.
old = "import 'package:neostation/services/library_addon_service.dart';\nimport 'package:neostation/services/library_catalog_service.dart';\n"
new = "import 'package:neostation/services/library_addon_service.dart';\nimport 'package:neostation/services/library_aidoku_native_service.dart';\nimport 'package:neostation/services/library_catalog_service.dart';\n"
assert old in screen
screen = screen.replace(old, new, 1)

# Source cards are no longer content entries.
screen = screen.replace("\n  bool get isSourceCard => item.raw['neoStationSourceCard'] == true;\n", "", 1)

old = "  final LibraryAddonService _addonService = LibraryAddonService.instance;\n  final LibraryCatalogService _catalogService = LibraryCatalogService.instance;\n"
new = "  final LibraryAddonService _addonService = LibraryAddonService.instance;\n  final LibraryAidokuNativeService _aidokuNativeService =\n      LibraryAidokuNativeService.instance;\n  final LibraryCatalogService _catalogService = LibraryCatalogService.instance;\n"
assert old in screen
screen = screen.replace(old, new, 1)

# Remove the metadata-only source-card factory introduced by the previous patch.
start = screen.index('  _NativeLibraryEntry _sourceEntryForAddon(LibraryAddon addon) {')
end = screen.index('  Future<void> _refreshNativeLibrary', start)
screen = screen[:start] + screen[end:]

old = """    for (final addon in addons) {
      if (addon.isRepositorySource && addon.isMetadataOnlyOnIos) {
        entries.add(_sourceEntryForAddon(addon));
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
new = """    for (final addon in addons) {
      if (addon.isAidokuRepositorySource && _aidokuNativeService.supports(addon)) {
        try {
          final items = await _aidokuNativeService.loadCatalog(addon);
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
assert old in screen
screen = screen.replace(old, new, 1)

# Aidoku details now communicate whether the imported source is natively bridged.
old = """                if (addon.isAidokuRepositorySource) ...[
                  SizedBox(height: 10.r),
                  Text(
                    'Aidoku • ${addon.language ?? 'all'} • iOS source metadata',
                    style: Theme.of(dialogContext).textTheme.bodySmall?.copyWith(
                      color: Theme.of(dialogContext).colorScheme.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
"""
new = """                if (addon.isAidokuRepositorySource) ...[
                  SizedBox(height: 10.r),
                  Text(
                    _aidokuNativeService.supports(addon)
                        ? 'Aidoku • ${addon.language ?? 'all'} • catalogue natif NeoStation'
                        : 'Aidoku • ${addon.language ?? 'all'} • métadonnées de source',
                    style: Theme.of(dialogContext).textTheme.bodySmall?.copyWith(
                      color: Theme.of(dialogContext).colorScheme.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
"""
assert old in screen
screen = screen.replace(old, new, 1)

# Open bridged Aidoku titles as real manga.
old = """  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {
    if (entry.isSourceCard && entry.source != null) {
      await _showAddonDetails(entry.source!);
      return;
    }

    if (entry.isMangaDex) {
"""
new = """  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {
    if (entry.source != null && _aidokuNativeService.supports(entry.source!)) {
      await _openAidokuTitle(entry);
      return;
    }

    if (entry.isMangaDex) {
"""
assert old in screen
screen = screen.replace(old, new, 1)

# Pass optional HTTP headers to page reader.
old = """  Future<void> _showPageReader(
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
          bookmarkId: 'pages:$title:$subtitle',
        ),
      ),
    );
  }

  Future<void> _openMangaDexTitle(LibraryCatalogItem item) async {
"""
new = """  Future<void> _showPageReader(
    String title,
    List<String> pages, {
    String subtitle = '',
    Map<String, String>? imageHeaders,
  }) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryReaderScreen(
          title: title,
          subtitle: subtitle,
          pages: pages,
          imageHeaders: imageHeaders,
          bookmarkId: 'pages:$title:$subtitle',
        ),
      ),
    );
  }

  Future<void> _openAidokuTitle(_NativeLibraryEntry entry) async {
    final addon = entry.source!;
    final locale = Localizations.localeOf(context).languageCode;
    var item = entry.item;

    _showMessage(
      locale == 'fr' ? 'Chargement des chapitres…' : 'Loading chapters…',
    );

    try {
      item = await _aidokuNativeService.loadDetails(addon, item);
    } catch (_) {
      // Catalog cards already contain enough data to continue if details fail.
    }

    List<LibraryAidokuChapter> chapters;
    try {
      chapters = await _aidokuNativeService.loadChapters(addon, item);
    } on LibraryAddonException catch (error) {
      _showMessage(error.message);
      return;
    }

    if (!mounted || chapters.isEmpty) {
      if (mounted) {
        _showMessage(
          locale == 'fr'
              ? 'Aucun chapitre disponible pour ce manga.'
              : 'No chapters are available for this manga.',
        );
      }
      return;
    }

    const layerId = 'library_aidoku_chapters';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    LibraryAidokuChapter? selectedChapter;
    try {
      selectedChapter = await showDialog<LibraryAidokuChapter>(
        context: context,
        builder: (dialogContext) {
          final size = MediaQuery.sizeOf(dialogContext);
          final theme = Theme.of(dialogContext);
          return Dialog(
            backgroundColor: Colors.transparent,
            insetPadding: EdgeInsets.symmetric(horizontal: 24.r, vertical: 18.r),
            child: NeoGlass(
              role: GlassSurfaceRole.card,
              borderRadius: BorderRadius.circular(18.r),
              enableBackdropBlur: true,
              showSheen: false,
              child: SizedBox(
                width: size.width * 0.92,
                height: size.height * 0.86,
                child: Column(
                  children: [
                    Padding(
                      padding: EdgeInsets.fromLTRB(18.r, 14.r, 8.r, 8.r),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  item.title,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.titleLarge?.copyWith(
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                Text(
                                  addon.name,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: theme.colorScheme.primary,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            onPressed: () => Navigator.of(dialogContext).pop(),
                            icon: const Icon(Symbols.close_rounded),
                          ),
                        ],
                      ),
                    ),
                    if (item.description.isNotEmpty)
                      Padding(
                        padding: EdgeInsets.fromLTRB(18.r, 0, 18.r, 10.r),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            item.description,
                            maxLines: 4,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodyMedium,
                          ),
                        ),
                      ),
                    Expanded(
                      child: ListView.separated(
                        padding: EdgeInsets.fromLTRB(12.r, 4.r, 12.r, 20.r),
                        itemCount: chapters.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (_, index) {
                          final chapter = chapters[index];
                          final details = <String>[
                            if (chapter.chapter.isNotEmpty)
                              'Ch. ${chapter.chapter}',
                            chapter.language.toUpperCase(),
                          ].join(' • ');
                          return ListTile(
                            title: Text(chapter.displayTitle),
                            subtitle: details.isEmpty ? null : Text(details),
                            trailing: const Icon(Symbols.menu_book_rounded),
                            onTap: () =>
                                Navigator.of(dialogContext).pop(chapter),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      );
    } finally {
      GamepadNavigationManager.popLayer(layerId);
    }

    if (!mounted || selectedChapter == null) return;
    _showMessage(locale == 'fr' ? 'Chargement des pages…' : 'Loading pages…');
    List<String> pages;
    try {
      pages = await _aidokuNativeService.loadPages(
        addon,
        item,
        selectedChapter,
      );
    } on LibraryAddonException catch (error) {
      _showMessage(error.message);
      return;
    }
    if (!mounted) return;
    await _showPageReader(
      '${item.title} — ${selectedChapter.displayTitle}',
      pages,
      subtitle: '${addon.name} • ${selectedChapter.language.toUpperCase()}',
      imageHeaders: _aidokuNativeService.imageHeaders(addon),
    );
  }

  Future<void> _openMangaDexTitle(LibraryCatalogItem item) async {
"""
assert old in screen
screen = screen.replace(old, new, 1)

# Remove source-card-only card argument and restore book icon fallback.
old = """                            child: _LibraryCatalogCard(
                              item: entry.item,
                              languageLabel: languageLabel,
                              isSourceCard: entry.isSourceCard,
                              selected:
"""
new = """                            child: _LibraryCatalogCard(
                              item: entry.item,
                              languageLabel: languageLabel,
                              selected:
"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """class _LibraryCatalogCard extends StatelessWidget {
  const _LibraryCatalogCard({
    required this.item,
    required this.languageLabel,
    required this.isSourceCard,
    required this.selected,
    required this.onTap,
  });

  final LibraryCatalogItem item;
  final String languageLabel;
  final bool isSourceCard;
  final bool selected;
"""
new = """class _LibraryCatalogCard extends StatelessWidget {
  const _LibraryCatalogCard({
    required this.item,
    required this.languageLabel,
    required this.selected,
    required this.onTap,
  });

  final LibraryCatalogItem item;
  final String languageLabel;
  final bool selected;
"""
assert old in screen
screen = screen.replace(old, new, 1)

screen = screen.replace("""                                  isSourceCard
                                      ? Symbols.extension_rounded
                                      : Symbols.menu_book_rounded,
""", """                                  Symbols.menu_book_rounded,
""", 1)
screen = screen.replace("""                                    isSourceCard
                                        ? Symbols.extension_rounded
                                        : Symbols.menu_book_rounded,
""", """                                    Symbols.menu_book_rounded,
""", 1)

# Restore title count wording now that the grid contains titles only.
screen = screen.replace("""    final countLabel = locale == 'fr'
        ? '${visible.length} élément${visible.length > 1 ? 's' : ''}'
        : '${visible.length} item${visible.length == 1 ? '' : 's'}';
""", """    final countLabel = locale == 'fr'
        ? '${visible.length} titre${visible.length > 1 ? 's' : ''}'
        : '${visible.length} title${visible.length == 1 ? '' : 's'}';
""", 1)

# Send source-specific Referer/User-Agent headers for external cover images.
old = """                            : Image.network(
                                item.coverUrl!,
                                fit: BoxFit.cover,
"""
new = """                            : Image.network(
                                item.coverUrl!,
                                headers: _imageHeaders,
                                fit: BoxFit.cover,
"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);

    return AnimatedContainer(
"""
new = """  Map<String, String>? get _imageHeaders {
    final raw = item.raw['imageHeaders'];
    if (raw is! Map) return null;
    final result = <String, String>{};
    for (final entry in raw.entries) {
      final key = entry.key?.toString().trim() ?? '';
      final value = entry.value?.toString().trim() ?? '';
      if (key.isNotEmpty && value.isNotEmpty) result[key] = value;
    }
    return result.isEmpty ? null : result;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);

    return AnimatedContainer(
"""
# This pattern occurs for multiple widgets; target occurrence after LibraryCatalogCard.
card_index = screen.index('class _LibraryCatalogCard extends StatelessWidget')
sub = screen[card_index:]
assert old in sub
sub = sub.replace(old, new, 1)
screen = screen[:card_index] + sub

# Reader accepts HTTP headers for page image requests.
old = """    this.text,
    this.pages = const [],
    this.bookmarkId,
  });
"""
new = """    this.text,
    this.pages = const [],
    this.imageHeaders,
    this.bookmarkId,
  });
"""
assert old in reader
reader = reader.replace(old, new, 1)

old = """  final String? text;
  final List<String> pages;

  /// Stable identity used to persist a bookmark.
"""
new = """  final String? text;
  final List<String> pages;
  final Map<String, String>? imageHeaders;

  /// Stable identity used to persist a bookmark.
"""
assert old in reader
reader = reader.replace(old, new, 1)

old = """                    child: Image.network(
                      widget.pages[index],
                      fit: BoxFit.contain,
"""
new = """                    child: Image.network(
                      widget.pages[index],
                      headers: widget.imageHeaders,
                      fit: BoxFit.contain,
"""
assert old in reader
reader = reader.replace(old, new, 1)

screen_path.write_text(screen, encoding='utf-8')
reader_path.write_text(reader, encoding='utf-8')
