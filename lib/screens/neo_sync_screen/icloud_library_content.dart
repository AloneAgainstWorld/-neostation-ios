import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/l10n/icloud_library_locale.dart';
import 'package:neostation/services/armsx2_library_service.dart';
import 'package:neostation/services/icloud_library_service.dart';
import 'package:neostation/services/melonx_library_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/utils/gamepad_nav.dart';
import 'package:neostation/widgets/custom_notification.dart';

class ICloudLibraryContent extends StatefulWidget {
  const ICloudLibraryContent({super.key, required this.onBack});

  final VoidCallback onBack;

  @override
  State<ICloudLibraryContent> createState() => _ICloudLibraryContentState();
}

class _ICloudLibraryContentState extends State<ICloudLibraryContent>
    with WidgetsBindingObserver {
  final ScrollController _scrollController = ScrollController();
  final List<GlobalKey> _rowKeys = [];
  late final GamepadNavigation _gamepadNav;

  String? _rootPath;
  List<ICloudLibraryItem> _items = const [];
  bool _loading = true;
  String? _importingPath;
  int _selectedIndex = 0;
  ICloudImportTarget? _pendingTarget;
  bool _leftForImporter = false;

  int get _actionCount => 2;
  int get _navigationCount => _actionCount + _items.length;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _gamepadNav = GamepadNavigation(
      onNavigateUp: () => _moveSelection(-1),
      onNavigateDown: () => _moveSelection(1),
      onSelectItem: _activateSelection,
      onBack: _goBack,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        'icloud_library',
        onActivate: _gamepadNav.activate,
        onDeactivate: _gamepadNav.deactivate,
      );
    });
    _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    GamepadNavigationManager.popLayer('icloud_library');
    _gamepadNav.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_pendingTarget == null) return;
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _leftForImporter = true;
      return;
    }
    if (state == AppLifecycleState.resumed && _leftForImporter) {
      final target = _pendingTarget;
      _pendingTarget = null;
      _leftForImporter = false;
      if (target != null) _resyncAfterImport(target);
    }
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    final root = await ICloudLibraryService.resolveLinkedFolder();
    List<ICloudLibraryItem> items = const [];
    if (root != null && root.isNotEmpty) {
      items = await ICloudLibraryService.scan(root);
    }
    if (!mounted) return;
    setState(() {
      _rootPath = root;
      _items = items;
      _loading = false;
      _selectedIndex = _selectedIndex.clamp(
        0,
        (_navigationCount - 1).clamp(0, 1 << 30),
      );
      _ensureRowKeys();
    });
  }

  Future<void> _chooseFolder() async {
    final selected = await ICloudLibraryService.chooseFolder();
    if (selected == null || selected.isEmpty || !mounted) return;
    setState(() {
      _rootPath = selected;
      _selectedIndex = 0;
    });
    await _load();
  }

  void _moveSelection(int delta) {
    final count = _navigationCount;
    if (count <= 0) return;
    final next = (_selectedIndex + delta).clamp(0, count - 1);
    if (next == _selectedIndex) return;
    setState(() => _selectedIndex = next);
    SfxService().playNavSound();
    _ensureSelectedVisible(next);
  }

  void _activateSelection() {
    if (_selectedIndex == 0) {
      _chooseFolder();
      return;
    }
    if (_selectedIndex == 1) {
      _load();
      return;
    }
    final itemIndex = _selectedIndex - _actionCount;
    if (itemIndex >= 0 && itemIndex < _items.length) {
      _importItem(_items[itemIndex]);
    }
  }

  void _ensureRowKeys() {
    while (_rowKeys.length < _navigationCount) {
      _rowKeys.add(GlobalKey());
    }
  }

  void _ensureSelectedVisible(int index) {
    if (index < 0 || index >= _rowKeys.length) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ctx = _rowKeys[index].currentContext;
      if (ctx == null) return;
      Scrollable.ensureVisible(
        ctx,
        duration: const Duration(milliseconds: 180),
        alignment: 0.5,
      );
    });
  }

  Future<void> _importItem(ICloudLibraryItem item) async {
    if (_importingPath != null) return;
    SfxService().playEnterSound();
    setState(() => _importingPath = item.sourcePath);

    try {
      final localPath = await ICloudLibraryService.materializeForImport(item);
      if (!mounted) return;
      final presented = await ExternalFolderAccess.openInMenu(localPath) ?? false;
      if (!mounted) return;
      if (!presented) {
        AppNotification.showNotification(
          context,
          ICloudLibraryLocale.get(context, 'importFailed'),
          type: NotificationType.error,
        );
        return;
      }

      _pendingTarget = item.target;
      final messageKey = switch (item.target) {
        ICloudImportTarget.melonx => 'sentMelonx',
        ICloudImportTarget.armsx2 => 'sentArmsx2',
        ICloudImportTarget.retroarch => 'sentRetroarch',
      };
      AppNotification.showNotification(
        context,
        ICloudLibraryLocale.get(context, messageKey),
        type: NotificationType.info,
      );
    } catch (e) {
      if (mounted) {
        AppNotification.showNotification(
          context,
          '${ICloudLibraryLocale.get(context, 'importFailed')}\n$e',
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) setState(() => _importingPath = null);
    }
  }

  Future<void> _resyncAfterImport(ICloudImportTarget target) async {
    // RetroArch intentionally stays manual: this preserves the existing iOS
    // workflow. MeloNX/ARMSX2 already expose reliable library callbacks.
    switch (target) {
      case ICloudImportTarget.melonx:
        await MelonxLibraryService.requestLibrarySync();
        break;
      case ICloudImportTarget.armsx2:
        await Armsx2LibraryService.requestLibrarySync();
        break;
      case ICloudImportTarget.retroarch:
        break;
    }
  }

  void _goBack() {
    SfxService().playBackSound();
    GamepadNavigationManager.popLayer('icloud_library');
    widget.onBack();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    _ensureRowKeys();

    return Padding(
      padding: EdgeInsets.fromLTRB(18.r, 48.r, 18.r, 14.r),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              IconButton(
                tooltip: ICloudLibraryLocale.get(context, 'back'),
                onPressed: _goBack,
                icon: const Icon(Symbols.arrow_back_rounded),
              ),
              SizedBox(width: 6.r),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      ICloudLibraryLocale.get(context, 'title'),
                      style: theme.textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        fontSize: 20.r,
                      ),
                    ),
                    Text(
                      ICloudLibraryLocale.get(context, 'subtitle'),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                        fontSize: 10.r,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: 12.r),
          Container(
            width: double.infinity,
            padding: EdgeInsets.all(10.r),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(10.r),
            ),
            child: Row(
              children: [
                Icon(Symbols.info_rounded, size: 16.r),
                SizedBox(width: 8.r),
                Expanded(
                  child: Text(
                    ICloudLibraryLocale.get(context, 'switchRule'),
                    style: TextStyle(fontSize: 9.r),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(height: 10.r),
          Row(
            children: [
              Expanded(
                child: _ActionTile(
                  key: _rowKeys[0],
                  selected: _selectedIndex == 0,
                  icon: Symbols.folder_open_rounded,
                  label: _rootPath == null
                      ? ICloudLibraryLocale.get(context, 'chooseFolder')
                      : ICloudLibraryLocale.get(context, 'changeFolder'),
                  subtitle: _rootPath ?? ICloudLibraryLocale.get(context, 'noFolder'),
                  onTap: _chooseFolder,
                ),
              ),
              SizedBox(width: 8.r),
              SizedBox(
                width: 132.r,
                child: _ActionTile(
                  key: _rowKeys[1],
                  selected: _selectedIndex == 1,
                  icon: Symbols.refresh_rounded,
                  label: ICloudLibraryLocale.get(context, 'refresh'),
                  subtitle: '${_items.length}',
                  onTap: _load,
                ),
              ),
            ],
          ),
          SizedBox(height: 10.r),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _rootPath == null
                ? Center(
                    child: Text(
                      ICloudLibraryLocale.get(context, 'noFolder'),
                      textAlign: TextAlign.center,
                    ),
                  )
                : _items.isEmpty
                ? Center(
                    child: Text(
                      ICloudLibraryLocale.get(context, 'empty'),
                      textAlign: TextAlign.center,
                    ),
                  )
                : ListView.separated(
                    controller: _scrollController,
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => SizedBox(height: 6.r),
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      final navIndex = index + _actionCount;
                      final importing = _importingPath == item.sourcePath;
                      return Container(
                        key: _rowKeys[navIndex],
                        decoration: BoxDecoration(
                          color: theme.cardColor.withValues(alpha: 0.28),
                          borderRadius: BorderRadius.circular(10.r),
                          border: Border.all(
                            color: _selectedIndex == navIndex
                                ? theme.colorScheme.primary
                                : Colors.transparent,
                            width: 2.r,
                          ),
                        ),
                        child: ListTile(
                          dense: true,
                          onTap: importing ? null : () => _importItem(item),
                          leading: Icon(
                            item.target == ICloudImportTarget.melonx
                                ? Symbols.videogame_asset_rounded
                                : item.target == ICloudImportTarget.armsx2
                                ? Symbols.stadia_controller_rounded
                                : Symbols.sports_esports_rounded,
                            color: theme.colorScheme.primary,
                          ),
                          title: Text(
                            item.filename,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 11.r, fontWeight: FontWeight.w600),
                          ),
                          subtitle: Text(
                            '${item.system.realName}  •  ${item.relativePath}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 8.5.r),
                          ),
                          trailing: importing
                              ? SizedBox(
                                  width: 18.r,
                                  height: 18.r,
                                  child: const CircularProgressIndicator(strokeWidth: 2),
                                )
                              : Container(
                                  padding: EdgeInsets.symmetric(horizontal: 8.r, vertical: 4.r),
                                  decoration: BoxDecoration(
                                    color: theme.colorScheme.primary.withValues(alpha: 0.12),
                                    borderRadius: BorderRadius.circular(20.r),
                                  ),
                                  child: Text(
                                    '→ ${item.target.label}',
                                    style: TextStyle(
                                      fontSize: 9.r,
                                      color: theme.colorScheme.primary,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    super.key,
    required this.selected,
    required this.icon,
    required this.label,
    required this.subtitle,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String label;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10.r),
      child: Container(
        padding: EdgeInsets.all(9.r),
        decoration: BoxDecoration(
          color: theme.cardColor.withValues(alpha: 0.3),
          borderRadius: BorderRadius.circular(10.r),
          border: Border.all(
            color: selected ? theme.colorScheme.primary : Colors.transparent,
            width: 2.r,
          ),
        ),
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
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 10.r, fontWeight: FontWeight.bold),
                  ),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 8.r,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
