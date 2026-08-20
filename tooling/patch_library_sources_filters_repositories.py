from pathlib import Path

service_path = Path('lib/services/library_addon_service.dart')
screen_path = Path('lib/screens/library_screen/library_screen.dart')
test_path = Path('test/library_addon_service_test.dart')

service = service_path.read_text()
screen = screen_path.read_text()
tests = test_path.read_text()

# ---------------------------------------------------------------------------
# library_addon_service.dart
# ---------------------------------------------------------------------------
service = service.replace(
    "enum LibraryAddonDocumentFormat { neoStationManifest, tachiyomiRepository }",
    "enum LibraryAddonDocumentFormat {\n  neoStationManifest,\n  tachiyomiRepository,\n  aidokuRepository,\n}",
)

service = service.replace(
    "  static const String tachiyomiProviderType = 'tachiyomi-extension-repository';\n  static const String gallicaProviderType = 'gallica-opds';",
    "  static const String tachiyomiProviderType = 'tachiyomi-extension-repository';\n  static const String aidokuProviderType = 'aidoku-source-repository';\n  static const String gallicaProviderType = 'gallica-opds';",
)

anchor = """  bool get isTachiyomiRepositorySource {
    final provider = manifest['provider'];
    return provider is Map && provider['type'] == tachiyomiProviderType;
  }

"""
replacement = anchor + """  bool get isAidokuRepositorySource {
    final provider = manifest['provider'];
    return provider is Map && provider['type'] == aidokuProviderType;
  }

  bool get isRepositorySource =>
      isTachiyomiRepositorySource || isAidokuRepositorySource;

  String get repositoryOrigin {
    final provider = manifest['provider'];
    if (provider is Map) {
      final value = provider['repositoryOrigin']?.toString().trim();
      if (value != null && value.isNotEmpty) return value;
    }
    return origin;
  }

  String? get sourceDownloadUrl {
    final provider = manifest['provider'];
    if (provider is Map) {
      final value = provider['downloadUrl']?.toString().trim();
      if (value != null && value.isNotEmpty) return value;
    }
    return null;
  }

"""
assert anchor in service
service = service.replace(anchor, replacement, 1)

