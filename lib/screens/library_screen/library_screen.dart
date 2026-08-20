import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/services/gamepad/gamepad_navigation_manager.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_mangadex_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/neo_glass.dart';

/// Native reading Library for iOS.
///
/// The hub keeps provider management, local-library entry and native content in
/// one controller-friendly surface. Provider websites are never embedded.
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  static LibraryScreenState? _currentState;

  static bool navigateLeft() => _currentState?._navigateHorizontal(-1) ?? false;
  static bool navigateRight() => _currentState?._navigateHorizontal(1) ?? false;
  static bool navigateUp() => _currentState?._navigateVertical(-1) ?? false;
  static bool navigateDown() => _currentState?._navigateVertical(1) ?? false;
  static void selectCurrent() => _currentState?._activateSelection();
  static void backCurrent() => _currentState?._back();
  static void deleteCurrent() => _currentState?._deleteSelectedAddon();

  @override
  State<LibraryScreen> createState() => LibraryScreenState();
}

enum _LibraryView { hub, addons, local }

enum _HubFocus { shortcuts, filters, books }

class _NativeLibraryEntry {
  const _NativeLibraryEntry({
    required this.providerId,
    required this.item,
    this.source,
  });

  final String providerId;
  final LibraryAddon? source;
  final LibraryCatalogItem item;

  bool get isMangaDex => providerId == LibraryMangaDexService.providerId;
}

class LibraryScreenState extends State<LibraryScreen> {
  final LibraryAddonService _addonService = LibraryAddonService.instance;
  final LibraryCatalogService _catalogService = LibraryCatalogService.instance;
  final LibraryMangaDexService _mangaDexService = LibraryMangaDexService.instance;

  final ScrollController _libraryScrollController = ScrollController();
  final Map<String, GlobalKey> _bookKeys = <String, GlobalKey>{};

  _LibraryView _view = _LibraryView.hub;
  _HubFocus _hubFocus = _HubFocus.shortcuts;

  int _hubSelectedIndex = 0;
  int _filterSelectedIndex = 0;
  int _addonSelectedIndex = 0;
  int _librarySelectedIndex = 0;
  int _libraryColumns = 5;
  double _libraryRowExtent = 220;

  String _languageFilter = 'all';
  bool _sortAscending = true;
  String? _alphabetAnchor;

  bool _loadingAddons = true;
  bool _loadingLibrary = true;
  int _catalogFailures = 0;
  List<LibraryAddon> _addons = const [];
  List<_NativeLibraryEntry> _libraryItems = const [];

  int get _addonSelectionCount => 3 + _addons.length;

  List<_NativeLibraryEntry> get _visibleLibraryItems {
    final items = _libraryItems.where((entry) {
      if (_languageFilter == 'all') return true;
      return _itemLanguageCodes(entry).contains(_languageFilter);
    }).toList();
    items.sort((a, b) {
      final comparison = a.item.title.toLowerCase().compareTo(
        b.item.title.toLowerCase(),
      );
      return _sortAscending ? comparison : -comparison;
    });
    return items;
  }

  List<String> get _languageOptions {
    final languages = <String>{};
    for (final entry in _libraryItems) {
      languages.addAll(_itemLanguageCodes(entry));
    }
    final sorted = languages.toList()..sort();
    final preferred = <String>['fr', 'en'];
    sorted.sort((a, b) {
      final ai = preferred.indexOf(a);
      final bi = preferred.indexOf(b);
      if (ai >= 0 || bi >= 0) {
        if (ai < 0) return 1;
        if (bi < 0) return -1;
        return ai.compareTo(bi);
      }
      return a.compareTo(b);
    });
    return <String>['all', ...sorted];
  }

  @override
  void initState() {
    super.initState();
    LibraryScreen._currentState = this;
    _loadAddons();
  }

  @override
  void dispose() {
    if (identical(LibraryScreen._currentState, this)) {
      LibraryScreen._currentState = null;
    }
    _libraryScrollController.dispose();
    super.dispose();
  }

  Future<void> _loadAddons() async {
    final addons = await _addonService.load();
    if (!mounted) return;
    setState(() {
      _addons = addons;
      _loadingAddons = false;
      if (_addonSelectedIndex >= _addonSelectionCount) {
        _addonSelectedIndex = (_addonSelectionCount - 1).clamp(0, 9999);
      }
    });
    await _refreshNativeLibrary(addons);
  }

