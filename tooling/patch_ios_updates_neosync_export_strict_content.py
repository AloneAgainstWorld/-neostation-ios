from pathlib import Path

APP = Path('lib/screens/app_screen.dart')
LIBRARY = Path('lib/screens/library_screen/library_screen.dart')
AIDOKU = Path('lib/services/library_aidoku_native_service.dart')
PROVIDER = Path('lib/providers/neo_sync_provider.dart')
NEOSYNC = Path('lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart')

app = APP.read_text(encoding='utf-8')
library = LIBRARY.read_text(encoding='utf-8')
aidoku = AIDOKU.read_text(encoding='utf-8')
provider = PROVIDER.read_text(encoding='utf-8')
neosync = NEOSYNC.read_text(encoding='utf-8')


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'anchor not found: {label}')
    return text.replace(old, new, 1)


def between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'start anchor not found: {label}')
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f'end anchor not found: {label}')
    return text[:a] + replacement + text[b:]

# ---------------------------------------------------------------------------
# iOS fork: desktop auto-update mechanisms must never execute.
# ---------------------------------------------------------------------------
app = once(
    app,
    '    if (configProvider.config.autoUpdateApp) {\n',
    "    // The iOS fork is sideloaded and owns its platform integrations. Desktop\n"
    "    // update manifests must never prompt, download, or replace iOS assets, even\n"
    "    // when a legacy config migrated from PC still has these booleans enabled.\n"
    "    if (!Platform.isIOS && configProvider.config.autoUpdateApp) {\n",
    'disable app updater on iOS',
)
app = once(
    app,
    '    if (configProvider.config.autoUpdateSystems) {\n',
    '    if (!Platform.isIOS && configProvider.config.autoUpdateSystems) {\n',
    'disable systems updater on iOS',
)

# ---------------------------------------------------------------------------
# Stronger adult/doujin filtering. Any source-level NSFW flag now excludes the
# entire source while Safe Content is enabled, and catalog metadata is scanned
# with a broader explicit-content vocabulary.
# ---------------------------------------------------------------------------
new_adult_filter = r'''  bool _isAdultOrDoujinshi(_NativeLibraryEntry entry) {
    bool explicitFlag(dynamic value) {
      if (value == true) return true;
      if (value is num) return value > 0;
      final raw = value?.toString().trim().toLowerCase() ?? '';
      if (raw.isEmpty) return false;
      if (raw == 'true' || raw == 'yes' || raw == '1' || raw == '2' || raw == '3') {
        return true;
      }
      return _strictAdultPattern.hasMatch(raw);
    }

    final provider = entry.source?.manifest['provider'];
    if (provider is Map) {
      // Repository/source metadata has priority. A source that declares any
      // non-zero NSFW level is excluded as a whole in strict safe mode.
      for (final key in const [
        'nsfw',
        'adult',
        'explicit',
        'isAdult',
        'contentWarning',
        'contentRating',
        'rating',
        'ageRating',
      ]) {
        if (explicitFlag(provider[key])) return true;
      }
    }

    final raw = entry.item.raw;
    for (final key in const [
      'explicitContent',
      'nsfw',
      'adult',
      'isAdult',
      'contentWarning',
      'contentRating',
      'rating',
      'ageRating',
      'genres',
      'genre',
      'categories',
      'tags',
      'labels',
    ]) {
      final value = raw[key];
      if (value is bool || value is num) {
        if (explicitFlag(value)) return true;
      } else if (value != null && _strictAdultPattern.hasMatch(value.toString())) {
        return true;
      }
    }

    String metadata = <String>[
      entry.item.title,
      entry.item.subtitle,
      entry.item.description,
      entry.item.coverUrl ?? '',
      entry.source?.name ?? '',
      entry.source?.description ?? '',
    ].join(' ').toLowerCase();
    try {
      metadata = '$metadata ${jsonEncode(raw).toLowerCase()}';
      if (provider is Map) {
        metadata = '$metadata ${jsonEncode(provider).toLowerCase()}';
      }
    } catch (_) {}

    return _strictAdultPattern.hasMatch(metadata);
  }

  static final RegExp _strictAdultPattern = RegExp(
    r'(^|[^a-z0-9])(hentai|doujinshi|doujin|porn|porno|pornographic|pornography|xxx|nsfw|r[ -]?18|18\+|18 plus|adult(?:s)?(?:[ -]?only|[ -]?content)?|mature(?:[ -]?content)?|explicit(?:[ -]?content)?|uncensored|smut|erotic|erotica|ecchi|sexual(?:[ -]?content)?|sex|hardcore|fetish|bdsm|ahegao|futanari|lolicon|shotacon|oppai|netorare|ntr|incest|rape|non[ -]?consensual|tentacle|milf|nudity|nude)([^a-z0-9]|$)',
    caseSensitive: false,
  );

'''
library = between(
    library,
    '  bool _isAdultOrDoujinshi(_NativeLibraryEntry entry) {\n',
    '  String _contentFilterLabel() {\n',
    new_adult_filter,
    'strict adult filter',
)