start = service.index("  Future<LibraryAddonBatchInstallResult> installDocumentFromUrl(\n")
end = service.index("  Future<http.Response> _downloadRepository(Uri uri) async {", start)
new_install = r'''  Future<LibraryAddonBatchInstallResult> installDocumentFromUrl(
    String documentUrl,
  ) async {
    final uri = Uri.tryParse(documentUrl.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const LibraryAddonException('Repository URL must use HTTPS.');
    }

    LibraryAddonException? lastError;
    for (final candidate in _repositoryCandidates(uri)) {
      try {
        var effectiveUri = candidate;
        var response = await _downloadRepository(candidate);

        if (_looksLikeKeiyoushiDeprecationStub(response.bodyBytes) &&
            candidate.path.endsWith('/index.min.json')) {
          final fullPath = candidate.path.substring(
                0,
                candidate.path.length - 'index.min.json'.length,
              ) +
              'index.json';
          final fullUri = candidate.replace(path: fullPath);
          try {
            final fullResponse = await _downloadRepository(fullUri);
            if (!_looksLikeKeiyoushiDeprecationStub(fullResponse.bodyBytes)) {
              effectiveUri = fullUri;
              response = fullResponse;
            }
          } on LibraryAddonException {
            // Keep the minified response if the full index is unavailable.
          }
        }

        return await installDocumentFromJson(
          utf8.decode(response.bodyBytes),
          origin: effectiveUri.toString(),
        );
      } on LibraryAddonException catch (error) {
        lastError = error;
      } on FormatException catch (error) {
        lastError = LibraryAddonException('Invalid repository document: $error');
      }
    }

    throw lastError ??
        const LibraryAddonException('Unable to resolve this repository URL.');
  }

  static List<Uri> _repositoryCandidates(Uri original) {
    final values = <String>[];

    void add(String value) {
      final parsed = Uri.tryParse(value);
      if (parsed == null || parsed.scheme != 'https' || parsed.host.isEmpty) {
        return;
      }
      if (!values.contains(parsed.toString())) values.add(parsed.toString());
    }

    add(original.toString());
    final host = original.host.toLowerCase();
    final lowerPath = original.path.toLowerCase();

    // Old repositories that moved or were archived. Keep accepting the URLs
    // users already have in their source lists and transparently resolve them.
    if ((host == 'raw.githubusercontent.com' || host == 'github.com') &&
        lowerPath.contains('/almightyhak/aniyomi-anime-repo')) {
      add(
        'https://raw.githubusercontent.com/aniyomi-addons/anime-extensions-repo/repo/index.min.json',
      );
      add(
        'https://raw.githubusercontent.com/aniyomi-addons/anime-extensions-repo/repo/index.json',
      );
    }
    if ((host == 'raw.githubusercontent.com' || host == 'github.com') &&
        lowerPath.contains('/komikku-app/extensions')) {
      add(
        'https://raw.githubusercontent.com/cuong-tran/manga-repo/repo/index.json',
      );
    }
    if ((host == 'raw.githubusercontent.com' || host == 'github.com') &&
        lowerPath.contains('/thepbone/tachiyomi-extensions-revived')) {
      add(
        'https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.min.json',
      );
      add(
        'https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.json',
      );
    }
    if ((host == 'raw.githubusercontent.com' || host == 'github.com') &&
        lowerPath.contains('/moomooo95/aidoku-french-sources')) {
      add(
        'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/gh-pages/index.min.json',
      );
      add(
        'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/gh-pages/index.json',
      );
    }

    // Accept a plain GitHub repository URL. Common source-repository branches
    // are tried in order, so users do not need to know the raw index URL.
    if (host == 'github.com' && original.pathSegments.length >= 2) {
      final owner = original.pathSegments[0];
      final repo = original.pathSegments[1].replaceFirst(RegExp(r'\.git$'), '');
      for (final branch in const ['repo', 'gh-pages', 'main', 'master']) {
        add(
          'https://raw.githubusercontent.com/$owner/$repo/$branch/index.min.json',
        );
        add(
          'https://raw.githubusercontent.com/$owner/$repo/$branch/index.json',
        );
      }
    }

    return values.map(Uri.parse).toList(growable: false);
  }

'''
service = service[:start] + new_install + service[end:]

map_anchor = """    if (decoded is Map) {
      final object = Map<String, dynamic>.from(decoded);
      final modernEntries = _extractModernKeiyoushiEntries(object);
"""
map_replacement = """    if (decoded is Map) {
      final object = Map<String, dynamic>.from(decoded);
      final aidokuEntries = _extractAidokuEntries(object);
      if (aidokuEntries != null) {
        final parsed = _parseAidokuRepository(aidokuEntries, origin: origin);
        return _upsertMany(
          parsed,
          format: LibraryAddonDocumentFormat.aidokuRepository,
        );
      }

      final modernEntries = _extractModernKeiyoushiEntries(object);
"""
assert map_anchor in service
service = service.replace(map_anchor, map_replacement, 1)

list_anchor = """    if (decoded is List) {
      final parsed = _parseTachiyomiRepository(decoded, origin: origin);
      return _upsertMany(
        parsed,
        format: LibraryAddonDocumentFormat.tachiyomiRepository,
      );
    }
"""
list_replacement = """    if (decoded is List) {
      if (_looksLikeAidokuEntries(decoded)) {
        final parsed = _parseAidokuRepository(decoded, origin: origin);
        return _upsertMany(
          parsed,
          format: LibraryAddonDocumentFormat.aidokuRepository,
        );
      }
      final parsed = _parseTachiyomiRepository(decoded, origin: origin);
      return _upsertMany(
        parsed,
        format: LibraryAddonDocumentFormat.tachiyomiRepository,
      );
    }
"""
assert list_anchor in service
service = service.replace(list_anchor, list_replacement, 1)