  Future<void> _refreshNativeLibrary([List<LibraryAddon>? installed]) async {
    final addons = installed ?? _addons;
    if (mounted) {
      setState(() {
        _loadingLibrary = true;
        _catalogFailures = 0;
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
      _libraryItems = List.unmodifiable(entries);
      _catalogFailures = failures;
      _loadingLibrary = false;
      _alphabetAnchor = null;
      final visible = _visibleLibraryItems;
      if (visible.isEmpty) {
        _librarySelectedIndex = 0;
        if (_hubFocus == _HubFocus.books) _hubFocus = _HubFocus.filters;
      } else if (_librarySelectedIndex >= visible.length) {
        _librarySelectedIndex = visible.length - 1;
      }
    });
  }

  Set<String> _itemLanguageCodes(_NativeLibraryEntry entry) {
    final result = <String>{};

    void addLanguage(dynamic value) {
      if (value == null) return;
      if (value is Iterable) {
        for (final item in value) {
          addLanguage(item);
        }
        return;
      }
      final raw = value.toString().trim().toLowerCase();
      if (raw.isEmpty || raw == 'null') return;
      final normalized = raw.replaceAll('_', '-').split('-').first;
      if (RegExp(r'^[a-z]{2,3}$').hasMatch(normalized)) {
        result.add(normalized);
      }
    }

    final raw = entry.item.raw;
    addLanguage(raw['language']);
    addLanguage(raw['languages']);
    addLanguage(raw['lang']);

    final attributes = raw['attributes'];
    if (attributes is Map) {
      addLanguage(attributes['availableTranslatedLanguages']);
      addLanguage(attributes['translatedLanguage']);
      addLanguage(attributes['originalLanguage']);
      final titles = attributes['title'];
      if (titles is Map) addLanguage(titles.keys);
      final descriptions = attributes['description'];
      if (descriptions is Map) addLanguage(descriptions.keys);
    }

    // Gallica's public-domain OPDS feed is primarily French. Keep its books
    // filterable even when an individual Atom entry omits dc:language.
    if (result.isEmpty && entry.source?.isGallicaSource == true) {
      result.add('fr');
    }

    return result;
  }

  String _languageLabel(String code) {
    if (code == 'all') {
      return Localizations.localeOf(context).languageCode == 'fr'
          ? 'Toutes'
          : 'All';
    }
    const labels = <String, String>{
      'fr': 'Français',
      'en': 'English',
      'es': 'Español',
      'de': 'Deutsch',
      'it': 'Italiano',
      'pt': 'Português',
      'ja': '日本語',
      'ko': '한국어',
      'zh': '中文',
      'ru': 'Русский',
      'id': 'Indonesia',
    };
    return labels[code] ?? code.toUpperCase();
  }

  String _bookKey(_NativeLibraryEntry entry) =>
      '${entry.providerId}|${entry.item.id}|${entry.item.title}';

  GlobalKey _keyForBook(_NativeLibraryEntry entry) =>
      _bookKeys.putIfAbsent(_bookKey(entry), GlobalKey.new);

  void _ensureSelectedBookVisible() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _hubFocus != _HubFocus.books) return;
      final visible = _visibleLibraryItems;
      if (_librarySelectedIndex < 0 ||
          _librarySelectedIndex >= visible.length) {
        return;
      }

      final context = _keyForBook(visible[_librarySelectedIndex]).currentContext;
      if (context != null) {
        Scrollable.ensureVisible(
          context,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          alignment: 0.22,
        );
        return;
      }