# Broaden metadata collected from Aidoku listing cards and fix 18+ regex.
aidoku = once(
    aidoku,
    "      '.genres a, .mgen a, .seriestugenre a, [class*=\"genre\"] a, '\n"
    "      '.post-content_item .summary-content a',\n",
    "      '.genres a, .mgen a, .seriestugenre a, [class*=\"genre\"] a, '\n"
    "      '.post-content_item .summary-content a, [class*=\"tag\"] a, '\n"
    "      'a[href*=\"/genre/\"], a[href*=\"/genres/\"], a[href*=\"/tag/\"], '\n"
    "      'a[href*=\"/tags/\"], .badge, .label, .tag, .genre',\n",
    'broaden aidoku category selectors',
)
aidoku = once(
    aidoku,
    "          '.adult, .nsfw, .manga-title-badges.adult, [class*=\"adult\"], '\n"
    "          '[class*=\"nsfw\"], [data-content-rating=\"adult\"]',\n",
    "          '.adult, .nsfw, .manga-title-badges.adult, [class*=\"adult\"], '\n"
    "          '[class*=\"nsfw\"], [class*=\"explicit\"], [class*=\"hentai\"], '\n"
    "          '[class*=\"doujin\"], [class*=\"mature\"], [data-content-rating=\"adult\"], '\n"
    "          '[data-nsfw=\"true\"], [data-adult=\"true\"]',\n",
    'broaden explicit selectors',
)
old_listing_metadata = """    final metadata = <String>[
      node.attributes['class'] ?? '',
      node.text,
      ...categories,
    ].join(' ');
    return RegExp(
      r'(^|[^a-z0-9])(hentai|doujinshi|doujin|porn|pornographic|xxx|nsfw|r-?18|18\\+|adult(?:s)?[ -]?only|explicit|uncensored|smut|erotic|erotica|ecchi|sexual[ -]?content|hardcore|fetish)([^a-z0-9]|$)',
      caseSensitive: false,
    ).hasMatch(metadata);
"""
new_listing_metadata = r'''    final image = node.querySelector('img');
    final link = node.querySelector('a[href]');
    final metadata = <String>[
      node.attributes['class'] ?? '',
      node.attributes['data-content-rating'] ?? '',
      node.attributes['data-nsfw'] ?? '',
      node.attributes['data-adult'] ?? '',
      link?.attributes['href'] ?? '',
      link?.attributes['title'] ?? '',
      image?.attributes['alt'] ?? '',
      image?.attributes['title'] ?? '',
      image?.attributes['src'] ?? '',
      node.text,
      ...categories,
    ].join(' ');
    return RegExp(
      r'(^|[^a-z0-9])(hentai|doujinshi|doujin|porn|porno|pornographic|pornography|xxx|nsfw|r[ -]?18|18\+|18 plus|adult(?:s)?(?:[ -]?only|[ -]?content)?|mature(?:[ -]?content)?|explicit(?:[ -]?content)?|uncensored|smut|erotic|erotica|ecchi|sexual(?:[ -]?content)?|sex|hardcore|fetish|bdsm|ahegao|futanari|lolicon|shotacon|oppai|netorare|ntr|incest|rape|non[ -]?consensual|tentacle|milf|nudity|nude)([^a-z0-9]|$)',
      caseSensitive: false,
    ).hasMatch(metadata);
'''
aidoku = once(aidoku, old_listing_metadata, new_listing_metadata, 'strict listing metadata')
# Fix/strengthen Phenix's explicit classifier too.
aidoku = aidoku.replace(
    r"r'(hentai|doujin|porn|nsfw|adult|explicit|smut|erotic|ecchi|18\\+|r-?18)'",
    r"r'(hentai|doujin|porn|porno|nsfw|adult|mature|explicit|smut|erotic|ecchi|18\+|r[ -]?18|uncensored|sexual|bdsm|futanari|lolicon|shotacon|netorare|ntr)'",
)