extract_anchor = """  static List<dynamic>? _extractModernKeiyoushiEntries(
"""
aidoku_methods = r'''  static List<dynamic>? _extractAidokuEntries(
    Map<String, dynamic> document,
  ) {
    final sources = document['sources'];
    if (sources is List && _looksLikeAidokuEntries(sources)) return sources;
    return null;
  }

  static bool _looksLikeAidokuEntries(List<dynamic> entries) {
    var matches = 0;
    for (final raw in entries) {
      if (raw is! Map) continue;
      final entry = Map<String, dynamic>.from(raw);
      final id = entry['id']?.toString().trim() ?? '';
      final name = entry['name']?.toString().trim() ?? '';
      final hasPackage =
          (entry['file']?.toString().trim().isNotEmpty ?? false) ||
          (entry['downloadURL']?.toString().trim().isNotEmpty ?? false) ||
          (entry['downloadUrl']?.toString().trim().isNotEmpty ?? false);
      if (id.isNotEmpty &&
          name.isNotEmpty &&
          hasPackage &&
          !entry.containsKey('pkg')) {
        matches++;
      }
    }
    return matches > 0;
  }

  List<LibraryAddon> _parseAidokuRepository(
    List<dynamic> entries, {
    required String origin,
  }) {
    final originUri = Uri.tryParse(origin);
    if (originUri == null ||
        originUri.scheme != 'https' ||
        originUri.host.isEmpty) {
      throw const LibraryAddonException('Aidoku repository origin must use HTTPS.');
    }

    final result = <LibraryAddon>[];
    final seenIds = <String>{};

    String? resolveOptional(dynamic raw, {String? legacyFolder}) {
      final value = raw?.toString().trim() ?? '';
      if (value.isEmpty) return null;
      final direct = Uri.tryParse(value);
      if (direct != null && direct.hasScheme) {
        if (direct.scheme != 'https' || direct.host.isEmpty) return null;
        return direct.toString();
      }
      final relative = legacyFolder == null ? value : '$legacyFolder/$value';
      final resolved = originUri.resolve(relative);
      if (resolved.scheme != 'https' || resolved.host.isEmpty) return null;
      return resolved.toString();
    }

    for (final rawEntry in entries) {
      if (rawEntry is! Map) continue;
      if (result.length >= _maxRepositorySources) {
        throw const LibraryAddonException(
          'Repository contains more than 10000 sources.',
        );
      }

      final entry = Map<String, dynamic>.from(rawEntry);
      final sourceId = entry['id']?.toString().trim() ?? '';
      final sourceName = entry['name']?.toString().trim() ?? '';
      if (sourceId.isEmpty || sourceName.isEmpty) continue;

      final version = entry['version']?.toString().trim().isNotEmpty == true
          ? entry['version'].toString().trim()
          : '0';
      final sourceLang =
          entry['lang']?.toString().trim().isNotEmpty == true
              ? entry['lang'].toString().trim()
              : ((entry['languages'] is List &&
                      (entry['languages'] as List).isNotEmpty)
                  ? (entry['languages'] as List).first.toString()
                  : 'all');
      final downloadUrl =
          resolveOptional(entry['downloadURL'] ?? entry['downloadUrl']) ??
          resolveOptional(entry['file'], legacyFolder: 'sources');
      if (downloadUrl == null) continue;
      final iconUrl =
          resolveOptional(entry['iconURL'] ?? entry['iconUrl']) ??
          resolveOptional(entry['icon'], legacyFolder: 'icons');
      final explicitBase = entry['baseURL'] ?? entry['baseUrl'];
      final parsedBase = explicitBase == null
          ? null
          : Uri.tryParse(explicitBase.toString().trim());
      final baseUrl = parsedBase != null &&
              parsedBase.scheme == 'https' &&
              parsedBase.host.isNotEmpty
          ? parsedBase.toString()
          : originUri.resolve('.').toString();

      final id = _aidokuAddonId(sourceId);
      if (!seenIds.add(id)) continue;
      final manifest = <String, dynamic>{
        'schema': LibraryAddon.schemaV1,
        'id': id,
        'name': sourceName,
        'version': version,
        'baseUrl': baseUrl,
        if (iconUrl != null) 'icon': iconUrl,
        'description': 'Aidoku repository source • $sourceLang',
        'iosCompatibility': 'metadata-only',
        'provider': <String, dynamic>{
          'type': LibraryAddon.aidokuProviderType,
          'sourceId': sourceId,
          'sourceLang': sourceLang,
          'downloadUrl': downloadUrl,
          'file': entry['file'],
          'nsfw': entry['nsfw'],
          'contentRating': entry['contentRating'],
          'repositoryOrigin': origin,
        },
      };
      result.add(LibraryAddon.fromManifest(manifest, origin: origin));
    }

    if (result.isEmpty) {
      throw const LibraryAddonException(
        'No installable Aidoku sources were found in this repository.',
      );
    }
    return result;
  }

  static String _aidokuAddonId(String sourceId) {
    var safe = sourceId
        .replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_')
        .replaceAll(RegExp(r'_+'), '_');
    if (safe.length > 92) safe = safe.substring(0, 92);
    if (safe.length < 2) safe = 'source';
    return 'aidoku.$safe';
  }

'''
assert extract_anchor in service
service = service.replace(extract_anchor, aidoku_methods + extract_anchor, 1)

