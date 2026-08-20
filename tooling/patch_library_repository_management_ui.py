from pathlib import Path

p = Path('lib/screens/library_screen/library_screen.dart')
s = p.read_text(encoding='utf-8')

# Add repository grouping helper before buildAddons.
anchor = '''  Widget _buildCatalogProgressSliver(BuildContext context) {
'''
helper = '''  Map<String, List<LibraryAddon>> get _installedRepositoryGroups {
    final groups = <String, List<LibraryAddon>>{};
    for (final addon in _addons) {
      if (!addon.isRepositorySource || addon.isBuiltIn) continue;
      groups.putIfAbsent(addon.repositoryOrigin, () => <LibraryAddon>[]).add(addon);
    }
    return groups;
  }

  String _repositoryDisplayName(String origin) {
    final uri = Uri.tryParse(origin);
    if (uri != null && uri.host.isNotEmpty) {
      final path = uri.pathSegments.where((segment) => segment.isNotEmpty).toList();
      if (uri.host == 'github.com' && path.length >= 2) {
        return '${path[0]}/${path[1]}';
      }
      return uri.host;
    }
    return origin;
  }

  Widget _buildCatalogProgressSliver(BuildContext context) {
'''
if anchor not in s:
    raise SystemExit('catalog progress anchor not found')
s = s.replace(anchor, helper, 1)

# Replace buildAddons with repository management UI while preserving source selection indices.
start = s.find('  Widget _buildAddons(BuildContext context) {')
end = s.find('  Widget _buildLocalLibrary(BuildContext context) {', start)
if start < 0 or end < 0:
    raise SystemExit('buildAddons range not found')
new_build = r'''  Widget _buildAddons(BuildContext context) {
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).languageCode;
    final repositoryGroups = _installedRepositoryGroups;
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
                subtitle: locale == 'fr'
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
        Expanded(
          child: _loadingAddons
              ? const Center(child: CircularProgressIndicator())
              : SingleChildScrollView(
                  padding: EdgeInsets.only(bottom: 26.r),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (repositoryGroups.isNotEmpty) ...[
                        Row(
                          children: [
                            Icon(
                              Symbols.inventory_2_rounded,
                              size: 18.r,
                              color: theme.colorScheme.primary,
                            ),
                            SizedBox(width: 7.r),
                            Text(
                              locale == 'fr' ? 'Dépôts installés' : 'Installed repositories',
                              style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: 5.r),
                        Text(
                          locale == 'fr'
                              ? 'Un dépôt peut être supprimé entièrement, avec toutes les sources qu’il a ajoutées.'
                              : 'A repository can be removed entirely together with every source it installed.',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                          ),
                        ),
                        SizedBox(height: 8.r),
                        for (final entry in repositoryGroups.entries) ...[
                          _RepositoryManagementRow(
                            name: _repositoryDisplayName(entry.key),
                            origin: entry.key,
                            sourceCount: entry.value.length,
                            onDelete: () => _confirmRemoveRepository(entry.value.first),
                          ),
                          SizedBox(height: 8.r),
                        ],
                        SizedBox(height: 8.r),
                      ],
                      Row(
                        children: [
                          Icon(
                            Symbols.extension_rounded,
                            size: 18.r,
                            color: theme.colorScheme.primary,
                          ),
                          SizedBox(width: 7.r),
                          Text(
                            AppLocale.libraryAddonInstalledSources.getString(context),
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 5.r),
                      Text(
                        locale == 'fr'
                            ? 'Chaque source ajoutée peut être retirée individuellement. Les sources natives sont conservées.'
                            : 'Every added source can be removed individually. Built-in sources are kept.',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                        ),
                      ),
                      SizedBox(height: 8.r),
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
                            selected: _addonSelectedIndex == index + 3,
                            onTap: () => _tapAddonSelection(index + 3),
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
s = s[:start] + new_build + s[end:]

# Replace AddonRow with explicit text action and add repository row widget.
start = s.find('class _AddonRow extends StatelessWidget {')
if start < 0:
    raise SystemExit('AddonRow class not found')
new_tail = r'''class _RepositoryManagementRow extends StatelessWidget {
  const _RepositoryManagementRow({
    required this.name,
    required this.origin,
    required this.sourceCount,
    required this.onDelete,
  });

  final String name;
  final String origin;
  final int sourceCount;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fr = Localizations.localeOf(context).languageCode == 'fr';
    final radius = BorderRadius.circular(10.r);
    return NeoGlass(
      role: GlassSurfaceRole.card,
      borderRadius: radius,
      enableBackdropBlur: false,
      showSheen: false,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: 12.r, vertical: 9.r),
        child: Row(
          children: [
            Container(
              width: 38.r,
              height: 38.r,
              decoration: BoxDecoration(
                color: theme.colorScheme.primary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(9.r),
              ),
              child: Icon(
                Symbols.inventory_2_rounded,
                color: theme.colorScheme.primary,
                size: 21.r,
              ),
            ),
            SizedBox(width: 10.r),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  SizedBox(height: 2.r),
                  Text(
                    fr
                        ? '$sourceCount source${sourceCount > 1 ? 's' : ''} • $origin'
                        : '$sourceCount source${sourceCount == 1 ? '' : 's'} • $origin',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.58),
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(width: 10.r),
            OutlinedButton.icon(
              onPressed: onDelete,
              icon: const Icon(Symbols.delete_forever_rounded),
              label: Text(fr ? 'Supprimer le dépôt' : 'Remove repository'),
              style: OutlinedButton.styleFrom(
                foregroundColor: theme.colorScheme.error,
                side: BorderSide(
                  color: theme.colorScheme.error.withValues(alpha: 0.55),
                ),
                padding: EdgeInsets.symmetric(horizontal: 12.r, vertical: 9.r),
              ),
            ),
          ],
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
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fr = Localizations.localeOf(context).languageCode == 'fr';
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
          trailing: addon.isBuiltIn
              ? Container(
                  padding: EdgeInsets.symmetric(horizontal: 9.r, vertical: 5.r),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(8.r),
                  ),
                  child: Text(
                    fr ? 'Native' : 'Built-in',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.primary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                )
              : OutlinedButton.icon(
                  onPressed: onDelete,
                  icon: const Icon(Symbols.delete_outline_rounded),
                  label: Text(fr ? 'Supprimer la source' : 'Remove source'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: theme.colorScheme.error,
                    side: BorderSide(
                      color: theme.colorScheme.error.withValues(alpha: 0.5),
                    ),
                    padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 8.r),
                  ),
                ),
        ),
      ),
    );
  }
}
'''
s = s[:start] + new_tail + '\n'

p.write_text(s, encoding='utf-8')