# ---------------------------------------------------------------------------
# NeoSync provider: expose safe, decompressed bytes for user-controlled export.
# ---------------------------------------------------------------------------
new_download_block = r'''  /// Downloads one cloud save for an explicit user export.
  ///
  /// NeoSync stores some payloads as `.neosync.gz`; exports must contain the
  /// original emulator save bytes so the archive is independently recoverable.
  Future<List<int>> downloadOnlineFileBytes(NeoSyncFile cloudFile) async {
    final result = await _neoSyncService.downloadFile(cloudFile.id);
    if (result['success'] != true || result['data'] == null) {
      throw Exception(result['message'] ?? 'Failed to download file');
    }
    final rawData = result['data'];
    if (rawData is! List) {
      throw const FormatException('NeoSync returned invalid file data');
    }
    final bytes = List<int>.from(rawData);
    return cloudFile.fileName.toLowerCase().endsWith('.neosync.gz')
        ? gzip.decode(bytes)
        : bytes;
  }

  /// Downloads a file from NeoSync storage and writes it to the local filesystem.
  ///
  /// Upon successful download, it synchronizes the local database sync state
  /// to match the cloud version.
  Future<void> _downloadCloudFile(NeoSyncFile cloudFile, File localFile) async {
    final payload = await downloadOnlineFileBytes(cloudFile);
    await localFile.writeAsBytes(payload);

    try {
      final stat = await localFile.stat();
      await SyncRepository.saveSyncState(
        localFile.path,
        stat.modified.millisecondsSinceEpoch,
        cloudFile.fileModifiedAtTimestamp ?? 0,
        stat.size,
        fileHash: cloudFile.checksum,
      );
    } catch (e) {
      _log.w('Could not save sync state for ${localFile.path}: $e');
    }
  }

'''
provider = between(
    provider,
    '  /// Downloads a file from NeoSync storage and writes it to the local filesystem.\n',
    '  /// Resolves the [SystemModel] associated with a specific game.\n',
    new_download_block,
    'public neosync download bytes',
)

# ---------------------------------------------------------------------------
# NeoSync iOS export UI.
# ---------------------------------------------------------------------------
neosync = once(
    neosync,
    "import 'package:flutter/material.dart';\n",
    "import 'dart:io';\n\n"
    "import 'package:archive/archive_io.dart';\n"
    "import 'package:path/path.dart' as p;\n"
    "import 'package:path_provider/path_provider.dart';\n"
    "import 'package:share_plus/share_plus.dart';\n"
    "import 'package:flutter/material.dart';\n",
    'neosync export imports',
)
neosync = once(
    neosync,
    '  bool _isNavigatingFast = false;\n',
    '  bool _isNavigatingFast = false;\n  bool _isExportingSaves = false;\n',
    'neosync export state',
)
neosync = once(
    neosync,
    '      onSelectItem: _selectSaveItem,\n',
    '      onSelectItem: _selectSaveItem,\n      onXButton: _exportSelectedSaveGroup,\n',
    'gamepad X export',
)

