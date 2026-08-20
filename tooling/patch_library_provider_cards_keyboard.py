from pathlib import Path

screen_path = Path('lib/screens/library_screen/library_screen.dart')
lifecycle_path = Path('lib/widgets/app_lifecycle_handler.dart')

screen = screen_path.read_text(encoding='utf-8')
lifecycle = lifecycle_path.read_text(encoding='utf-8')

old = """  bool get isMangaDex => providerId == LibraryMangaDexService.providerId;\n}\n"""
new = """  bool get isMangaDex => providerId == LibraryMangaDexService.providerId;\n\n  bool get isSourceCard => item.raw['neoStationSourceCard'] == true;\n}\n"""
assert old in screen
screen = screen.replace(old, new, 1)

marker = """  Future<void> _refreshNativeLibrary([List<LibraryAddon>? installed]) async {\n"""
helper = """  _NativeLibraryEntry _sourceEntryForAddon(LibraryAddon addon) {\n    final isAnime =\n        addon.androidPackage?.contains('animeextension') == true;\n    final runtimeLabel = addon.isAidokuRepositorySource\n        ? 'Aidoku'\n        : (isAnime ? 'Aniyomi' : 'Tachiyomi / Mihon');\n    final language = addon.language?.trim().toLowerCase();\n    final languageLabel = language == null || language.isEmpty\n        ? 'ALL'\n        : language.toUpperCase();\n\n    return _NativeLibraryEntry(\n      providerId: addon.id,\n      source: addon,\n      item: LibraryCatalogItem(\n        id: 'source:${addon.id}',\n        title: addon.name,\n        mediaType: isAnime ? LibraryMediaType.anime : LibraryMediaType.manga,\n        subtitle: '$runtimeLabel • $languageLabel',\n        description: Localizations.localeOf(context).languageCode == 'fr'\n            ? 'Source installée depuis un dépôt externe. Ouvrez-la pour afficher ses informations.'\n            : 'Source installed from an external repository. Open it to view its details.',\n        coverUrl: addon.iconUrl,\n        content: null,\n        contentUrl: null,\n        pageUrls: const [],\n        raw: <String, dynamic>{\n          'neoStationSourceCard': true,\n          'language': language,\n          'repositoryOrigin': addon.repositoryOrigin,\n          'runtime': runtimeLabel,\n        },\n      ),\n    );\n  }\n\n"""
assert marker in screen
screen = screen.replace(marker, helper + marker, 1)

old = """    for (final addon in addons) {\n      if (!addon.canBrowseOnIos) continue;\n      try {\n"""
new = """    for (final addon in addons) {\n      if (addon.isRepositorySource && addon.isMetadataOnlyOnIos) {\n        entries.add(_sourceEntryForAddon(addon));\n        continue;\n      }\n      if (!addon.canBrowseOnIos) continue;\n      try {\n"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {\n    if (entry.isMangaDex) {\n"""
new = """  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {\n    if (entry.isSourceCard && entry.source != null) {\n      await _showAddonDetails(entry.source!);\n      return;\n    }\n\n    if (entry.isMangaDex) {\n"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """                            child: _LibraryCatalogCard(\n                              item: entry.item,\n                              languageLabel: languageLabel,\n                              selected:\n"""
new = """                            child: _LibraryCatalogCard(\n                              item: entry.item,\n                              languageLabel: languageLabel,\n                              isSourceCard: entry.isSourceCard,\n                              selected:\n"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """class _LibraryCatalogCard extends StatelessWidget {\n  const _LibraryCatalogCard({\n    required this.item,\n    required this.languageLabel,\n    required this.selected,\n    required this.onTap,\n  });\n\n  final LibraryCatalogItem item;\n  final String languageLabel;\n  final bool selected;\n"""
new = """class _LibraryCatalogCard extends StatelessWidget {\n  const _LibraryCatalogCard({\n    required this.item,\n    required this.languageLabel,\n    required this.isSourceCard,\n    required this.selected,\n    required this.onTap,\n  });\n\n  final LibraryCatalogItem item;\n  final String languageLabel;\n  final bool isSourceCard;\n  final bool selected;\n"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """                                child: Icon(\n                                  Symbols.menu_book_rounded,\n                                  color: theme.colorScheme.primary,\n                                  size: 34.r,\n                                ),\n"""
new = """                                child: Icon(\n                                  isSourceCard\n                                      ? Symbols.extension_rounded\n                                      : Symbols.menu_book_rounded,\n                                  color: theme.colorScheme.primary,\n                                  size: 34.r,\n                                ),\n"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """                                  child: Icon(\n                                    Symbols.menu_book_rounded,\n                                    color: theme.colorScheme.primary,\n                                    size: 34.r,\n                                  ),\n"""
new = """                                  child: Icon(\n                                    isSourceCard\n                                        ? Symbols.extension_rounded\n                                        : Symbols.menu_book_rounded,\n                                    color: theme.colorScheme.primary,\n                                    size: 34.r,\n                                  ),\n"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """          title: Text(\n            addon.name,\n"""
# Leave list rows unchanged; provider cards are handled above.
assert old in screen

old = """                          onDelete: () => _confirmRemoveAddon(addon),\n"""
new = """                          onDelete: () => addon.isRepositorySource\n                              ? _chooseRemoveSourceOrRepository(addon)\n                              : _confirmRemoveAddon(addon),\n"""
assert old in screen
screen = screen.replace(old, new, 1)

old = """    final countLabel = locale == 'fr'\n        ? '${visible.length} titre${visible.length > 1 ? 's' : ''}'\n        : '${visible.length} title${visible.length == 1 ? '' : 's'}';\n"""
new = """    final countLabel = locale == 'fr'\n        ? '${visible.length} élément${visible.length > 1 ? 's' : ''}'\n        : '${visible.length} item${visible.length == 1 ? '' : 's'}';\n"""
assert old in screen
screen = screen.replace(old, new, 1)

# Fix stale iOS keyboard after returning to NeoStation from another app.
old = """import 'package:flutter/material.dart';\n"""
new = """import 'package:flutter/material.dart';\nimport 'package:flutter/services.dart';\n"""
assert old in lifecycle
lifecycle = lifecycle.replace(old, new, 1)

old = """    if (state == AppLifecycleState.resumed) {\n      await GameService.handleAppResumed();\n"""
new = """    if (state == AppLifecycleState.resumed) {\n      // iOS can keep the system IME visible across app switches even when\n      // NeoStation has no active text field. Clear Flutter focus and explicitly\n      // dismiss the text-input channel before restoring the rest of the app.\n      FocusManager.instance.primaryFocus?.unfocus();\n      await SystemChannels.textInput.invokeMethod<void>('TextInput.hide');\n\n      await GameService.handleAppResumed();\n"""
assert old in lifecycle
lifecycle = lifecycle.replace(old, new, 1)

screen_path.write_text(screen, encoding='utf-8')
lifecycle_path.write_text(lifecycle, encoding='utf-8')