remove_anchor = """  Future<bool> remove(String id) async {
"""
remove_methods = r'''  Future<int> removeRepository(String repositoryOrigin) async {
    await load();
    final normalized = repositoryOrigin.trim();
    if (normalized.isEmpty) return 0;
    final before = _addons.length;
    _addons.removeWhere(
      (addon) =>
          !addon.isBuiltIn &&
          addon.isRepositorySource &&
          addon.repositoryOrigin == normalized,
    );
    final removed = before - _addons.length;
    if (removed > 0) await _persist();
    return removed;
  }

'''
assert remove_anchor in service
service = service.replace(remove_anchor, remove_methods + remove_anchor, 1)

# ---------------------------------------------------------------------------
# library_screen.dart: source filter + repository removal + Aidoku labels
# ---------------------------------------------------------------------------
screen = screen.replace(
    "  String _languageFilter = 'all';\n  bool _sortAscending = true;",
    "  String _languageFilter = 'all';\n  String _sourceFilter = 'all';\n  bool _sortAscending = true;",
)

visible_anchor = """    final items = _libraryItems.where((entry) {
      if (_languageFilter == 'all') return true;
      return _itemLanguageCodes(entry).contains(_languageFilter);
    }).toList();
"""
visible_replacement = """    final items = _libraryItems.where((entry) {
      if (_languageFilter != 'all' &&
          !_itemLanguageCodes(entry).contains(_languageFilter)) {
        return false;
      }
      if (_sourceFilter != 'all' && entry.providerId != _sourceFilter) {
        return false;
      }
      return true;
    }).toList();
"""
assert visible_anchor in screen
screen = screen.replace(visible_anchor, visible_replacement, 1)

lang_options_end = """    return <String>['all', ...sorted];
  }

"""
source_options = r'''    return <String>['all', ...sorted];
  }

  Map<String, String> get _sourceOptions {
    final options = <String, String>{'all': 'all'};
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
    return <String, String>{'all': 'all', for (final entry in pairs) entry.key: entry.value};
  }

  String _sourceLabel(String id) {
    if (id == 'all') {
      return Localizations.localeOf(context).languageCode == 'fr'
          ? 'Toutes les sources'
          : 'All sources';
    }
    return _sourceOptions[id] ?? id;
  }

'''
assert lang_options_end in screen
screen = screen.replace(lang_options_end, source_options, 1)

screen = screen.replace(
    "final next = (_filterSelectedIndex + delta).clamp(0, 2).toInt();",
    "final next = (_filterSelectedIndex + delta).clamp(0, 3).toInt();",
    1,
)