export_methods = r'''  Future<void> _exportSelectedSaveGroup() async {
    if (_isDialogMode || _isExportingSaves) return;
    final neoSyncProvider = Provider.of<NeoSyncProvider>(context, listen: false);
    final groups = _groupedOnlineSaves(neoSyncProvider);
    if (groups.isEmpty || _selectedSaveIndex < 0 || _selectedSaveIndex >= groups.length) {
      return;
    }
    await _exportSaveGroups(
      <_OnlineSaveGroup>[groups[_selectedSaveIndex]],
      label: groups[_selectedSaveIndex].displayName,
    );
  }

  Future<void> _exportAllCloudSaves() async {
    if (_isExportingSaves) return;
    final neoSyncProvider = Provider.of<NeoSyncProvider>(context, listen: false);
    final groups = _groupedOnlineSaves(neoSyncProvider);
    if (groups.isEmpty) return;
    await _exportSaveGroups(groups, label: 'NeoSync-All-Saves');
  }

  String _safeExportComponent(String value) {
    var result = value.trim().replaceAll(RegExp(r'[^A-Za-z0-9._-]+'), '_');
    result = result.replaceAll(RegExp(r'_+'), '_');
    result = result.replaceAll(RegExp(r'^[_\.]+|[_\.]+$'), '');
    return result.isEmpty ? 'save' : result;
  }

  List<String> _safeCloudPathSegments(String cloudPath) {
    var value = cloudPath.replaceAll('\\', '/').trim();
    if (value.toLowerCase().endsWith('.neosync.gz')) {
      value = value.substring(0, value.length - '.neosync.gz'.length);
    }
    final result = <String>[];
    for (final segment in value.split('/')) {
      final trimmed = segment.trim();
      if (trimmed.isEmpty || trimmed == '.' || trimmed == '..') continue;
      result.add(_safeExportComponent(trimmed));
    }
    return result.isEmpty ? <String>['save.bin'] : result;
  }

  File _uniqueExportFile(Directory root, List<String> segments) {
    final directorySegments = segments.length > 1
        ? segments.sublist(0, segments.length - 1)
        : const <String>[];
    final baseName = segments.last;
    final dot = baseName.lastIndexOf('.');
    final stem = dot > 0 ? baseName.substring(0, dot) : baseName;
    final extension = dot > 0 ? baseName.substring(dot) : '';
    var candidate = File(p.join(root.path, ...directorySegments, baseName));
    var suffix = 2;
    while (candidate.existsSync()) {
      candidate = File(
        p.join(root.path, ...directorySegments, '$stem-$suffix$extension'),
      );
      suffix++;
    }
    return candidate;
  }

  Rect _neoSyncShareOrigin() {
    final renderObject = context.findRenderObject();
    if (renderObject is RenderBox && renderObject.hasSize) {
      return renderObject.localToGlobal(Offset.zero) & renderObject.size;
    }
    return const Rect.fromLTWH(0, 0, 1, 1);
  }

  Future<void> _exportSaveGroups(
    List<_OnlineSaveGroup> groups, {
    required String label,
  }) async {
    if (_isExportingSaves || groups.isEmpty) return;
    final fr = Localizations.localeOf(context).languageCode == 'fr';
    final neoSyncProvider = Provider.of<NeoSyncProvider>(context, listen: false);
    Directory? exportRoot;
    File? zipFile;

    setState(() => _isExportingSaves = true);
    _savesGamepadNav.deactivate();
    custom.AppNotification.showNotification(
      context,
      fr ? 'Préparation de l’archive NeoSync…' : 'Preparing NeoSync archive…',
      type: custom.NotificationType.info,
    );

    try {
      final temp = await getTemporaryDirectory();
      final stamp = DateTime.now().microsecondsSinceEpoch;
      exportRoot = Directory(p.join(temp.path, 'neosync_export_$stamp'));
      await exportRoot.create(recursive: true);

      var exportedFiles = 0;
      for (final group in groups) {
        for (final cloudFile in group.files) {
          final bytes = await neoSyncProvider.downloadOnlineFileBytes(cloudFile);
          final target = _uniqueExportFile(
            exportRoot,
            _safeCloudPathSegments(cloudFile.fileName),
          );
          await target.parent.create(recursive: true);
          await target.writeAsBytes(bytes, flush: true);
          exportedFiles++;
        }
      }

      if (exportedFiles == 0) {
        throw StateError('No NeoSync files were exported');
      }

      final safeLabel = _safeExportComponent(label);
      zipFile = File(p.join(temp.path, 'NeoSync-$safeLabel-$stamp.zip'));
      final encoder = ZipFileEncoder();
      encoder.create(zipFile.path);
      await encoder.addDirectory(exportRoot, includeDirName: false);
      await encoder.close();

      if (await exportRoot.exists()) {
        await exportRoot.delete(recursive: true);
        exportRoot = null;
      }

      if (!mounted) return;
      custom.AppNotification.showNotification(
        context,
        fr
            ? 'Archive prête — choisissez « Enregistrer dans Fichiers » pour la conserver sur l’iPhone.'
            : 'Archive ready — choose “Save to Files” to keep it on this iPhone.',
        type: custom.NotificationType.success,
      );

      await SharePlus.instance.share(
        ShareParams(
          files: <XFile>[
            XFile(zipFile.path, mimeType: 'application/zip'),
          ],
          subject: 'NeoSync backup - $label',
          sharePositionOrigin: _neoSyncShareOrigin(),
        ),
      );
    } catch (e) {
      if (mounted) {
        custom.AppNotification.showNotification(
          context,
          fr
              ? 'Impossible d’exporter les sauvegardes NeoSync : $e'
              : 'Could not export NeoSync saves: $e',
          type: custom.NotificationType.error,
        );
      }
    } finally {
      try {
        if (exportRoot != null && await exportRoot.exists()) {
          await exportRoot.delete(recursive: true);
        }
      } catch (_) {}
      // The native share sheet has finished using the temp file when the await
      // above returns. Keeping no stale backups in the app cache avoids storage
      // growth across repeated exports.
      try {
        if (zipFile != null && await zipFile.exists()) {
          await zipFile.delete();
        }
      } catch (_) {}
      if (mounted) {
        setState(() => _isExportingSaves = false);
        _savesGamepadNav.activate();
      }
    }
  }

'''
neosync = once(
    neosync,
    '  void _selectSaveItem() async {\n',
    export_methods + '  void _selectSaveItem() async {\n',
    'neosync export methods',
)

