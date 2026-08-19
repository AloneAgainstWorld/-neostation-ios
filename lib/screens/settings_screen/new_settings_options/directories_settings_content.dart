import 'dart:async';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/rpcs3_library_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/armsx2_library_service.dart';
import 'package:neostation/services/config_service.dart';
import 'package:neostation/services/ios_shortcut_jit_launch_service.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/melonx_library_service.dart';
import 'package:neostation/services/permission_service.dart';
import 'package:neostation/services/retroarch_library_service.dart';
import 'package:neostation/services/rpcs3_library_service.dart';
import 'package:neostation/services/user_data_location_service.dart';
import 'package:neostation/widgets/confirm_action_dialog.dart';
import 'package:neostation/widgets/custom_notification.dart';
import 'package:neostation/widgets/move_user_data_dialog.dart';
import 'package:neostation/widgets/tv_directory_picker.dart';
import 'package:path/path.dart' as path;
import 'package:provider/provider.dart';

class DirectoriesSettingsContent extends StatefulWidget {
  const DirectoriesSettingsContent({super.key});

  @override
  State<DirectoriesSettingsContent> createState() =>
      _DirectoriesSettingsContentState();
}

class _DirectoriesSettingsContentState extends State<DirectoriesSettingsContent> {
  final _log = LoggerService.instance;

  String? _currentUserDataPath;
  bool _isLoadingPaths = true;
  bool _isMigrating = false;
  String? _linkingFolderKey;

  @override
  void initState() {
    super.initState();
    unawaited(_loadCurrentPaths());
  }