activate_anchor = """        if (_filterSelectedIndex == 0) {
          _openLanguageMenu();
        } else if (_filterSelectedIndex == 1) {
          _openSortMenu();
        } else {
          _openIndexMenu();
        }
"""
activate_replacement = """        if (_filterSelectedIndex == 0) {
          _openLanguageMenu();
        } else if (_filterSelectedIndex == 1) {
          _openSortMenu();
        } else if (_filterSelectedIndex == 2) {
          _openIndexMenu();
        } else {
          _openSourceMenu();
        }
"""
assert activate_anchor in screen
screen = screen.replace(activate_anchor, activate_replacement, 1)

index_method_end = """    _ensureSelectedBookVisible();
  }

  void _tapHubCard(int index) {
"""
source_menu = r'''    _ensureSelectedBookVisible();
  }

  Future<void> _openSourceMenu() async {
    final options = _sourceOptions;
    final selected = await showMenu<String>(
      context: context,
      position: _popupPosition(),
      items: [
        for (final entry in options.entries)
          PopupMenuItem<String>(
            value: entry.key,
            child: Row(
              children: [
                SizedBox(
                  width: 28.r,
                  child: entry.key == _sourceFilter
                      ? Icon(Symbols.check_rounded, size: 18.r)
                      : null,
                ),
                Flexible(child: Text(_sourceLabel(entry.key))),
              ],
            ),
          ),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _sourceFilter = selected;
      _librarySelectedIndex = 0;
      _alphabetAnchor = null;
    });
  }

  void _tapHubCard(int index) {
'''
assert index_method_end in screen
screen = screen.replace(index_method_end, source_menu, 1)

# Treat Aidoku imports as repository imports for success messages.
screen = screen.replace(
    "if (result.format == LibraryAddonDocumentFormat.tachiyomiRepository) {",
    "if (result.format == LibraryAddonDocumentFormat.tachiyomiRepository ||\n          result.format == LibraryAddonDocumentFormat.aidokuRepository) {",
)
screen = screen.replace(
    "if (install.format == LibraryAddonDocumentFormat.tachiyomiRepository) {",
    "if (install.format == LibraryAddonDocumentFormat.tachiyomiRepository ||\n          install.format == LibraryAddonDocumentFormat.aidokuRepository) {",
)

# Add repository-aware delete choice to controller delete action.
delete_method_start = screen.index("  Future<void> _deleteSelectedAddon() async {")
delete_method_end = screen.index("  void _cycleLanguageFilter()", delete_method_start)
new_delete = r'''  Future<void> _deleteSelectedAddon() async {
    if (_view != _LibraryView.addons || _addonSelectedIndex < 3) return;
    final addonIndex = _addonSelectedIndex - 3;
    if (addonIndex < 0 || addonIndex >= _addons.length) return;
    final addon = _addons[addonIndex];
    if (addon.isBuiltIn) return;
    if (addon.isRepositorySource) {
      await _chooseRemoveSourceOrRepository(addon);
    } else {
      await _confirmRemoveAddon(addon);
    }
  }

'''
screen = screen[:delete_method_start] + new_delete + screen[delete_method_end:]

# Add Aidoku details and delete buttons in details dialog.
tach_details = """                if (addon.isTachiyomiRepositorySource) ...[
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
"""
aidoku_details = tach_details + """                if (addon.isAidokuRepositorySource) ...[
                  SizedBox(height: 10.r),
                  Text(
                    'Aidoku • ${addon.language ?? 'all'} • iOS source metadata',
                    style: Theme.of(dialogContext).textTheme.bodySmall?.copyWith(
                      color: Theme.of(dialogContext).colorScheme.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (addon.sourceDownloadUrl != null)
                    Text(
                      addon.sourceDownloadUrl!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(dialogContext).textTheme.bodySmall,
                    ),
                ],
"""
assert tach_details in screen
screen = screen.replace(tach_details, aidoku_details, 1)