# Header: add Export All before Refresh.
header_anchor = """                  Spacer(),
                  IconButton(
                    onPressed: (_isRefreshingOnlineFiles || _refreshCompleted)
"""
header_replacement = """                  Spacer(),
                  IconButton(
                    onPressed: (groups.isEmpty || _isExportingSaves)
                        ? null
                        : _exportAllCloudSaves,
                    icon: _isExportingSaves
                        ? SizedBox(
                            width: 12.r,
                            height: 12.r,
                            child: CircularProgressIndicator(strokeWidth: 2.r),
                          )
                        : Icon(Symbols.download_rounded, size: 16.r),
                    tooltip: Localizations.localeOf(context).languageCode == 'fr'
                        ? 'Exporter toutes les sauvegardes vers Fichiers'
                        : 'Export all saves to Files',
                  ),
                  IconButton(
                    onPressed: (_isRefreshingOnlineFiles || _refreshCompleted)
"""
neosync = once(neosync, header_anchor, header_replacement, 'export all header')

# List callback wiring.
neosync = once(
    neosync,
    """                        onDeleteRequest: (group, index) async {
                          // This logic can be simplified but essentially it's the same
                          // we can trigger the deletion logic here or move it to a method
                          setState(() => _selectedSaveIndex = index);
                          _selectSaveItem();
                        },
                        onSelectionChanged: (index) {
""",
    """                        onExportRequest: (group, index) async {
                          setState(() => _selectedSaveIndex = index);
                          await _exportSaveGroups(
                            <_OnlineSaveGroup>[group],
                            label: group.displayName,
                          );
                        },
                        onDeleteRequest: (group, index) async {
                          setState(() => _selectedSaveIndex = index);
                          _selectSaveItem();
                        },
                        onSelectionChanged: (index) {
""",
    'list export callback',
)

neosync = once(
    neosync,
    """  final Function(_OnlineSaveGroup, int) onDeleteRequest;
  final Function(int) onSelectionChanged;
""",
    """  final Function(_OnlineSaveGroup, int) onExportRequest;
  final Function(_OnlineSaveGroup, int) onDeleteRequest;
  final Function(int) onSelectionChanged;
""",
    'list export field',
)
neosync = once(
    neosync,
    """    required this.selectedIndex,
    required this.onDeleteRequest,
    required this.onSelectionChanged,
""",
    """    required this.selectedIndex,
    required this.onExportRequest,
    required this.onDeleteRequest,
    required this.onSelectionChanged,
""",
    'list export constructor',
)

old_delete_button = """          IconButton(
            onPressed: () => widget.onDeleteRequest(group, index),
            icon: Icon(
              Symbols.delete_rounded,
              color: isSelected
                  ? Theme.of(context).colorScheme.onSecondary
                  : Theme.of(context).colorScheme.error,
            ),
            tooltip: AppLocale.delete.getString(context),
          ),
"""
new_buttons = """          IconButton(
            constraints: BoxConstraints.tightFor(width: 30.r, height: 30.r),
            padding: EdgeInsets.zero,
            onPressed: () => widget.onExportRequest(group, index),
            icon: Icon(
              Symbols.download_rounded,
              size: 17.r,
              color: isSelected
                  ? Theme.of(context).colorScheme.onSecondary
                  : Theme.of(context).colorScheme.primary,
            ),
            tooltip: Localizations.localeOf(context).languageCode == 'fr'
                ? 'Exporter vers Fichiers'
                : 'Export to Files',
          ),
          IconButton(
            constraints: BoxConstraints.tightFor(width: 30.r, height: 30.r),
            padding: EdgeInsets.zero,
            onPressed: () => widget.onDeleteRequest(group, index),
            icon: Icon(
              Symbols.delete_rounded,
              size: 17.r,
              color: isSelected
                  ? Theme.of(context).colorScheme.onSecondary
                  : Theme.of(context).colorScheme.error,
            ),
            tooltip: AppLocale.delete.getString(context),
          ),
"""
neosync = once(neosync, old_delete_button, new_buttons, 'row export button')

APP.write_text(app, encoding='utf-8')
LIBRARY.write_text(library, encoding='utf-8')
AIDOKU.write_text(aidoku, encoding='utf-8')
PROVIDER.write_text(provider, encoding='utf-8')
NEOSYNC.write_text(neosync, encoding='utf-8')
