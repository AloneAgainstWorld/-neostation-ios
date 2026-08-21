import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/services/fin_library_service.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/widgets/custom_notification.dart';

/// Two iOS settings cards for the Fin GameCube/Wii integration:
/// library folder/synchronization and Apple Shortcut launch configuration.
class FinIntegrationCards extends StatefulWidget {
  const FinIntegrationCards({super.key});

  @override
  State<FinIntegrationCards> createState() => _FinIntegrationCardsState();
}

class _FinIntegrationCardsState extends State<FinIntegrationCards> {
  static final _log = LoggerService.instance;

  bool _loading = true;
  bool _working = false;

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  Future<void> _initialize() async {
    try {
      await FinLibraryService.initialize();
    } catch (e) {
      _log.w('FinIntegrationCards: initialization failed: $e');
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _linkAndSync() async {
    if (_working) return;
    setState(() => _working = true);
    try {
      final result = await FinLibraryService.linkAndSync();
      if (!mounted || result == null) return;
      _showSyncResult(result);
      setState(() {});
    } on FormatException catch (e) {
      if (mounted) {
        AppNotification.showNotification(
          context,
          e.message,
          type: NotificationType.error,
        );
      }
    } catch (e) {
      _log.e('FinIntegrationCards: link/sync failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          'Fin library sync failed: $e',
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _sync() async {
    if (_working) return;
    setState(() => _working = true);
    try {
      final result = await FinLibraryService.syncLinkedLibrary();
      if (!mounted) return;
      _showSyncResult(result);
      setState(() {});
    } catch (e) {
      _log.e('FinIntegrationCards: sync failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          'Fin library sync failed: $e',
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  void _showSyncResult(FinLibrarySyncResult result) {
    final suffix = result.unresolvedGames > 0
        ? ' • ${result.unresolvedGames} unresolved'
        : '';
    AppNotification.showNotification(
      context,
      '${result.importedGames} Fin games synced '
      '(${result.gameCubeGames} GameCube, ${result.wiiGames} Wii)$suffix',
      type: result.importedGames > 0
          ? NotificationType.success
          : NotificationType.info,
    );
  }

  Future<void> _configureShortcut() async {
    final opened = await FinLibraryService.openShortcutSetup();
    if (!mounted) return;
    AppNotification.showNotification(
      context,
      opened
          ? 'Create the Shortcut as “${FinLibraryService.finShortcutName}”.'
          : AppLocale.shortcutSetupOpenError.getString(context),
      type: opened ? NotificationType.info : NotificationType.error,
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!Platform.isIOS) return const SizedBox.shrink();
    final theme = Theme.of(context);

    if (_loading) {
      return Padding(
        padding: EdgeInsets.symmetric(horizontal: 4.r, vertical: 8.r),
        child: const Center(child: CircularProgressIndicator()),
      );
    }

    final result = FinLibraryService.lastSync;
    final linked = FinLibraryService.isLinked;
    final hasSynced = FinLibraryService.hasSyncedLibrary;

    final libraryStatus = !linked
        ? 'Link Fin/Games to import GameCube and Wii games.'
        : !hasSynced
        ? 'Fin/Games is linked. Sync it to populate the GameCube and Wii libraries.'
        : '${result!.importedGames} games synced • '
              '${result.gameCubeGames} GameCube • ${result.wiiGames} Wii'
              '${result.unresolvedGames > 0 ? ' • ${result.unresolvedGames} unresolved' : ''}';

    return Column(
      children: [
        _buildCard(
          theme: theme,
          name: 'Fin — GameCube & Wii',
          icon: Symbols.sports_esports_rounded,
          statusText: libraryStatus,
          extra: linked && FinLibraryService.linkedGamesFolderPath != null
              ? _buildPathChip(
                  theme,
                  FinLibraryService.linkedGamesFolderPath!,
                )
              : null,
          actions: Row(
            children: [
              Expanded(
                child: SizedBox(
                  height: 48.r,
                  child: OutlinedButton.icon(
                    onPressed: _working ? null : _linkAndSync,
                    icon: _working
                        ? SizedBox(
                            width: 18.r,
                            height: 18.r,
                            child: const CircularProgressIndicator(
                              strokeWidth: 2,
                            ),
                          )
                        : Icon(
                            linked
                                ? Symbols.link_rounded
                                : Symbols.add_link_rounded,
                            size: 20.r,
                          ),
                    label: Text(
                      linked
                          ? AppLocale.iosEmuChangeFolder.getString(context)
                          : AppLocale.iosEmuLinkFolder.getString(context),
                      style: TextStyle(fontSize: 14.r),
                    ),
                  ),
                ),
              ),
              SizedBox(width: 10.r),
              Expanded(
                child: SizedBox(
                  height: 48.r,
                  child: FilledButton.icon(
                    onPressed: linked && !_working ? _sync : null,
                    icon: Icon(Symbols.sync_rounded, size: 20.r),
                    label: Text(
                      hasSynced
                          ? AppLocale.iosEmuResync.getString(context)
                          : AppLocale.iosEmuSync.getString(context),
                      style: TextStyle(fontSize: 14.r),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        _buildCard(
          theme: theme,
          name: 'Fin Shortcut',
          icon: Symbols.rocket_launch_rounded,
          statusText:
              'Shortcut: ${FinLibraryService.finShortcutName}\n'
              'NeoStation will pass the game path relative to Fin/Games. '
              'We will build and verify the Fin “Launch Game” action together.',
          actions: SizedBox(
            width: double.infinity,
            height: 48.r,
            child: OutlinedButton.icon(
              onPressed: _configureShortcut,
              icon: Icon(Symbols.add_rounded, size: 20.r),
              label: Text(
                AppLocale.configureLaunch.getString(context),
                style: TextStyle(fontSize: 14.r),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCard({
    required ThemeData theme,
    required String name,
    required IconData icon,
    required String statusText,
    required Widget actions,
    Widget? extra,
  }) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 4.r, vertical: 8.r),
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.all(16.r),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest.withValues(
            alpha: 0.4,
          ),
          borderRadius: BorderRadius.circular(14.r),
          border: Border.all(
            color: theme.colorScheme.outline.withValues(alpha: 0.2),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: theme.colorScheme.primary, size: 24.r),
                SizedBox(width: 10.r),
                Expanded(
                  child: Text(
                    name,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontSize: 16.r,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
            SizedBox(height: 8.r),
            Text(
              statusText,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontSize: 13.r,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (extra != null) ...[SizedBox(height: 8.r), extra],
            SizedBox(height: 16.r),
            actions,
          ],
        ),
      ),
    );
  }

  Widget _buildPathChip(ThemeData theme, String value) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: 8.r, vertical: 4.r),
      decoration: BoxDecoration(
        color: theme.colorScheme.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(6.r),
      ),
      child: Row(
        children: [
          Icon(
            Symbols.folder_rounded,
            size: 11.r,
            color: theme.colorScheme.primary.withValues(alpha: 0.5),
          ),
          SizedBox(width: 6.r),
          Expanded(
            child: Text(
              value,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 9.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                fontFamily: 'monospace',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