actions_anchor = """          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(AppLocale.close.getString(dialogContext)),
            ),
          ],
"""
actions_replacement = """          actions: [
            if (!addon.isBuiltIn)
              TextButton.icon(
                onPressed: () async {
                  Navigator.of(dialogContext).pop();
                  if (addon.isRepositorySource) {
                    await _chooseRemoveSourceOrRepository(addon);
                  } else {
                    await _confirmRemoveAddon(addon);
                  }
                },
                icon: const Icon(Symbols.delete_rounded),
                label: Text(AppLocale.delete.getString(dialogContext)),
              ),
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(AppLocale.close.getString(dialogContext)),
            ),
          ],
"""
# Only replace first matching actions after addon details.
details_pos = screen.index("  Future<void> _showAddonDetails")
actions_pos = screen.index(actions_anchor, details_pos)
screen = screen[:actions_pos] + screen[actions_pos:].replace(actions_anchor, actions_replacement, 1)

confirm_pos = screen.index("  Future<void> _confirmRemoveAddon(LibraryAddon addon) async {")
repo_remove_methods = r'''  Future<void> _chooseRemoveSourceOrRepository(LibraryAddon addon) async {
    final locale = Localizations.localeOf(context).languageCode;
    final repositoryCount = _addons
        .where(
          (item) =>
              item.isRepositorySource &&
              item.repositoryOrigin == addon.repositoryOrigin,
        )
        .length;
    final choice = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(locale == 'fr' ? 'Supprimer' : 'Remove'),
        content: Text(
          locale == 'fr'
              ? 'Cette source appartient à un dépôt contenant $repositoryCount source(s).'
              : 'This source belongs to a repository containing $repositoryCount source(s).',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: Text(AppLocale.cancel.getString(dialogContext)),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop('source'),
            child: Text(locale == 'fr' ? 'Cette source' : 'This source'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop('repository'),
            child: Text(locale == 'fr' ? 'Tout le dépôt' : 'Entire repository'),
          ),
        ],
      ),
    );
    if (!mounted || choice == null) return;
    if (choice == 'repository') {
      await _confirmRemoveRepository(addon);
    } else {
      await _confirmRemoveAddon(addon);
    }
  }

  Future<void> _confirmRemoveRepository(LibraryAddon addon) async {
    final locale = Localizations.localeOf(context).languageCode;
    final origin = addon.repositoryOrigin;
    final count = _addons
        .where(
          (item) => item.isRepositorySource && item.repositoryOrigin == origin,
        )
        .length;
    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (dialogContext) => AlertDialog(
            title: Text(
              locale == 'fr' ? 'Supprimer le dépôt ?' : 'Remove repository?',
            ),
            content: Text(
              locale == 'fr'
                  ? 'Les $count sources importées depuis ce dépôt seront supprimées. Les autres dépôts et Gallica ne seront pas modifiés.'
                  : 'All $count sources imported from this repository will be removed. Other repositories and Gallica will not be changed.',
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
    if (!confirmed) return;
    final removed = await _addonService.removeRepository(origin);
    await _loadAddons();
    if (!mounted) return;
    setState(() {
      _addonSelectedIndex = _addonSelectedIndex.clamp(
        0,
        (_addonSelectionCount - 1).clamp(0, 9999),
      );
    });
    _showMessage(
      locale == 'fr'
          ? '$removed source(s) supprimée(s) avec le dépôt.'
          : '$removed source(s) removed with the repository.',
    );
  }

'''
screen = screen[:confirm_pos] + repo_remove_methods + screen[confirm_pos:]

# Add a fourth Source filter control.
filter_count_anchor = """        Expanded(
          child: _FilterControl(
            selected:
                _hubFocus == _HubFocus.filters && _filterSelectedIndex == 2,
            icon: Symbols.abc_rounded,
            label: 'Index',
            value: _alphabetAnchor == null ? 'A–Z' : _alphabetAnchor!,
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = 2;
              });
              _openIndexMenu();
            },
          ),
        ),
        SizedBox(width: 12.r),
        Text(
"""
filter_count_replacement = """        Expanded(
          child: _FilterControl(
            selected:
                _hubFocus == _HubFocus.filters && _filterSelectedIndex == 2,
            icon: Symbols.abc_rounded,
            label: 'Index',
            value: _alphabetAnchor == null ? 'A–Z' : _alphabetAnchor!,
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = 2;
              });
              _openIndexMenu();
            },
          ),
        ),
        SizedBox(width: 10.r),
        Expanded(
          child: _FilterControl(
            selected:
                _hubFocus == _HubFocus.filters && _filterSelectedIndex == 3,
            icon: Symbols.source_rounded,
            label: locale == 'fr' ? 'Source' : 'Source',
            value: _sourceLabel(_sourceFilter),
            onTap: () {
              setState(() {
                _hubFocus = _HubFocus.filters;
                _filterSelectedIndex = 3;
              });
              _openSourceMenu();
            },
          ),
        ),
        SizedBox(width: 12.r),
        Text(
"""
assert filter_count_anchor in screen
screen = screen.replace(filter_count_anchor, filter_count_replacement, 1)

