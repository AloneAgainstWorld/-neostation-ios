from pathlib import Path

p = Path('lib/screens/library_screen/library_screen.dart')
s = p.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global s
    if old not in s:
        raise SystemExit(f'anchor not found: {label}')
    s = s.replace(old, new, 1)

replace_once(
    "enum _LibraryView { hub, addons, local }",
    "enum _LibraryView { hub, addons, local, manage }",
    'library view enum',
)

replace_once(
    """      case _HubFocus.shortcuts:\n        final next = (_hubSelectedIndex + delta).clamp(0, 1).toInt();""",
    """      case _HubFocus.shortcuts:\n        final next = (_hubSelectedIndex + delta).clamp(0, 2).toInt();""",
    'hub horizontal shortcuts',
)

replace_once(
    """  bool _navigateVertical(int delta) {\n    if (_view == _LibraryView.addons) {""",
    """  bool _navigateVertical(int delta) {\n    if (_view == _LibraryView.manage) {\n      if (_addons.isEmpty) return false;\n      final next = (_addonSelectedIndex + delta).clamp(0, _addons.length - 1).toInt();\n      if (next == _addonSelectedIndex) return false;\n      setState(() => _addonSelectedIndex = next);\n      return true;\n    }\n\n    if (_view == _LibraryView.addons) {""",
    'manage vertical navigation',
)

replace_once(
    """        if (_hubSelectedIndex == 0) {\n          setState(() {\n            _view = _LibraryView.addons;\n            _addonSelectedIndex = 0;\n          });\n        } else {\n          setState(() => _view = _LibraryView.local);\n        }\n        return;""",
    """        if (_hubSelectedIndex == 0) {\n          setState(() {\n            _view = _LibraryView.addons;\n            _addonSelectedIndex = 0;\n          });\n        } else if (_hubSelectedIndex == 1) {\n          setState(() => _view = _LibraryView.local);\n        } else {\n          setState(() {\n            _view = _LibraryView.manage;\n            _addonSelectedIndex = 0;\n          });\n        }\n        return;""",
    'hub shortcut activation',
)

replace_once(
    """    if (_view == _LibraryView.local) {\n      _backToHub(selectLocal: true);\n      return;\n    }\n\n    if (_addonSelectedIndex == 0) {""",
    """    if (_view == _LibraryView.local) {\n      _backToHub(selectLocal: true);\n      return;\n    }\n\n    if (_view == _LibraryView.manage) {\n      if (_addonSelectedIndex >= 0 && _addonSelectedIndex < _addons.length) {\n        _showAddonDetails(_addons[_addonSelectedIndex]);\n      }\n      return;\n    }\n\n    if (_addonSelectedIndex == 0) {""",
    'manage activation',
)

replace_once(
    """    if (_view == _LibraryView.addons || _view == _LibraryView.local) {\n      _backToHub();\n      return;\n    }""",
    """    if (_view == _LibraryView.addons || _view == _LibraryView.local) {\n      _backToHub();\n      return;\n    }\n    if (_view == _LibraryView.manage) {\n      _backToHub(selectManage: true);\n      return;\n    }""",
    'manage back',
)

replace_once(
    """  void _backToHub({bool selectLocal = false}) {\n    setState(() {\n      _view = _LibraryView.hub;\n      _hubFocus = _HubFocus.shortcuts;\n      _hubSelectedIndex = selectLocal ? 1 : 0;\n    });\n  }""",
    """  void _backToHub({bool selectLocal = false, bool selectManage = false}) {\n    setState(() {\n      _view = _LibraryView.hub;\n      _hubFocus = _HubFocus.shortcuts;\n      _hubSelectedIndex = selectManage ? 2 : (selectLocal ? 1 : 0);\n    });\n  }""",
    'back to hub signature',
)

replace_once(
    """  Future<void> _deleteSelectedAddon() async {\n    if (_view != _LibraryView.addons || _addonSelectedIndex < 3) return;\n    final addonIndex = _addonSelectedIndex - 3;\n    if (addonIndex < 0 || addonIndex >= _addons.length) return;""",
    """  Future<void> _deleteSelectedAddon() async {\n    final int addonIndex;\n    if (_view == _LibraryView.addons) {\n      if (_addonSelectedIndex < 3) return;\n      addonIndex = _addonSelectedIndex - 3;\n    } else if (_view == _LibraryView.manage) {\n      addonIndex = _addonSelectedIndex;\n    } else {\n      return;\n    }\n    if (addonIndex < 0 || addonIndex >= _addons.length) return;""",
    'delete selected manage',
)

replace_once(
    """          _LibraryView.hub => _buildHub(context),\n          _LibraryView.addons => _buildAddons(context),\n          _LibraryView.local => _buildLocalLibrary(context),""",
    """          _LibraryView.hub => _buildHub(context),\n          _LibraryView.addons => _buildAddons(context),\n          _LibraryView.local => _buildLocalLibrary(context),\n          _LibraryView.manage => _buildManageSources(context),""",
    'build switch',
)