  Future<void> _loadCurrentPaths() async {
    setState(() => _isLoadingPaths = true);
    try {
      final path = await UserDataLocationService.getUserDataPath();
      if (!mounted) return;
      setState(() {
        _currentUserDataPath = path;
        _isLoadingPaths = false;
      });
    } catch (e) {
      _log.e('Failed to load current paths: $e');
      if (mounted) setState(() => _isLoadingPaths = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final configProvider = context.watch<SqliteConfigProvider>();
    final isIOS = Platform.isIOS;

    return SingleChildScrollView(
      padding: EdgeInsets.symmetric(horizontal: 24.r, vertical: 20.r),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            AppLocale.directories.getString(context),
            style: theme.textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          SizedBox(height: 8.r),
          Text(
            AppLocale.directoriesDescription.getString(context),
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          SizedBox(height: 24.r),
          if (isIOS) ...[
            _buildIOSDirectorySection(theme),
            SizedBox(height: 20.r),
          ],
          _buildRomFoldersSection(theme, configProvider),
          SizedBox(height: 20.r),
          _buildUserDataSection(theme),
          SizedBox(height: 24.r),
        ],
      ),
    );
  }

  Widget _buildIOSDirectorySection(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle(
          theme,
          AppLocale.iosEmulatorFolders.getString(context),
        ),
        SizedBox(height: 10.r),
        _buildIOSRetroArchSection(theme),
        SizedBox(height: 10.r),
        _buildIOSRpcs3Section(theme),
        SizedBox(height: 10.r),
        _buildIOSArmsx2Section(theme),
        SizedBox(height: 10.r),
        _buildIOSMeloNXSection(theme),
      ],
    );
  }

  Widget _buildSectionTitle(ThemeData theme, String title) {
    return Text(
      title,
      style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
    );
  }

  Widget _buildRomFoldersSection(
    ThemeData theme,
    SqliteConfigProvider configProvider,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: _buildSectionTitle(
                theme,
                AppLocale.romFolders.getString(context),
              ),
            ),
            IconButton(
              onPressed: configProvider.config.romFolders.length >= 5
                  ? null
                  : _addRomFolder,
              tooltip: AppLocale.addRomFolder.getString(context),
              icon: const Icon(Symbols.add_rounded),
            ),
          ],
        ),
        SizedBox(height: 10.r),
        if (configProvider.config.romFolders.isEmpty)
          _buildEmptyCard(
            theme,
            AppLocale.noRomFoldersConfigured.getString(context),
          )
        else
          ...configProvider.config.romFolders.map(
            (folder) => Padding(
              padding: EdgeInsets.only(bottom: 8.r),
              child: _buildPathCard(
                theme,
                folder,
                onRemove: () => _removeRomFolder(folder),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildUserDataSection(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle(
          theme,
          AppLocale.userDataLocation.getString(context),
        ),
        SizedBox(height: 10.r),
        Container(
          width: double.infinity,
          padding: EdgeInsets.all(16.r),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerLow,
            borderRadius: BorderRadius.circular(14.r),
            border: Border.all(
              color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Symbols.folder_data_rounded, size: 24.r),
                  SizedBox(width: 10.r),
                  Expanded(
                    child: Text(
                      _isLoadingPaths
                          ? AppLocale.loading.getString(context)
                          : (_currentUserDataPath ??
                                AppLocale.defaultLocation.getString(context)),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium,
                    ),
                  ),
                ],
              ),
              SizedBox(height: 12.r),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _isMigrating || _isLoadingPaths
                          ? null
                          : _selectUserDataLocation,
                      icon: const Icon(Symbols.folder_open_rounded),
                      label: Text(
                        AppLocale.changeLocation.getString(context),
                      ),
                    ),
                  ),
                  SizedBox(width: 10.r),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _isMigrating || _isLoadingPaths
                          ? null
                          : _resetUserDataLocation,
                      icon: const Icon(Symbols.restart_alt_rounded),
                      label: Text(
                        AppLocale.resetToDefault.getString(context),
                      ),
                    ),
                  ),
                ],
              ),
              if (_isMigrating) ...[
                SizedBox(height: 12.r),
                const LinearProgressIndicator(),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyCard(ThemeData theme, String text) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(16.r),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14.r),
      ),
      child: Text(
        text,
        style: theme.textTheme.bodyMedium?.copyWith(
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }

  Widget _buildPathCard(
    ThemeData theme,
    String pathValue, {
    required VoidCallback onRemove,
  }) {
    return Container(
      padding: EdgeInsets.all(14.r),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14.r),
      ),
      child: Row(
        children: [
          Icon(Symbols.folder_rounded, size: 22.r),
          SizedBox(width: 10.r),
          Expanded(
            child: Text(
              pathValue,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium,
            ),
          ),
          IconButton(
            onPressed: onRemove,
            icon: const Icon(Symbols.delete_outline_rounded),
            tooltip: AppLocale.remove.getString(context),
          ),
        ],
      ),
    );
  }

  Future<void> _linkExternalFolder({
    required String bookmarkKey,
    required String successMessage,
  }) async {
    if (_linkingFolderKey != null) return;

    setState(() => _linkingFolderKey = bookmarkKey);
    try {
      final picked = await ExternalFolderAccess.pickAndBookmarkFolder(
        key: bookmarkKey,
      );
      if (!mounted || picked == null) return;
      setState(() {});
      if (successMessage.isNotEmpty) {
        AppNotification.showNotification(
          context,
          successMessage,
          type: NotificationType.success,
        );
      }
    } catch (e) {
      _log.e('External folder link failed for $bookmarkKey: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          AppLocale.folderLinkError.getString(context),
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) setState(() => _linkingFolderKey = null);
    }
  }

  Future<void> _syncWithRetroArch() async {
    final opened = await RetroArchLibraryService.requestLibrarySync();
    if (!mounted) return;
    AppNotification.showNotification(
      context,
      opened
          ? AppLocale.iosRetroarchSyncRequested.getString(context)
          : AppLocale.iosRetroarchUnavailable.getString(context),
      type: opened ? NotificationType.info : NotificationType.error,
    );
  }

  Future<void> _syncWithArmsx2() async {
    final opened = await Armsx2LibraryService.requestLibrarySync();
    if (!mounted) return;
    AppNotification.showNotification(
      context,
      opened
          ? AppLocale.iosArmsx2SyncRequested.getString(context)
          : AppLocale.iosArmsx2Unavailable.getString(context),
      type: opened ? NotificationType.info : NotificationType.error,
    );
  }

  Future<void> _configureArmsx2Launch() async {
    final opened =
        await IosShortcutJitLaunchService.openArmsx2ShortcutInstaller();
    if (!mounted || opened) return;

    AppNotification.showNotification(
      context,
      AppLocale.shortcutSetupOpenError.getString(context),
      type: NotificationType.error,
    );
  }

  Future<void> _syncWithMeloNX() async {
    final opened = await MelonxLibraryService.requestLibrarySync();
    if (!mounted) return;
    AppNotification.showNotification(
      context,
      opened
          ? AppLocale.iosMelonxSyncRequested.getString(context)
          : AppLocale.iosMelonxUnavailable.getString(context),
      type: opened ? NotificationType.info : NotificationType.error,
    );
  }

  Future<void> _configureMeloNXLaunch() async {
    final opened =
        await IosShortcutJitLaunchService.openMeloNXShortcutInstaller();
    if (!mounted || opened) return;

    AppNotification.showNotification(
      context,
      AppLocale.shortcutSetupOpenError.getString(context),
      type: NotificationType.error,
    );
  }

  Future<void> _linkRpcs3DataFolder() async {
    if (_linkingFolderKey != null) return;

    setState(() => _linkingFolderKey = Rpcs3LibraryService.bookmarkKey);
    try {
      final result = await Rpcs3LibraryService.linkAndSync();
      if (result == null || !mounted) return;

      setState(() {});
      AppNotification.showNotification(
        context,
        result.discoveredGames == 0
            ? Rpcs3LibraryLocale.noGames(context)
            : Rpcs3LibraryLocale.syncComplete(context, result.discoveredGames),
        type: result.discoveredGames == 0
            ? NotificationType.info
            : NotificationType.success,
      );
    } on FormatException {
      if (mounted) {
        AppNotification.showNotification(
          context,
          Rpcs3LibraryLocale.invalidFolder(context),
          type: NotificationType.error,
        );
      }
    } catch (e) {
      _log.e('RPCS3 folder link/sync failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          Rpcs3LibraryLocale.syncFailed(context, e),
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _linkingFolderKey = null);
      }
    }
  }

  Future<void> _syncWithRpcs3() async {
    try {
      final result = await Rpcs3LibraryService.syncLinkedLibrary();
      if (!mounted) return;
      setState(() {});
      AppNotification.showNotification(
        context,
        result.discoveredGames == 0
            ? Rpcs3LibraryLocale.noGames(context)
            : Rpcs3LibraryLocale.syncComplete(context, result.discoveredGames),
        type: result.discoveredGames == 0
            ? NotificationType.info
            : NotificationType.success,
      );
    } on StateError catch (e) {
      if (mounted) {
        AppNotification.showNotification(
          context,
          Rpcs3LibraryLocale.syncFailed(context, e),
          type: NotificationType.error,
        );
      }
    } catch (e) {
      _log.e('RPCS3 sync failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          Rpcs3LibraryLocale.syncFailed(context, e),
          type: NotificationType.error,
        );
      }
    }
  }

  Widget _buildIOSRetroArchSection(ThemeData theme) {
    final isLinked = ExternalFolderAccess.hasBookmark(
      key: ExternalFolderAccess.defaultBookmarkKey,
    );
    final hasSynced = RetroArchLibraryService.hasSyncedLibrary;

    final statusText = !isLinked
        ? AppLocale.iosRetroarchStatusNeedsLink.getString(context)
        : hasSynced
        ? AppLocale.iosRetroarchStatusSynced.getString(context)
        : AppLocale.iosRetroarchStatusNeedsSync.getString(context);

    return _buildIOSEmulatorCard(
      theme: theme,
      name: 'RetroArch',
      icon: Symbols.sports_esports_rounded,
      statusText: statusText,
      isLinked: isLinked,
      bookmarkKey: ExternalFolderAccess.defaultBookmarkKey,
      successMessage: AppLocale.iosRetroarchLinkSuccess.getString(context),
      trailingAction: SizedBox(
        height: 48.r,
        child: FilledButton.icon(
          onPressed: !isLinked ? null : _syncWithRetroArch,
          icon: Icon(Symbols.bolt_rounded, size: 20.r),
          label: Text(
            hasSynced
                ? AppLocale.iosEmuResync.getString(context)
                : AppLocale.iosEmuSync.getString(context),
            style: TextStyle(fontSize: 14.r),
          ),
        ),
      ),
    );
  }

  Widget _buildIOSRpcs3Section(ThemeData theme) {
    final isLinked = Rpcs3LibraryService.isLinked;
    final hasSynced = Rpcs3LibraryService.hasSyncedLibrary;
    final count = Rpcs3LibraryService.syncedGameCount;

    final String statusText;
    if (!isLinked) {
      statusText = Rpcs3LibraryLocale.statusNeedsLink(context);
    } else if (!hasSynced) {
      statusText = Rpcs3LibraryLocale.statusNeedsSync(context);
    } else {
      statusText = Rpcs3LibraryLocale.statusSynced(context, count);
    }

    return _buildIOSEmulatorCard(
      theme: theme,
      name: 'RPCS3',
      icon: Symbols.sports_esports_rounded,
      statusText: statusText,
      isLinked: isLinked,
      bookmarkKey: Rpcs3LibraryService.bookmarkKey,
      successMessage: '',
      onLinkPressed: _linkRpcs3DataFolder,
      trailingAction: SizedBox(
        height: 48.r,
        child: FilledButton.icon(
          onPressed: !isLinked || _linkingFolderKey != null
              ? null
              : _syncWithRpcs3,
          icon: Icon(Symbols.bolt_rounded, size: 20.r),
          label: Text(
            hasSynced
                ? AppLocale.iosEmuResync.getString(context)
                : AppLocale.iosEmuSync.getString(context),
            style: TextStyle(fontSize: 14.r),
          ),
        ),
      ),
    );
  }

  /// ARMSX2 is sync-only, like MeloNX. Its exported library is authoritative
  /// for PS2 discovery and does not require a user-selected folder.
  Widget _buildIOSArmsx2Section(ThemeData theme) {
    final hasSynced = Armsx2LibraryService.hasSyncedLibrary;
    final statusText = hasSynced
        ? AppLocale.iosArmsx2StatusSynced.getString(context)
        : AppLocale.iosArmsx2StatusNeedsSync.getString(context);

    return _buildIOSEmulatorCard(
      theme: theme,
      name: 'ARMSX2',
      icon: Symbols.stadia_controller_rounded,
      statusText: statusText,
      isLinked: true,
      bookmarkKey: ExternalFolderAccess.defaultBookmarkKey,
      successMessage: '',
      showLinkButton: false,
      trailingAction: Row(
        children: [
          Expanded(
            child: SizedBox(
              height: 48.r,
              child: FilledButton.icon(
                onPressed: _syncWithArmsx2,
                icon: Icon(Symbols.bolt_rounded, size: 20.r),
                label: Text(
                  hasSynced
                      ? AppLocale.iosEmuResync.getString(context)
                      : AppLocale.iosEmuSync.getString(context),
                  style: TextStyle(fontSize: 14.r),
                ),
              ),
            ),
          ),
          SizedBox(width: 10.r),
          Expanded(
            child: SizedBox(
              height: 48.r,
              child: OutlinedButton.icon(
                onPressed: _configureArmsx2Launch,
                icon: Icon(Symbols.rocket_launch_rounded, size: 20.r),
                label: Text(
                  AppLocale.configureLaunch.getString(context),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 13.r),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildIOSMeloNXSection(ThemeData theme) {
    final hasSynced = MelonxLibraryService.hasSyncedLibrary;

    final statusText = hasSynced
        ? AppLocale.iosMelonxStatusSynced.getString(context)
        : AppLocale.iosMelonxStatusNeedsSync.getString(context);

    return _buildIOSEmulatorCard(
      theme: theme,
      name: 'MeloNX',
      icon: Symbols.videogame_asset_rounded,
      statusText: statusText,
      isLinked: true,
      bookmarkKey: ExternalFolderAccess.defaultBookmarkKey,
      successMessage: '',
      showLinkButton: false,
      trailingAction: Row(
        children: [
          Expanded(
            child: SizedBox(
              height: 48.r,
              child: FilledButton.icon(
                onPressed: _syncWithMeloNX,
                icon: Icon(Symbols.bolt_rounded, size: 20.r),
                label: Text(
                  hasSynced
                      ? AppLocale.iosEmuResync.getString(context)
                      : AppLocale.iosEmuSync.getString(context),
                  style: TextStyle(fontSize: 14.r),
                ),
              ),
            ),
          ),
          SizedBox(width: 10.r),
          Expanded(
            child: SizedBox(
              height: 48.r,
              child: OutlinedButton.icon(
                onPressed:
                    IosShortcutJitLaunchService.hasMeloNXShortcutInstaller
                    ? _configureMeloNXLaunch
                    : null,
                icon: Icon(Symbols.rocket_launch_rounded, size: 20.r),
                label: Text(
                  AppLocale.configureLaunch.getString(context),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 13.r),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildIOSEmulatorCard({
    required ThemeData theme,
    required String name,
    required IconData icon,
    required String statusText,
    required bool isLinked,
    required String bookmarkKey,
    required String successMessage,
    bool showLinkButton = true,
    Future<void> Function()? onLinkPressed,
    Widget? trailingAction,
  }) {
    final isLinkingThis = _linkingFolderKey == bookmarkKey;
    final isAnyLinkInFlight = _linkingFolderKey != null;

    final linkButton = SizedBox(
      height: 48.r,
      child: OutlinedButton.icon(
        onPressed: isAnyLinkInFlight
            ? null
            : () async {
                if (onLinkPressed != null) {
                  await onLinkPressed();
                } else {
                  await _linkExternalFolder(
                    bookmarkKey: bookmarkKey,
                    successMessage: successMessage,
                  );
                }
              },
        icon: isLinkingThis
            ? SizedBox(
                width: 18.r,
                height: 18.r,
                child: const CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(Symbols.folder_open_rounded, size: 20.r),
        label: Text(
          AppLocale.linkFolder.getString(context),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(fontSize: 13.r),
        ),
      ),
    );

    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(16.r),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14.r),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 24.r),
              SizedBox(width: 10.r),
              Expanded(
                child: Text(
                  name,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: 8.r),
          Text(
            statusText,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          SizedBox(height: 12.r),
          if (showLinkButton && trailingAction != null)
            Row(
              children: [
                Expanded(child: linkButton),
                SizedBox(width: 10.r),
                Expanded(child: trailingAction),
              ],
            )
          else if (showLinkButton)
            linkButton
          else if (trailingAction != null)
            trailingAction,
        ],
      ),
    );
  }

  Future<void> _addRomFolder() async {
    final configProvider = Provider.of<SqliteConfigProvider>(
      context,
      listen: false,
    );

    if (configProvider.config.romFolders.length >= 5) {
      if (mounted) {
        AppNotification.showNotification(
          context,
          AppLocale.maxRomFoldersReached.getString(context),
          type: NotificationType.info,
        );
      }
      return;
    }

    try {
      String? selected;

      if (Platform.isAndroid) {
        final isTV = await PermissionService.isTelevision();
        if (isTV) {
          if (mounted) selected = await TvDirectoryPicker.show(context);
        } else {
          try {
            final uri = await PermissionService.requestFolderAccess();
            selected = uri?.toString();
          } on PlatformException catch (e) {
            if (e.code == 'PICKER_FAILED' && mounted) {
              selected = await TvDirectoryPicker.show(context);
            }
          }
        }
      } else if (Platform.isIOS) {
        selected = await ConfigService.getDefaultIOSRomsFolder();
        if (configProvider.config.romFolders.contains(selected)) {
          if (mounted) {
            AppNotification.showNotification(
              context,
              'Already using the internal roms folder. Drop ROMs into it '
              'via the Files app under "On My iPhone > NeoStation > roms".',
              type: NotificationType.info,
            );
          }
          return;
        }
      } else {
        selected = await FilePicker.getDirectoryPath(
          dialogTitle: AppLocale.selectRomsFolder.getString(context),
        );
      }

      if (selected != null) {
        await configProvider.addRomFolder(selected);
        await _loadCurrentPaths();
      }
    } catch (e) {
      _log.e('ROM folder selection failed: $e');
    }
  }

  Future<void> _removeRomFolder(String path) async {
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: AppLocale.removeRomFolder.getString(context),
      body: AppLocale.removeRomFolderConfirmBody.getString(context),
      confirmLabel: AppLocale.removeRomFolder.getString(context),
      icon: Symbols.folder_delete_rounded,
    );
    if (!confirmed || !mounted) return;

    final configProvider = Provider.of<SqliteConfigProvider>(
      context,
      listen: false,
    );
    try {
      await configProvider.removeRomFolder(path);
      await _loadCurrentPaths();
      if (mounted) {
        AppNotification.showNotification(
          context,
          AppLocale.romFolderRemoved.getString(context),
          type: NotificationType.info,
        );
      }
    } catch (e) {
      _log.e('Failed to remove ROM folder: $e');
    }
  }

  Future<void> _selectUserDataLocation() async {
    try {
      String? selected;

      if (Platform.isAndroid) {
        final isTV = await PermissionService.isTelevision();
        if (!mounted) return;
        if (isTV) {
          selected = await TvDirectoryPicker.show(context);
        } else {
          try {
            final uri = await PermissionService.requestFolderAccess();
            if (uri != null) {
              final uriStr = uri.toString();
              final hasFiles = await PermissionService.hasAllFilesAccess();
              selected =
                  await UserDataLocationService.resolveAndroidUserDataPath(
                    uriStr,
                    hasAllFilesAccess: hasFiles,
                  ) ??
                  UserDataLocationService.safUriToRealPath(uriStr);
            }
          } on PlatformException catch (e) {
            if (e.code == 'PICKER_FAILED' && mounted) {
              selected = await TvDirectoryPicker.show(context);
            }
          }
        }
      } else {
        selected = await FilePicker.getDirectoryPath(
          dialogTitle: AppLocale.selectUserDataFolder.getString(context),
          initialDirectory: _currentUserDataPath,
        );
      }

      if (selected == null || !mounted) return;
      if (selected.endsWith(Platform.pathSeparator)) {
        selected = selected.substring(0, selected.length - 1);
      }

      final current = _currentUserDataPath;
      if (current == null || selected == current) return;

      final entryCount = await UserDataLocationService.countDirectoryEntries(
        selected,
      );
      if (!mounted) return;
      final proceed = await MoveUserDataDialog.show(
        context,
        fromPath: current,
        toPath: selected,
        destItemCount: entryCount,
      );
      if (!proceed || !mounted) return;

      await _migrateUserData(sourcePath: current, destPath: selected);
    } catch (e) {
      _log.e('User data location selection failed: $e');
    }
  }

  Future<void> _resetUserDataLocation() async {
    if (_currentUserDataPath == null) return;

    try {
      final defaultPath = await UserDataLocationService.getDefaultUserDataPath();
      if (!mounted || defaultPath == _currentUserDataPath) return;

      final proceed = await MoveUserDataDialog.show(
        context,
        fromPath: _currentUserDataPath!,
        toPath: defaultPath,
        destItemCount: await UserDataLocationService.countDirectoryEntries(
          defaultPath,
        ),
      );
      if (!proceed || !mounted) return;

      await _migrateUserData(
        sourcePath: _currentUserDataPath!,
        destPath: defaultPath,
      );
    } catch (e) {
      _log.e('Failed to reset user data location: $e');
    }
  }

  Future<void> _migrateUserData({
    required String sourcePath,
    required String destPath,
  }) async {
    setState(() => _isMigrating = true);
    try {
      await UserDataLocationService.migrateUserData(
        sourcePath: sourcePath,
        destinationPath: destPath,
      );
      if (!mounted) return;
      await _loadCurrentPaths();
      AppNotification.showNotification(
        context,
        AppLocale.userDataMoveComplete.getString(context),
        type: NotificationType.success,
      );
    } catch (e) {
      _log.e('User data migration failed: $e');
      if (mounted) {
        AppNotification.showNotification(
          context,
          AppLocale.userDataMoveFailed.getString(context),
          type: NotificationType.error,
        );
      }
    } finally {
      if (mounted) setState(() => _isMigrating = false);
    }
  }
}