# Keep source filter valid after refresh/removal.
refresh_anchor = """      _libraryItems = List.unmodifiable(entries);
      _catalogFailures = failures;
      _loadingLibrary = false;
      _alphabetAnchor = null;
"""
refresh_replacement = """      _libraryItems = List.unmodifiable(entries);
      _catalogFailures = failures;
      _loadingLibrary = false;
      _alphabetAnchor = null;
      if (_sourceFilter != 'all' &&
          !_libraryItems.any((entry) => entry.providerId == _sourceFilter)) {
        _sourceFilter = 'all';
      }
"""
assert refresh_anchor in screen
screen = screen.replace(refresh_anchor, refresh_replacement, 1)

# Stable bookmark identities for books and chapters.
screen = screen.replace(
    "          text: text,\n        ),",
    "          text: text,\n          bookmarkId: 'book:${item.id}:${item.title}',\n        ),",
    1,
)
screen = screen.replace(
    "          pages: pages,\n        ),",
    "          pages: pages,\n          bookmarkId: 'pages:$title:$subtitle',\n        ),",
    1,
)

# ---------------------------------------------------------------------------
# Tests: Aidoku parsing + repository-wide removal.
# ---------------------------------------------------------------------------
insert_before = "\n    test('keeps Gallica as a built-in native catalog source', () async {"
assert insert_before in tests
new_tests = r'''
    test('imports legacy Aidoku source-list entries', () async {
      final raw = jsonEncode([
        {
          'id': 'fr.example',
          'name': 'Example FR',
          'file': 'fr.example-v2.aix',
          'icon': 'fr.example-v2.png',
          'lang': 'fr',
          'version': 2,
          'nsfw': 0,
        },
      ]);

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin:
            'https://raw.githubusercontent.com/example/aidoku/gh-pages/index.min.json',
      );

      expect(result.format, LibraryAddonDocumentFormat.aidokuRepository);
      expect(result.totalCount, 1);
      expect(result.addons.single.isAidokuRepositorySource, isTrue);
      expect(result.addons.single.language, 'fr');
      expect(
        result.addons.single.sourceDownloadUrl,
        'https://raw.githubusercontent.com/example/aidoku/gh-pages/sources/fr.example-v2.aix',
      );
    });

    test('removes every source belonging to one imported repository', () async {
      final raw = jsonEncode([
        {
          'id': 'fr.one',
          'name': 'One',
          'file': 'fr.one-v1.aix',
          'lang': 'fr',
          'version': 1,
        },
        {
          'id': 'fr.two',
          'name': 'Two',
          'file': 'fr.two-v1.aix',
          'lang': 'fr',
          'version': 1,
        },
      ]);
      const origin =
          'https://raw.githubusercontent.com/example/aidoku/gh-pages/index.min.json';
      await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin: origin,
      );

      final removed = await LibraryAddonService.instance.removeRepository(origin);
      expect(removed, 2);
      final remaining = await LibraryAddonService.instance.load();
      expect(remaining.where((item) => item.repositoryOrigin == origin), isEmpty);
      expect(
        remaining.any((item) => item.id == LibraryAddonService.gallicaAddonId),
        isTrue,
      );
    });
'''
tests = tests.replace(insert_before, new_tests + insert_before, 1)

service_path.write_text(service)
screen_path.write_text(screen)
test_path.write_text(tests)

print('Library source/filter/repository patch applied successfully.')