      if (!_libraryScrollController.hasClients) return;
      final row = _librarySelectedIndex ~/ _libraryColumns;
      final top = row * _libraryRowExtent;
      final position = _libraryScrollController.position;
      final viewport = position.viewportDimension;
      final current = position.pixels;
      var target = current;
      if (top < current) {
        target = top;
      } else if (top + _libraryRowExtent > current + viewport) {
        target = top + _libraryRowExtent - viewport;
      }
      target = target.clamp(0.0, position.maxScrollExtent);
      if ((target - current).abs() > 1) {
        _libraryScrollController.animateTo(
          target,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }

  bool _navigateHorizontal(int delta) {
    if (_view == _LibraryView.addons) {
      if (_addonSelectedIndex > 2) return false;
      final next = (_addonSelectedIndex + delta).clamp(0, 2);
      if (next == _addonSelectedIndex) return false;
      setState(() => _addonSelectedIndex = next);
      return true;
    }
    if (_view != _LibraryView.hub) return false;

    switch (_hubFocus) {
      case _HubFocus.shortcuts:
        final next = (_hubSelectedIndex + delta).clamp(0, 1);
        if (next == _hubSelectedIndex) return false;
        setState(() => _hubSelectedIndex = next);
        return true;
      case _HubFocus.filters:
        final next = (_filterSelectedIndex + delta).clamp(0, 2);
        if (next == _filterSelectedIndex) return false;
        setState(() => _filterSelectedIndex = next);
        return true;
      case _HubFocus.books:
        final visible = _visibleLibraryItems;
        if (visible.isEmpty) return false;
        final next = (_librarySelectedIndex + delta).clamp(
          0,
          visible.length - 1,
        );
        if (next == _librarySelectedIndex) return false;
        setState(() => _librarySelectedIndex = next);
        _ensureSelectedBookVisible();
        return true;
    }
  }

  bool _navigateVertical(int delta) {
    if (_view == _LibraryView.addons) {
      if (_addonSelectionCount <= 0) return false;
      final next = (_addonSelectedIndex + delta).clamp(
        0,
        _addonSelectionCount - 1,
      );
      if (next == _addonSelectedIndex) return false;
      setState(() => _addonSelectedIndex = next);
      return true;
    }
    if (_view != _LibraryView.hub) return false;

    final visible = _visibleLibraryItems;
    switch (_hubFocus) {
      case _HubFocus.shortcuts:
        if (delta <= 0 || _loadingLibrary) return false;
        setState(() => _hubFocus = _HubFocus.filters);
        return true;
      case _HubFocus.filters:
        if (delta < 0) {
          setState(() => _hubFocus = _HubFocus.shortcuts);
          return true;
        }
        if (visible.isEmpty) return false;
        setState(() {
          _hubFocus = _HubFocus.books;
          _librarySelectedIndex = _librarySelectedIndex.clamp(
            0,
            visible.length - 1,
          );
        });
        _ensureSelectedBookVisible();
        return true;
      case _HubFocus.books:
        if (visible.isEmpty) return false;
        final next = _librarySelectedIndex + (delta * _libraryColumns);
        if (delta < 0 && next < 0) {
          setState(() => _hubFocus = _HubFocus.filters);
          return true;
        }
        final clamped = next.clamp(0, visible.length - 1);
        if (clamped == _librarySelectedIndex) return false;
        setState(() => _librarySelectedIndex = clamped);
        _ensureSelectedBookVisible();
        return true;
    }
  }

  void _activateSelection() {
    if (_view == _LibraryView.hub) {
      if (_hubFocus == _HubFocus.shortcuts) {
        if (_hubSelectedIndex == 0) {
          setState(() {
            _view = _LibraryView.addons;
            _addonSelectedIndex = 0;
          });
        } else {
          setState(() => _view = _LibraryView.local);
        }
        return;
      }

      if (_hubFocus == _HubFocus.filters) {
        if (_filterSelectedIndex == 0) {
          _cycleLanguageFilter();
        } else if (_filterSelectedIndex == 1) {
          _toggleAlphabeticalSort();
        } else {
          _jumpToNextLetter();
        }
        return;
      }

      final visible = _visibleLibraryItems;
      if (_librarySelectedIndex >= 0 &&
          _librarySelectedIndex < visible.length) {
        _openCatalogItem(visible[_librarySelectedIndex]);
      }
      return;
    }

    if (_view == _LibraryView.local) {
      _backToHub(selectLocal: true);
      return;
    }

    if (_addonSelectedIndex == 0) {
      _backToHub();
    } else if (_addonSelectedIndex == 1) {
      _installFromUrl();
    } else if (_addonSelectedIndex == 2) {
      _installFromLocalManifest();
    } else {
      final addonIndex = _addonSelectedIndex - 3;
      if (addonIndex >= 0 && addonIndex < _addons.length) {
        _showAddonDetails(_addons[addonIndex]);
      }
    }
  }

  void _back() {
    if (_view == _LibraryView.addons || _view == _LibraryView.local) {
      _backToHub();
      return;
    }

    if (_hubFocus == _HubFocus.books) {
      setState(() => _hubFocus = _HubFocus.filters);
    } else if (_hubFocus == _HubFocus.filters) {
      setState(() => _hubFocus = _HubFocus.shortcuts);
    }
  }

  void _backToHub({bool selectLocal = false}) {
    setState(() {
      _view = _LibraryView.hub;
      _hubFocus = _HubFocus.shortcuts;
      _hubSelectedIndex = selectLocal ? 1 : 0;
    });
  }

  Future<void> _deleteSelectedAddon() async {
    if (_view != _LibraryView.addons || _addonSelectedIndex < 3) return;
    final addonIndex = _addonSelectedIndex - 3;
    if (addonIndex < 0 || addonIndex >= _addons.length) return;
    await _confirmRemoveAddon(_addons[addonIndex]);
  }

  void _cycleLanguageFilter() {
    final options = _languageOptions;
    if (options.isEmpty) return;
    var index = options.indexOf(_languageFilter);
    if (index < 0) index = 0;
    final next = options[(index + 1) % options.length];
    setState(() {
      _languageFilter = next;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
  }

  void _toggleAlphabeticalSort() {
    setState(() {
      _sortAscending = !_sortAscending;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
  }

  void _jumpToNextLetter() {
    final visible = _visibleLibraryItems;
    if (visible.isEmpty) return;
    final letters = visible
        .map((entry) => _firstLetter(entry.item.title))
        .where((letter) => letter.isNotEmpty)
        .toSet()
        .toList()
      ..sort();
    if (letters.isEmpty) return;

    final current = _alphabetAnchor;
    final currentIndex = current == null ? -1 : letters.indexOf(current);
    final nextLetter = letters[(currentIndex + 1) % letters.length];
    final itemIndex = visible.indexWhere(
      (entry) => _firstLetter(entry.item.title) == nextLetter,
    );
    if (itemIndex < 0) return;

    setState(() {
      _alphabetAnchor = nextLetter;
      _hubFocus = _HubFocus.books;
      _librarySelectedIndex = itemIndex;
    });
    _ensureSelectedBookVisible();
  }

  String _firstLetter(String title) {
    final trimmed = title.trim();
    if (trimmed.isEmpty) return '';
    final first = trimmed.substring(0, 1).toUpperCase();
    return RegExp(r'[A-ZÀ-ÖØ-Þ0-9]').hasMatch(first) ? first : '#';
  }

  void _tapHubCard(int index) {
    SfxService().playNavSound();
    setState(() {
      _hubFocus = _HubFocus.shortcuts;
      _hubSelectedIndex = index;
    });
    _activateSelection();
  }

  void _tapAddonSelection(int index) {
    SfxService().playNavSound();
    setState(() => _addonSelectedIndex = index);
    _activateSelection();
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 3)),
      );
  }

  Future<String?> _showUrlDialog() async {
    final controller = TextEditingController();
    const layerId = 'library_addon_url_dialog';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    try {
      return await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => AlertDialog(
          title: Text(AppLocale.libraryAddonUrlTitle.getString(dialogContext)),
          content: SizedBox(
            width: 520.r,
            child: TextField(
              controller: controller,
              autofocus: true,
              keyboardType: TextInputType.url,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                hintText: 'https://example.com/neostation-library.json',
                helperText: AppLocale.libraryAddonUrlHelp.getString(
                  dialogContext,
                ),
              ),
              onSubmitted: (value) {
                if (value.trim().isNotEmpty) {
                  Navigator.of(dialogContext).pop(value.trim());
                }
              },
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(AppLocale.cancel.getString(dialogContext)),
            ),
            FilledButton(
              onPressed: () {
                final value = controller.text.trim();
                if (value.isNotEmpty) Navigator.of(dialogContext).pop(value);
              },
              child: Text(AppLocale.libraryAddonInstall.getString(dialogContext)),
            ),
          ],
        ),
      );
    } finally {
      controller.dispose();
      GamepadNavigationManager.popLayer(layerId);
    }
  }