replace_once(
    """              Expanded(\n                child: _LibraryEntryCard(\n                  selected:\n                      _hubFocus == _HubFocus.shortcuts && _hubSelectedIndex == 1,\n                  icon: Symbols.folder_open_rounded,\n                  title: AppLocale.libraryLocal.getString(context),\n                  subtitle: AppLocale.libraryLocalSubtitle.getString(context),\n                  onTap: () => _tapHubCard(1),\n                ),\n              ),\n            ],""",
    """              Expanded(\n                child: _LibraryEntryCard(\n                  selected:\n                      _hubFocus == _HubFocus.shortcuts && _hubSelectedIndex == 1,\n                  icon: Symbols.folder_open_rounded,\n                  title: AppLocale.libraryLocal.getString(context),\n                  subtitle: AppLocale.libraryLocalSubtitle.getString(context),\n                  onTap: () => _tapHubCard(1),\n                ),\n              ),\n              SizedBox(width: 14.r),\n              Expanded(\n                child: _LibraryEntryCard(\n                  selected:\n                      _hubFocus == _HubFocus.shortcuts && _hubSelectedIndex == 2,\n                  icon: Symbols.manage_accounts_rounded,\n                  title: Localizations.localeOf(context).languageCode == 'fr'\n                      ? 'Gérer les sources'\n                      : 'Manage sources',\n                  subtitle: Localizations.localeOf(context).languageCode == 'fr'\n                      ? 'Supprimer une source ou un dépôt installé.'\n                      : 'Remove an installed source or repository.',\n                  onTap: () => _tapHubCard(2),\n                ),\n              ),\n            ],""",
    'third hub card',
)

manage_method = r'''  Widget _buildManageSources(BuildContext context) {
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).languageCode;
    final repositoryGroups = _installedRepositoryGroups;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(
          context,
          trailing: FilledButton.tonalIcon(
            onPressed: () => _backToHub(selectManage: true),
            icon: const Icon(Symbols.arrow_back_rounded),
            label: Text(AppLocale.back.getString(context)),
          ),
        ),
        SizedBox(height: 18.r),
        Row(
          children: [
            Icon(
              Symbols.manage_accounts_rounded,
              size: 24.r,
              color: theme.colorScheme.primary,
            ),
            SizedBox(width: 9.r),
            Text(
              locale == 'fr' ? 'Gérer les sources' : 'Manage sources',
              style: theme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        SizedBox(height: 5.r),
        Text(
          locale == 'fr'
              ? 'Retirez à tout moment une source devenue inutile ou un dépôt complet devenu indisponible.'
              : 'Remove an unused source or an unavailable repository at any time.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurface.withValues(alpha: 0.64),
          ),
        ),
        SizedBox(height: 12.r),
        Expanded(
          child: _loadingAddons
              ? const Center(child: CircularProgressIndicator())
              : SingleChildScrollView(
                  padding: EdgeInsets.only(bottom: 26.r),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (repositoryGroups.isNotEmpty) ...[
                        Text(
                          locale == 'fr' ? 'Dépôts installés' : 'Installed repositories',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        SizedBox(height: 7.r),
                        for (final entry in repositoryGroups.entries) ...[
                          _RepositoryManagementRow(
                            name: _repositoryDisplayName(entry.key),
                            origin: entry.key,
                            sourceCount: entry.value.length,
                            onDelete: () => _confirmRemoveRepository(entry.value.first),
                          ),
                          SizedBox(height: 8.r),
                        ],
                        SizedBox(height: 10.r),
                      ],
                      Text(
                        AppLocale.libraryAddonInstalledSources.getString(context),
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 7.r),
                      if (_addons.isEmpty)
                        Padding(
                          padding: EdgeInsets.symmetric(vertical: 36.r),
                          child: Center(
                            child: Text(
                              AppLocale.libraryEmptyTitle.getString(context),
                              style: theme.textTheme.bodyMedium?.copyWith(
                                color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                              ),
                            ),
                          ),
                        )
                      else
                        for (var index = 0; index < _addons.length; index++) ...[
                          _AddonRow(
                            addon: _addons[index],
                            selected: _addonSelectedIndex == index,
                            onTap: () {
                              setState(() => _addonSelectedIndex = index);
                              _showAddonDetails(_addons[index]);
                            },
                            onDelete: _addons[index].isBuiltIn
                                ? null
                                : () => _confirmRemoveAddon(_addons[index]),
                          ),
                          if (index + 1 < _addons.length) SizedBox(height: 8.r),
                        ],
                    ],
                  ),
                ),
        ),
      ],
    );
  }

'''
anchor = "  Widget _buildLocalLibrary(BuildContext context) {\n"
if anchor not in s:
    raise SystemExit('anchor not found: manage method insertion')
s = s.replace(anchor, manage_method + anchor, 1)

# Keep the selection in range after deletions in either the Add-ons or Manage view.
old_clamp = """    setState(() {\n      _addonSelectedIndex = _addonSelectedIndex.clamp(\n        0,\n        (_addonSelectionCount - 1).clamp(0, 9999),\n      );\n    });"""
new_clamp = """    setState(() {\n      final maxIndex = _view == _LibraryView.manage\n          ? (_addons.length - 1).clamp(0, 9999)\n          : (_addonSelectionCount - 1).clamp(0, 9999);\n      _addonSelectedIndex = _addonSelectedIndex.clamp(0, maxIndex);\n    });"""
if s.count(old_clamp) < 2:
    raise SystemExit('expected two deletion clamp blocks')
s = s.replace(old_clamp, new_clamp, 2)

p.write_text(s, encoding='utf-8')
