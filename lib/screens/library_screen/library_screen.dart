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
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/neo_glass.dart';

/// Native Library hub and declarative source manager.
///
/// Installed sources are providers only: users browse the normalized NeoStation
/// catalog here, never a provider website or WebView. Tachiyomi/Mihon APK-only
/// sources remain installable as metadata until a native iOS adapter exists.
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

enum _LibraryView { hub, addons }

class _NativeLibraryEntry {
  const _NativeLibraryEntry({required this.source, required this.item});

  final LibraryAddon source;
  final LibraryCatalogItem item;
}

class LibraryScreenState extends State<LibraryScreen> {
  final LibraryAddonService _addonService = LibraryAddonService.instance;
  final LibraryCatalogService _catalogService = LibraryCatalogService.instance;

  _LibraryView _view = _LibraryView.hub;
  int _hubSelectedIndex = 0;
  int _addonSelectedIndex = 0;
  int _librarySelectedIndex = 0;
  int _libraryColumns = 5;
  bool _libraryFocused = false;
  bool _loadingAddons = true;
  bool _loadingLibrary = true;
  int _catalogFailures = 0;
  List<LibraryAddon> _addons = const [];
  List<_NativeLibraryEntry> _libraryItems = const [];

  int get _addonSelectionCount => 2 + _addons.length;

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
    super.dispose();
  }

  Future<void> _loadAddons() async {
    final addons = await _addonService.load();
    if (!mounted) return;
    setState(() {
      _addons = addons;
      _loadingAddons = false;
      if (_addonSelectedIndex >= _addonSelectionCount) {
        _addonSelectedIndex = (_addonSelectionCount - 1).clamp(0, 9999).toInt();
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

    for (final addon in addons) {
      // Repository entries backed only by Android APK runtime are intentionally
      // ignored here. They become visible automatically once a native adapter
      // exposes a NeoStation catalog endpoint.
      if (!addon.canBrowseOnIos) continue;
      try {
        final items = await _catalogService.loadCatalog(addon);
        for (final item in items) {
          entries.add(_NativeLibraryEntry(source: addon, item: item));
        }
      } catch (_) {
        failures++;
      }
    }

    entries.sort(
      (a, b) => a.item.title.toLowerCase().compareTo(b.item.title.toLowerCase()),
    );

    if (!mounted) return;
    setState(() {
      _libraryItems = List.unmodifiable(entries);
      _catalogFailures = failures;
      _loadingLibrary = false;
      if (_libraryItems.isEmpty) {
        _librarySelectedIndex = 0;
        _libraryFocused = false;
      } else if (_librarySelectedIndex >= _libraryItems.length) {
        _librarySelectedIndex = _libraryItems.length - 1;
      }
    });
  }

  bool _navigateHorizontal(int delta) {
    if (_view != _LibraryView.hub) return false;

    if (_libraryFocused && _libraryItems.isNotEmpty) {
      final next = (_librarySelectedIndex + delta)
          .clamp(0, _libraryItems.length - 1)
          .toInt();
      if (next == _librarySelectedIndex) return false;
      setState(() => _librarySelectedIndex = next);
      return true;
    }

    final next = (_hubSelectedIndex + delta).clamp(0, 1).toInt();
    if (next == _hubSelectedIndex) return false;
    setState(() => _hubSelectedIndex = next);
    return true;
  }

  bool _navigateVertical(int delta) {
    if (_view == _LibraryView.addons) {
      if (_addonSelectionCount <= 0) return false;
      final next = (_addonSelectedIndex + delta)
          .clamp(0, _addonSelectionCount - 1)
          .toInt();
      if (next == _addonSelectedIndex) return false;
      setState(() => _addonSelectedIndex = next);
      return true;
    }

    if (_libraryItems.isEmpty) return false;
    if (!_libraryFocused) {
      if (delta <= 0) return false;
      setState(() {
        _libraryFocused = true;
        _librarySelectedIndex = _librarySelectedIndex
            .clamp(0, _libraryItems.length - 1)
            .toInt();
      });
      return true;
    }

    final next = _librarySelectedIndex + (delta * _libraryColumns);
    if (delta < 0 && next < 0) {
      setState(() => _libraryFocused = false);
      return true;
    }

    final clamped = next.clamp(0, _libraryItems.length - 1).toInt();
    if (clamped == _librarySelectedIndex) return false;
    setState(() => _librarySelectedIndex = clamped);
    return true;
  }

  void _activateSelection() {
    if (_view == _LibraryView.hub) {
      if (_libraryFocused &&
          _librarySelectedIndex >= 0 &&
          _librarySelectedIndex < _libraryItems.length) {
        _openCatalogItem(_libraryItems[_librarySelectedIndex]);
        return;
      }

      if (_hubSelectedIndex == 0) {
        setState(() {
          _view = _LibraryView.addons;
          _addonSelectedIndex = 0;
          _libraryFocused = false;
        });
      } else {
        _showMessage(AppLocale.libraryNextStep.getString(context));
      }
      return;
    }

    if (_addonSelectedIndex == 0) {
      _installFromUrl();
    } else if (_addonSelectedIndex == 1) {
      _installFromLocalManifest();
    } else {
      final addonIndex = _addonSelectedIndex - 2;
      if (addonIndex >= 0 && addonIndex < _addons.length) {
        _showAddonDetails(_addons[addonIndex]);
      }
    }
  }

  void _back() {
    if (_view == _LibraryView.addons) {
      setState(() {
        _view = _LibraryView.hub;
        _hubSelectedIndex = 0;
        _libraryFocused = false;
      });
      return;
    }

    if (_libraryFocused) {
      setState(() => _libraryFocused = false);
    }
  }

  Future<void> _deleteSelectedAddon() async {
    if (_view != _LibraryView.addons || _addonSelectedIndex < 2) return;
    final addonIndex = _addonSelectedIndex - 2;
    if (addonIndex < 0 || addonIndex >= _addons.length) return;
    await _confirmRemoveAddon(_addons[addonIndex]);
  }

  void _tapHubCard(int index) {
    SfxService().playNavSound();
    setState(() {
      _hubSelectedIndex = index;
      _libraryFocused = false;
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
            width: 430.r,
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
              child: Text(
                AppLocale.libraryAddonInstall.getString(dialogContext),
              ),
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
    } on LibraryAddonException catch (e) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', e.message),
      );
    } catch (e) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', e.toString()),
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
    } on LibraryAddonException catch (e) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', e.message),
      );
    } catch (e) {
      _showMessage(
        AppLocale.libraryAddonError
            .getString(context)
            .replaceFirst('{error}', e.toString()),
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
      final baseUrl = addon.baseUrl;
      final location = baseUrl == null
          ? 'local'
          : (Uri.tryParse(baseUrl)?.host ?? baseUrl);
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(addon.name),
          content: SizedBox(
            width: 430.r,
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
                    style: Theme.of(dialogContext).textTheme.bodySmall
                        ?.copyWith(
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
                    color: Theme.of(dialogContext).colorScheme.onSurface
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
    final item = entry.item;
    const layerId = 'library_catalog_reader';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    try {
      if (item.pageUrls.isNotEmpty) {
        await showDialog<void>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(item.title),
            content: SizedBox(
              width: 680.r,
              height: 540.r,
              child: ListView.separated(
                itemCount: item.pageUrls.length,
                separatorBuilder: (_, _) => SizedBox(height: 12.r),
                itemBuilder: (_, index) => Image.network(
                  item.pageUrls[index],
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
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
        return;
      }

      String text;
      try {
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
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(item.title),
          content: SizedBox(
            width: 680.r,
            height: 540.r,
            child: SingleChildScrollView(child: SelectableText(text)),
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
              title: Text(
                AppLocale.libraryAddonRemoveTitle.getString(dialogContext),
              ),
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
    _addonSelectedIndex = _addonSelectedIndex
        .clamp(0, (_addonSelectionCount - 1).clamp(0, 9999).toInt())
        .toInt();
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
        child: _view == _LibraryView.hub
            ? _buildHub(context)
            : _buildAddons(context),
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
        SizedBox(height: 22.r),
        Row(
          children: [
            Expanded(
              child: _LibraryEntryCard(
                selected: !_libraryFocused && _hubSelectedIndex == 0,
                icon: Symbols.extension_rounded,
                title: AppLocale.libraryAddons.getString(context),
                subtitle: AppLocale.libraryAddonsSubtitle.getString(context),
                onTap: () => _tapHubCard(0),
              ),
            ),
            SizedBox(width: 14.r),
            Expanded(
              child: _LibraryEntryCard(
                selected: !_libraryFocused && _hubSelectedIndex == 1,
                icon: Symbols.folder_open_rounded,
                title: AppLocale.libraryLocal.getString(context),
                subtitle: AppLocale.libraryLocalSubtitle.getString(context),
                onTap: () => _tapHubCard(1),
              ),
            ),
          ],
        ),
        SizedBox(height: 14.r),
        Expanded(child: _buildNativeLibrary(context, theme)),
      ],
    );
  }

  Widget _buildNativeLibrary(BuildContext context, ThemeData theme) {
    if (_loadingLibrary) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_libraryItems.isEmpty) {
      final hasInstalledSources = _addons.isNotEmpty;
      return Align(
        alignment: const Alignment(0, -0.55),
        child: Padding(
          padding: EdgeInsets.only(top: 12.r, bottom: 34.r),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Symbols.collections_bookmark_rounded,
                size: 36.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.35),
              ),
              SizedBox(height: 8.r),
              Text(
                hasInstalledSources
                    ? 'Aucun contenu disponible'
                    : AppLocale.libraryEmptyTitle.getString(context),
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
              SizedBox(height: 4.r),
              ConstrainedBox(
                constraints: BoxConstraints(maxWidth: 620.r),
                child: Text(
                  hasInstalledSources
                      ? 'Les sources sont installées, mais aucune ne fournit encore un catalogue natif compatible avec NeoStation sur iOS.'
                      : AppLocale.libraryEmptySubtitle.getString(context),
                  textAlign: TextAlign.center,
                  maxLines: 3,
                  overflow: TextOverflow.visible,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                    height: 1.25,
                  ),
                ),
              ),
              if (_catalogFailures > 0) ...[
                SizedBox(height: 6.r),
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
        const targetExtent = 155.0;
        final columns = (constraints.maxWidth / targetExtent)
            .floor()
            .clamp(2, 8)
            .toInt();
        _libraryColumns = columns;

        return GridView.builder(
          padding: EdgeInsets.only(bottom: 28.r),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisSpacing: 12.r,
            crossAxisSpacing: 12.r,
            childAspectRatio: 0.68,
          ),
          itemCount: _libraryItems.length,
          itemBuilder: (context, index) {
            final entry = _libraryItems[index];
            return _LibraryCatalogCard(
              item: entry.item,
              selected: _libraryFocused && _librarySelectedIndex == index,
              onTap: () {
                SfxService().playNavSound();
                setState(() {
                  _libraryFocused = true;
                  _librarySelectedIndex = index;
                });
                _openCatalogItem(entry);
              },
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
          trailing: IconButton(
            tooltip: AppLocale.back.getString(context),
            onPressed: _back,
            icon: const Icon(Symbols.arrow_back_rounded),
          ),
        ),
        SizedBox(height: 18.r),
        Text(
          AppLocale.libraryAddons.getString(context),
          style: theme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        SizedBox(height: 10.r),
        Row(
          children: [
            Expanded(
              child: _LibraryEntryCard(
                selected: _addonSelectedIndex == 0,
                icon: Symbols.language_rounded,
                title: AppLocale.libraryAddonAddUrl.getString(context),
                subtitle: AppLocale.libraryAddonAddUrlSubtitle.getString(
                  context,
                ),
                onTap: () => _tapAddonSelection(0),
              ),
            ),
            SizedBox(width: 14.r),
            Expanded(
              child: _LibraryEntryCard(
                selected: _addonSelectedIndex == 1,
                icon: Symbols.file_open_rounded,
                title: AppLocale.libraryAddonImportFile.getString(context),
                subtitle: AppLocale.libraryAddonImportFileSubtitle.getString(
                  context,
                ),
                onTap: () => _tapAddonSelection(1),
              ),
            ),
          ],
        ),
        SizedBox(height: 14.r),
        Text(
          AppLocale.libraryAddonInstalledSources.getString(context),
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w700,
          ),
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
                      color: theme.colorScheme.onSurface.withValues(
                        alpha: 0.62,
                      ),
                    ),
                  ),
                )
              : ListView.separated(
                  cacheExtent: 1200.r,
                  padding: EdgeInsets.only(bottom: 26.r),
                  itemCount: _addons.length,
                  separatorBuilder: (_, _) => SizedBox(height: 8.r),
                  itemBuilder: (context, index) {
                    final addon = _addons[index];
                    return _AddonRow(
                      addon: addon,
                      selected: _addonSelectedIndex == index + 2,
                      onTap: () => _tapAddonSelection(index + 2),
                      onDelete: () => _confirmRemoveAddon(addon),
                    );
                  },
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
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.62,
                        ),
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

class _LibraryCatalogCard extends StatelessWidget {
  const _LibraryCatalogCard({
    required this.item,
    required this.selected,
    required this.onTap,
  });

  final LibraryCatalogItem item;
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
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(7.r),
                    child: SizedBox.expand(
                      child: item.coverUrl == null
                          ? ColoredBox(
                              color: theme.colorScheme.primary.withValues(
                                alpha: 0.10,
                              ),
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
    final baseUrl = addon.baseUrl;
    final host = baseUrl == null
        ? 'local'
        : (Uri.tryParse(baseUrl)?.host ?? baseUrl);
    final compatibility = switch (addon.sourceKind) {
      LibrarySourceKind.catalog => 'catalogue natif',
      LibrarySourceKind.localLibrary => 'local',
      LibrarySourceKind.metadataOnly => 'métadonnées iOS',
    };

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
            padding: EdgeInsets.symmetric(horizontal: 13.r, vertical: 10.r),
            child: Row(
              children: [
                Container(
                  width: 40.r,
                  height: 40.r,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(9.r),
                  ),
                  child: Icon(
                    Symbols.extension_rounded,
                    color: theme.colorScheme.primary,
                    size: 22.r,
                  ),
                ),
                SizedBox(width: 12.r),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        addon.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 2.r),
                      Text(
                        'v${addon.version} • $host • $compatibility',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(
                            alpha: 0.58,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: AppLocale.delete.getString(context),
                  onPressed: onDelete,
                  icon: Icon(
                    Symbols.delete_rounded,
                    color: theme.colorScheme.error,
                    size: 21.r,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