  Future<void> _installFromUrl() async {
    final url = await _showUrlDialog();
    if (!mounted || url == null || url.isEmpty) return;

    _showMessage(AppLocale.libraryAddonInstalling.getString(context));
    try {
      final result = await _addonService.installDocumentFromUrl(url);
      await _loadAddons();
      if (!mounted) return;
      if (result.format == LibraryAddonDocumentFormat.tachiyomiRepository) {
        _showMessage(
          AppLocale.libraryAddonCount
              .getString(context)
              .replaceFirst('{count}', result.totalCount.toString()),
        );
      } else {
        final addon = result.addons.single;
        _showMessage(
          result.updatedCount > 0
              ? AppLocale.libraryAddonUpdated
                    .getString(context)
                    .replaceFirst('{name}', addon.name)
              : AppLocale.libraryAddonInstalled
                    .getString(context)
                    .replaceFirst('{name}', addon.name),
        );
      }
    } on LibraryAddonException catch (error) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', error.message),
      );
    } catch (error) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', error.toString()),
      );
    }
  }

  Future<void> _installFromLocalManifest() async {
    final result = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['json'],
      allowMultiple: false,
      withData: true,
    );
    if (!mounted || result == null || result.files.isEmpty) return;

    final picked = result.files.single;
    try {
      final bytes =
          picked.bytes ??
          (picked.path == null ? null : await File(picked.path!).readAsBytes());
      if (bytes == null) {
        throw const LibraryAddonException('Unable to read selected manifest.');
      }
      final install = await _addonService.installDocumentFromJson(
        utf8.decode(bytes),
        origin: 'file:${picked.name}',
      );
      await _loadAddons();
      if (!mounted) return;
      if (install.format == LibraryAddonDocumentFormat.tachiyomiRepository) {
        _showMessage(
          AppLocale.libraryAddonCount
              .getString(context)
              .replaceFirst('{count}', install.totalCount.toString()),
        );
      } else {
        final addon = install.addons.single;
        _showMessage(
          install.updatedCount > 0
              ? AppLocale.libraryAddonUpdated
                    .getString(context)
                    .replaceFirst('{name}', addon.name)
              : AppLocale.libraryAddonInstalled
                    .getString(context)
                    .replaceFirst('{name}', addon.name),
        );
      }
    } on LibraryAddonException catch (error) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', error.message),
      );
    } catch (error) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', error.toString()),
      );
    }
  }

  Future<void> _showAddonDetails(LibraryAddon addon) async {
    const layerId = 'library_addon_details_dialog';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    try {
      final location = addon.baseUrl == null
          ? 'local'
          : (Uri.tryParse(addon.baseUrl!)?.host ?? addon.baseUrl!);
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(addon.name),
          content: SizedBox(
            width: 520.r,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('v${addon.version} • $location'),
                if (addon.description.isNotEmpty) ...[
                  SizedBox(height: 10.r),
                  Text(addon.description),
                ],
                if (addon.isTachiyomiRepositorySource) ...[
                  SizedBox(height: 10.r),
                  Text(
                    'Tachiyomi/Mihon • ${addon.language ?? 'all'} • iOS metadata',
                    style: Theme.of(dialogContext).textTheme.bodySmall?.copyWith(
                      color: Theme.of(dialogContext).colorScheme.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (addon.androidPackage != null)
                    Text(
                      addon.androidPackage!,
                      style: Theme.of(dialogContext).textTheme.bodySmall,
                    ),
                ],
                SizedBox(height: 12.r),
                Text(
                  addon.origin,
                  style: Theme.of(dialogContext).textTheme.bodySmall?.copyWith(
                    color: Theme.of(dialogContext)
                        .colorScheme
                        .onSurface
                        .withValues(alpha: 0.6),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(AppLocale.close.getString(dialogContext)),
            ),
          ],
        ),
      );
    } finally {
      GamepadNavigationManager.popLayer(layerId);
    }
  }

  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {
    if (entry.isMangaDex) {
      await _openMangaDexTitle(entry.item);
      return;
    }

    final item = entry.item;
    if (item.pageUrls.isNotEmpty) {
      await _showPageReader(item.title, item.pageUrls, subtitle: item.subtitle);
      return;
    }

    String text;
    try {
      _showMessage(
        Localizations.localeOf(context).languageCode == 'fr'
            ? 'Chargement du livre…'
            : 'Loading book…',
      );
      text = await _catalogService.loadReadableText(item);
    } on LibraryAddonException catch (error) {
      if (item.description.isNotEmpty) {
        text = item.description;
      } else {
        _showMessage(error.message);
        return;
      }
    }
    if (!mounted) return;
    await _showTextReader(item, text);
  }

  Future<void> _showTextReader(LibraryCatalogItem item, String text) async {
    const layerId = 'library_catalog_reader';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    try {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) {
          final size = MediaQuery.sizeOf(dialogContext);
          final theme = Theme.of(dialogContext);
          return Dialog(
            backgroundColor: Colors.transparent,
            insetPadding: EdgeInsets.symmetric(horizontal: 22.r, vertical: 18.r),
            child: NeoGlass(
              role: GlassSurfaceRole.card,
              borderRadius: BorderRadius.circular(18.r),
              enableBackdropBlur: true,
              showSheen: false,
              child: SizedBox(
                width: size.width * 0.94,
                height: size.height * 0.88,
                child: Padding(
                  padding: EdgeInsets.all(18.r),
                  child: Column(
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (item.coverUrl != null) ...[
                            ClipRRect(
                              borderRadius: BorderRadius.circular(9.r),
                              child: SizedBox(
                                width: 74.r,
                                height: 104.r,
                                child: Image.network(
                                  item.coverUrl!,
                                  fit: BoxFit.cover,
                                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                                ),
                              ),
                            ),
                            SizedBox(width: 16.r),
                          ],
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  item.title,
                                  maxLines: 3,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.headlineSmall?.copyWith(
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                if (item.subtitle.isNotEmpty) ...[
                                  SizedBox(height: 5.r),
                                  Text(
                                    item.subtitle,
                                    style: theme.textTheme.titleMedium?.copyWith(
                                      color: theme.colorScheme.onSurface.withValues(
                                        alpha: 0.7,
                                      ),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                          IconButton(
                            tooltip: AppLocale.close.getString(dialogContext),
                            onPressed: () => Navigator.of(dialogContext).pop(),
                            icon: const Icon(Symbols.close_rounded),
                          ),
                        ],
                      ),
                      SizedBox(height: 14.r),
                      Divider(color: theme.colorScheme.outline.withValues(alpha: 0.18)),
                      SizedBox(height: 8.r),
                      Expanded(
                        child: Scrollbar(
                          thumbVisibility: true,
                          child: SingleChildScrollView(
                            padding: EdgeInsets.fromLTRB(8.r, 4.r, 18.r, 28.r),
                            child: SelectableText(
                              text,
                              style: theme.textTheme.bodyLarge?.copyWith(
                                height: 1.55,
                                fontSize: 16.r.clamp(14.0, 20.0),
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
          );
        },
      );
    } finally {
      GamepadNavigationManager.popLayer(layerId);
    }
  }

  Future<void> _showPageReader(
    String title,
    List<String> pages, {
    String subtitle = '',
  }) async {
    const layerId = 'library_page_reader';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    try {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) {
          final size = MediaQuery.sizeOf(dialogContext);
          final theme = Theme.of(dialogContext);
          return Dialog(
            backgroundColor: Colors.transparent,
            insetPadding: EdgeInsets.symmetric(horizontal: 18.r, vertical: 14.r),
            child: NeoGlass(
              role: GlassSurfaceRole.card,
              borderRadius: BorderRadius.circular(18.r),
              enableBackdropBlur: true,
              showSheen: false,
              child: SizedBox(
                width: size.width * 0.95,
                height: size.height * 0.90,
                child: Column(
                  children: [
                    Padding(
                      padding: EdgeInsets.fromLTRB(18.r, 12.r, 10.r, 8.r),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  title,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.titleLarge?.copyWith(
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                if (subtitle.isNotEmpty)
                                  Text(
                                    subtitle,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      color: theme.colorScheme.onSurface.withValues(
                                        alpha: 0.65,
                                      ),
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
                    Expanded(
                      child: ListView.separated(
                        cacheExtent: 1800.r,
                        padding: EdgeInsets.fromLTRB(14.r, 6.r, 14.r, 24.r),
                        itemCount: pages.length,
                        separatorBuilder: (_, __) => SizedBox(height: 10.r),
                        itemBuilder: (_, index) => Image.network(
                          pages[index],
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
                            child: const Center(
                              child: Icon(Symbols.broken_image_rounded),
                            ),
                          ),
                        ),
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
  }

  Future<void> _openMangaDexTitle(LibraryCatalogItem item) async {
    final mangaId = item.raw['mangadexId']?.toString().trim() ?? item.id;
    final localeLanguage = Localizations.localeOf(context).languageCode;
    final languages = <String>{
      if (_languageFilter != 'all') _languageFilter,
      localeLanguage,
      'en',
    }.toList();

    _showMessage(
      localeLanguage == 'fr' ? 'Chargement des chapitres…' : 'Loading chapters…',
    );
    List<LibraryMangaDexChapter> chapters;
    try {
      chapters = await _mangaDexService.loadChapters(
        mangaId,
        languages: languages,
      );
    } on LibraryAddonException catch (error) {
      _showMessage(error.message);
      return;
    }
    if (!mounted || chapters.isEmpty) {
      if (mounted) {
        _showMessage(
          localeLanguage == 'fr'
              ? 'Aucun chapitre disponible dans les langues sélectionnées.'
              : 'No chapters are available in the selected languages.',
        );
      }
      return;
    }

    const layerId = 'library_mangadex_chapters';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    LibraryMangaDexChapter? selectedChapter;
    try {
      selectedChapter = await showDialog<LibraryMangaDexChapter>(
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
                            child: Text(
                              item.title,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.w800,
                              ),
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
                            if (chapter.volume.isNotEmpty) 'Vol. ${chapter.volume}',
                            if (chapter.chapter.isNotEmpty) 'Ch. ${chapter.chapter}',
                            if (chapter.language.isNotEmpty)
                              chapter.language.toUpperCase(),
                          ].join(' • ');
                          return ListTile(
                            title: Text(chapter.displayTitle),
                            subtitle: details.isEmpty ? null : Text(details),
                            trailing: const Icon(Symbols.menu_book_rounded),
                            onTap: () => Navigator.of(dialogContext).pop(chapter),
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
    final pages = await _mangaDexService.loadChapterPages(selectedChapter.id);
    if (!mounted) return;
    await _showPageReader(
      '${item.title} — ${selectedChapter.displayTitle}',
      pages,
      subtitle: selectedChapter.language.toUpperCase(),
    );
  }

  Future<void> _confirmRemoveAddon(LibraryAddon addon) async {
    const layerId = 'library_addon_remove_dialog';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    bool confirmed = false;
    try {
      confirmed =
          await showDialog<bool>(
            context: context,
            barrierDismissible: false,
            builder: (dialogContext) => AlertDialog(
              title: Text(AppLocale.libraryAddonRemoveTitle.getString(dialogContext)),
              content: Text(
                AppLocale.libraryAddonRemoveBody
                    .getString(dialogContext)
                    .replaceFirst('{name}', addon.name),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(false),
                  child: Text(AppLocale.cancel.getString(dialogContext)),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(dialogContext).pop(true),
                  child: Text(AppLocale.delete.getString(dialogContext)),
                ),
              ],
            ),
          ) ??
          false;
    } finally {
      GamepadNavigationManager.popLayer(layerId);
    }

    if (!confirmed) return;
    await _addonService.remove(addon.id);
    await _loadAddons();
    if (!mounted) return;
    setState(() {
      _addonSelectedIndex = _addonSelectedIndex.clamp(
        0,
        (_addonSelectionCount - 1).clamp(0, 9999),
      );
    });
    _showMessage(
      AppLocale.libraryAddonRemoved
          .getString(context)
          .replaceFirst('{name}', addon.name),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(24.r, 54.r, 24.r, 18.r),
        child: switch (_view) {
          _LibraryView.hub => _buildHub(context),
          _LibraryView.addons => _buildAddons(context),
          _LibraryView.local => _buildLocalLibrary(context),
        },
      ),
    );
  }

  Widget _buildHeader(BuildContext context, {Widget? trailing}) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SizedBox(
          width: 58.r,
          height: 58.r,
          child: Padding(
            padding: EdgeInsets.all(2.r),
            child: Image.asset(
              'assets/images/icons/library-manga-clean.webp',
              fit: BoxFit.contain,
              alignment: Alignment.center,
              filterQuality: FilterQuality.high,
            ),
          ),
        ),
        SizedBox(width: 14.r),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                AppLocale.library.getString(context),
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(height: 3.r),
              Text(
                AppLocale.libraryIntro.getString(context),
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.68),
                ),
              ),
            ],
          ),
        ),
        if (trailing != null) trailing,
      ],
    );
  }

  Widget _buildHub(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(context),
        SizedBox(height: 20.r),
        Row(
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
        SizedBox(height: 12.r),
        _buildFilters(context),
        SizedBox(height: 10.r),
        Expanded(child: _buildNativeLibrary(context, theme)),
      ],
    );
  }

  Widget _buildFilters(BuildContext context) {
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
              _cycleLanguageFilter();
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
              _toggleAlphabeticalSort();
            },
          ),
        ),
        SizedBox(width: 10.r),
        Expanded(
          child: _FilterControl(
            selected:
                _hubFocus == _HubFocus.filters && _filterSelectedIndex == 2,
            icon: Symbols.abc_rounded,
            label: locale == 'fr' ? 'Index' : 'Index',
            value: _alphabetAnchor == null ? 'A–Z' : _alphabetAnchor!,
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = 2;
              });
              _jumpToNextLetter();
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
  }

  Widget _buildNativeLibrary(BuildContext context, ThemeData theme) {
    if (_loadingLibrary) {
      return const Center(child: CircularProgressIndicator());
    }

    final visible = _visibleLibraryItems;
    if (visible.isEmpty) {
      final hasContent = _libraryItems.isNotEmpty;
      return Align(
        alignment: const Alignment(0, -0.48),
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
            SizedBox(height: 5.r),
            if (_catalogFailures > 0)
              Text(
                '$_catalogFailures catalogue(s) n’ont pas pu être chargés.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error.withValues(alpha: 0.85),
                ),
              ),
          ],
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        const targetExtent = 155.0;
        final columns = (constraints.maxWidth / targetExtent)
            .floor()
            .clamp(2, 8);
        _libraryColumns = columns;
        final totalSpacing = (columns - 1) * 12.r;
        final cardWidth = (constraints.maxWidth - totalSpacing) / columns;
        _libraryRowExtent = (cardWidth / 0.68) + 12.r;

        return GridView.builder(
          controller: _libraryScrollController,
          cacheExtent: _libraryRowExtent * 2.4,
          padding: EdgeInsets.only(bottom: 32.r),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisSpacing: 12.r,
            crossAxisSpacing: 12.r,
            childAspectRatio: 0.68,
          ),
          itemCount: visible.length,
          itemBuilder: (context, index) {
            final entry = visible[index];
            final languages = _itemLanguageCodes(entry);
            final languageLabel = languages.isEmpty
                ? ''
                : languages.map((code) => code.toUpperCase()).take(2).join(' • ');
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
        );
      },
    );
  }

  Widget _buildAddons(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(
          context,
          trailing: FilledButton.tonalIcon(
            onPressed: _backToHub,
            icon: const Icon(Symbols.arrow_back_rounded),
            label: Text(AppLocale.back.getString(context)),
          ),
        ),
        SizedBox(height: 18.r),
        Text(
          AppLocale.libraryAddons.getString(context),
          style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
        ),
        SizedBox(height: 10.r),
        Row(
          children: [
            Expanded(
              child: _LibraryEntryCard(
                selected: _addonSelectedIndex == 0,
                icon: Symbols.arrow_back_rounded,
                title: AppLocale.back.getString(context),
                subtitle: Localizations.localeOf(context).languageCode == 'fr'
                    ? 'Revenir à la Bibliothèque et choisir une autre section.'
                    : 'Return to the Library and choose another section.',
                onTap: () => _tapAddonSelection(0),
              ),
            ),
            SizedBox(width: 10.r),
            Expanded(
              child: _LibraryEntryCard(
                selected: _addonSelectedIndex == 1,
                icon: Symbols.language_rounded,
                title: AppLocale.libraryAddonAddUrl.getString(context),
                subtitle: AppLocale.libraryAddonAddUrlSubtitle.getString(context),
                onTap: () => _tapAddonSelection(1),
              ),
            ),
            SizedBox(width: 10.r),
            Expanded(
              child: _LibraryEntryCard(
                selected: _addonSelectedIndex == 2,
                icon: Symbols.file_open_rounded,
                title: AppLocale.libraryAddonImportFile.getString(context),
                subtitle: AppLocale.libraryAddonImportFileSubtitle.getString(context),
                onTap: () => _tapAddonSelection(2),
              ),
            ),
          ],
        ),
        SizedBox(height: 14.r),
        Text(
          AppLocale.libraryAddonInstalledSources.getString(context),
          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
        ),
        SizedBox(height: 8.r),
        Expanded(
          child: _loadingAddons
              ? const Center(child: CircularProgressIndicator())
              : _addons.isEmpty
                  ? Align(
                      alignment: const Alignment(0, -0.5),
                      child: Text(
                        AppLocale.libraryEmptyTitle.getString(context),
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                        ),
                      ),
                    )
                  : ListView.separated(
                      cacheExtent: 1200.r,
                      padding: EdgeInsets.only(bottom: 26.r),
                      itemCount: _addons.length,
                      separatorBuilder: (_, __) => SizedBox(height: 8.r),
                      itemBuilder: (context, index) {
                        final addon = _addons[index];
                        return _AddonRow(
                          addon: addon,
                          selected: _addonSelectedIndex == index + 3,
                          onTap: () => _tapAddonSelection(index + 3),
                          onDelete: () => _confirmRemoveAddon(addon),
                        );
                      },
                    ),
        ),
      ],
    );
  }

  Widget _buildLocalLibrary(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(
          context,
          trailing: FilledButton.tonalIcon(
            onPressed: () => _backToHub(selectLocal: true),
            icon: const Icon(Symbols.arrow_back_rounded),
            label: Text(AppLocale.back.getString(context)),
          ),
        ),
        SizedBox(height: 24.r),
        Expanded(
          child: Center(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: 620.r),
              child: NeoGlass(
                role: GlassSurfaceRole.card,
                borderRadius: BorderRadius.circular(16.r),
                enableBackdropBlur: false,
                showSheen: true,
                padding: EdgeInsets.all(24.r),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Symbols.folder_open_rounded,
                      size: 46.r,
                      color: theme.colorScheme.primary,
                    ),
                    SizedBox(height: 12.r),
                    Text(
                      AppLocale.libraryLocal.getString(context),
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    SizedBox(height: 7.r),
                    Text(
                      AppLocale.libraryNextStep.getString(context),
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.68),
                      ),
                    ),
                    SizedBox(height: 16.r),
                    FilledButton.tonalIcon(
                      onPressed: () => _backToHub(selectLocal: true),
                      icon: const Icon(Symbols.arrow_back_rounded),
                      label: Text(AppLocale.back.getString(context)),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _LibraryEntryCard extends StatelessWidget {
  const _LibraryEntryCard({
    required this.selected,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(12.r);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: selected ? theme.colorScheme.primary : Colors.transparent,
          width: selected ? 2.r : 0,
        ),
        boxShadow: selected
            ? [
                BoxShadow(
                  color: theme.colorScheme.primary.withValues(alpha: 0.18),
                  blurRadius: 12.r,
                  spreadRadius: 1.r,
                ),
              ]
            : null,
      ),
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: radius,
        enableBackdropBlur: false,
        showSheen: true,
        padding: EdgeInsets.all(14.r),
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: Row(
            children: [
              Container(
                width: 42.r,
                height: 42.r,
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(10.r),
                ),
                child: Icon(icon, size: 24.r, color: theme.colorScheme.primary),
              ),
              SizedBox(width: 12.r),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 3.r),
                    Text(
                      subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: 6.r),
              Icon(
                Symbols.chevron_right_rounded,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FilterControl extends StatelessWidget {
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);
    return AnimatedContainer(
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
            padding: EdgeInsets.symmetric(horizontal: 12.r, vertical: 9.r),
            child: Row(
              children: [
                Icon(icon, size: 20.r, color: theme.colorScheme.primary),
                SizedBox(width: 8.r),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.58),
                        ),
                      ),
                      Text(
                        value,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Symbols.expand_more_rounded,
                  size: 18.r,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _LibraryCatalogCard extends StatelessWidget {
  const _LibraryCatalogCard({
    required this.item,
    required this.languageLabel,
    required this.selected,
    required this.onTap,
  });

  final LibraryCatalogItem item;
  final String languageLabel;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: selected
              ? theme.colorScheme.primary
              : theme.colorScheme.outline.withValues(alpha: 0.15),
          width: selected ? 2.r : 1.r,
        ),
        boxShadow: selected
            ? [
                BoxShadow(
                  color: theme.colorScheme.primary.withValues(alpha: 0.16),
                  blurRadius: 10.r,
                ),
              ]
            : null,
      ),
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: radius,
        enableBackdropBlur: false,
        showSheen: false,
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: Padding(
            padding: EdgeInsets.all(8.r),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(7.r),
                        child: item.coverUrl == null
                            ? ColoredBox(
                                color: theme.colorScheme.primary.withValues(alpha: 0.10),
                                child: Icon(
                                  Symbols.menu_book_rounded,
                                  color: theme.colorScheme.primary,
                                  size: 34.r,
                                ),
                              )
                            : Image.network(
                                item.coverUrl!,
                                fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => ColoredBox(
                                  color: theme.colorScheme.primary.withValues(
                                    alpha: 0.10,
                                  ),
                                  child: Icon(
                                    Symbols.menu_book_rounded,
                                    color: theme.colorScheme.primary,
                                    size: 34.r,
                                  ),
                                ),
                              ),
                      ),
                      if (languageLabel.isNotEmpty)
                        Positioned(
                          top: 6.r,
                          right: 6.r,
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: 6.r,
                              vertical: 3.r,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.68),
                              borderRadius: BorderRadius.circular(6.r),
                            ),
                            child: Text(
                              languageLabel,
                              style: TextStyle(
                                fontSize: 9.r.clamp(8.0, 12.0),
                                color: Colors.white,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                SizedBox(height: 7.r),
                Text(
                  item.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    height: 1.05,
                  ),
                ),
                if (item.subtitle.isNotEmpty) ...[
                  SizedBox(height: 3.r),
                  Text(
                    item.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.58),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AddonRow extends StatelessWidget {
  const _AddonRow({
    required this.addon,
    required this.selected,
    required this.onTap,
    required this.onDelete,
  });

  final LibraryAddon addon;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);
    final location = addon.baseUrl == null
        ? 'local'
        : (Uri.tryParse(addon.baseUrl!)?.host ?? addon.baseUrl!);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: selected
              ? theme.colorScheme.primary
              : theme.colorScheme.outline.withValues(alpha: 0.14),
          width: selected ? 2.r : 1.r,
        ),
      ),
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: radius,
        enableBackdropBlur: false,
        showSheen: false,
        child: ListTile(
          onTap: onTap,
          leading: addon.iconUrl == null
              ? CircleAvatar(
                  backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.12),
                  child: Icon(
                    addon.isTachiyomiRepositorySource
                        ? Symbols.extension_rounded
                        : Symbols.menu_book_rounded,
                    color: theme.colorScheme.primary,
                  ),
                )
              : ClipRRect(
                  borderRadius: BorderRadius.circular(8.r),
                  child: Image.network(
                    addon.iconUrl!,
                    width: 40.r,
                    height: 40.r,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Icon(
                      Symbols.menu_book_rounded,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ),
          title: Text(
            addon.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
          subtitle: Text(
            'v${addon.version} • $location${addon.language == null ? '' : ' • ${addon.language!.toUpperCase()}'}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          trailing: IconButton(
            tooltip: AppLocale.delete.getString(context),
            onPressed: onDelete,
            icon: const Icon(Symbols.delete_outline_rounded),
          ),
        ),
      ),
    );
  }
}
