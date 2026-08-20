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
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/neo_glass.dart';

/// Library hub and declarative add-on manager.
///
/// Add-ons are intentionally manifests rather than executable plugins. This
/// keeps the iOS build safe and lets NeoStation add catalog capabilities later
/// without loading third-party code into the process.
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

class LibraryScreenState extends State<LibraryScreen> {
  final LibraryAddonService _addonService = LibraryAddonService.instance;

  _LibraryView _view = _LibraryView.hub;
  int _hubSelectedIndex = 0;
  int _addonSelectedIndex = 0;
  bool _loadingAddons = true;
  List<LibraryAddon> _addons = const [];

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
  }

  bool _navigateHorizontal(int delta) {
    if (_view != _LibraryView.hub) return false;
    final next = (_hubSelectedIndex + delta).clamp(0, 1).toInt();
    if (next == _hubSelectedIndex) return false;
    setState(() => _hubSelectedIndex = next);
    return true;
  }

  bool _navigateVertical(int delta) {
    if (_view != _LibraryView.addons || _addonSelectionCount <= 0) return false;
    final next = (_addonSelectedIndex + delta)
        .clamp(0, _addonSelectionCount - 1)
        .toInt();
    if (next == _addonSelectedIndex) return false;
    setState(() => _addonSelectedIndex = next);
    return true;
  }

  void _activateSelection() {
    if (_view == _LibraryView.hub) {
      if (_hubSelectedIndex == 0) {
        setState(() {
          _view = _LibraryView.addons;
          _addonSelectedIndex = 0;
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
      });
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
    setState(() => _hubSelectedIndex = index);
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
                Text('v${addon.version} • ${Uri.parse(addon.baseUrl).host}'),
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
              'assets/images/icons/library-manga.webp',
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
                selected: _hubSelectedIndex == 0,
                icon: Symbols.extension_rounded,
                title: AppLocale.libraryAddons.getString(context),
                subtitle: AppLocale.libraryAddonsSubtitle.getString(context),
                onTap: () => _tapHubCard(0),
              ),
            ),
            SizedBox(width: 14.r),
            Expanded(
              child: _LibraryEntryCard(
                selected: _hubSelectedIndex == 1,
                icon: Symbols.folder_open_rounded,
                title: AppLocale.libraryLocal.getString(context),
                subtitle: AppLocale.libraryLocalSubtitle.getString(context),
                onTap: () => _tapHubCard(1),
              ),
            ),
          ],
        ),
        SizedBox(height: 12.r),
        Expanded(
          // Keep the empty-state copy high enough that short landscape displays
          // cannot crop it into the bottom Library border/footer area.
          child: Align(
            alignment: const Alignment(0, -0.72),
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
                    _addons.isEmpty
                        ? AppLocale.libraryEmptyTitle.getString(context)
                        : AppLocale.libraryAddonCount
                              .getString(context)
                              .replaceFirst(
                                '{count}',
                                _addons.length.toString(),
                              ),
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  SizedBox(height: 4.r),
                  ConstrainedBox(
                    constraints: BoxConstraints(maxWidth: 520.r),
                    child: Text(
                      AppLocale.libraryEmptySubtitle.getString(context),
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      overflow: TextOverflow.visible,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.62,
                        ),
                        height: 1.25,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
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
    final host = Uri.tryParse(addon.baseUrl)?.host ?? addon.baseUrl;

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
                        'v${addon.version} • $host',
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
