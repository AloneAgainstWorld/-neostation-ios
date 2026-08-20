#!/usr/bin/env python3
from pathlib import Path

screen_path = Path('lib/screens/library_screen/library_screen.dart')
s = screen_path.read_text(encoding='utf-8')

old = '''      final result = await _addonService.installFromUrl(url);\n      await _loadAddons();\n      if (!mounted) return;\n      _showMessage(\n        result.updated\n            ? AppLocale.libraryAddonUpdated\n                  .getString(context)\n                  .replaceFirst('{name}', result.addon.name)\n            : AppLocale.libraryAddonInstalled\n                  .getString(context)\n                  .replaceFirst('{name}', result.addon.name),\n      );'''
new = '''      final result = await _addonService.installDocumentFromUrl(url);\n      await _loadAddons();\n      if (!mounted) return;\n      if (result.format == LibraryAddonDocumentFormat.tachiyomiRepository) {\n        _showMessage(\n          AppLocale.libraryAddonCount\n              .getString(context)\n              .replaceFirst('{count}', result.totalCount.toString()),\n        );\n      } else {\n        final addon = result.addons.single;\n        _showMessage(\n          result.updatedCount > 0\n              ? AppLocale.libraryAddonUpdated\n                    .getString(context)\n                    .replaceFirst('{name}', addon.name)\n              : AppLocale.libraryAddonInstalled\n                    .getString(context)\n                    .replaceFirst('{name}', addon.name),\n        );\n      }'''
if old not in s:
    if new not in s:
        raise SystemExit('URL import block not found')
else:
    s = s.replace(old, new, 1)

old = '''      final install = await _addonService.installFromJson(\n        utf8.decode(bytes),\n        origin: 'file:${picked.name}',\n      );\n      await _loadAddons();\n      if (!mounted) return;\n      _showMessage(\n        install.updated\n            ? AppLocale.libraryAddonUpdated\n                  .getString(context)\n                  .replaceFirst('{name}', install.addon.name)\n            : AppLocale.libraryAddonInstalled\n                  .getString(context)\n                  .replaceFirst('{name}', install.addon.name),\n      );'''
new = '''      final install = await _addonService.installDocumentFromJson(\n        utf8.decode(bytes),\n        origin: 'file:${picked.name}',\n      );\n      await _loadAddons();\n      if (!mounted) return;\n      if (install.format == LibraryAddonDocumentFormat.tachiyomiRepository) {\n        _showMessage(\n          AppLocale.libraryAddonCount\n              .getString(context)\n              .replaceFirst('{count}', install.totalCount.toString()),\n        );\n      } else {\n        final addon = install.addons.single;\n        _showMessage(\n          install.updatedCount > 0\n              ? AppLocale.libraryAddonUpdated\n                    .getString(context)\n                    .replaceFirst('{name}', addon.name)\n              : AppLocale.libraryAddonInstalled\n                    .getString(context)\n                    .replaceFirst('{name}', addon.name),\n        );\n      }'''
if old not in s:
    if new not in s:
        raise SystemExit('Local import block not found')
else:
    s = s.replace(old, new, 1)

# Add Tachiyomi/Mihon metadata to the details dialog so repository entries are
# understandable on iOS without implying that their Android APK is executable.
old = '''                if (addon.description.isNotEmpty) ...[\n                  SizedBox(height: 10.r),\n                  Text(addon.description),\n                ],\n                SizedBox(height: 12.r),'''
new = '''                if (addon.description.isNotEmpty) ...[\n                  SizedBox(height: 10.r),\n                  Text(addon.description),\n                ],\n                if (addon.isTachiyomiRepositorySource) ...[\n                  SizedBox(height: 10.r),\n                  Text(\n                    'Tachiyomi/Mihon • ${addon.language ?? 'all'} • iOS metadata',\n                    style: Theme.of(dialogContext).textTheme.bodySmall?.copyWith(\n                      color: Theme.of(dialogContext).colorScheme.primary,\n                      fontWeight: FontWeight.w600,\n                    ),\n                  ),\n                  if (addon.androidPackage != null)\n                    Text(\n                      addon.androidPackage!,\n                      style: Theme.of(dialogContext).textTheme.bodySmall,\n                    ),\n                ],\n                SizedBox(height: 12.r),'''
if old not in s:
    if new not in s:
        raise SystemExit('Details block not found')
else:
    s = s.replace(old, new, 1)

screen_path.write_text(s, encoding='utf-8')

# Rename the hub concept from Add-ons to a source Directory/Repository. Keep
# the localization key stable so existing settings and translations do not need
# a schema migration.
replacements = {
    'fr': [('AppLocale.libraryAddons: \'Add-ons\'', "AppLocale.libraryAddons: 'Répertoire'"),
           ("AppLocale.libraryAddonsSubtitle:\n      'Ajoutez des sources externes pour enrichir votre bibliothèque.'", "AppLocale.libraryAddonsSubtitle:\n      'Parcourez et ajoutez des dépôts ou des sources externes.'"),
           ("'URL HTTPS du manifeste (schéma neostation.library.v1).'", "'URL HTTPS d’un manifeste NeoStation ou d’un dépôt Tachiyomi/Mihon.'")],
    'en': [("AppLocale.libraryAddons: 'Add-ons'", "AppLocale.libraryAddons: 'Directory'"),
           ("'Add external sources to expand your library.'", "'Browse and add repositories or external sources.'"),
           ("'HTTPS manifest URL (schema neostation.library.v1).'", "'HTTPS NeoStation manifest or Tachiyomi/Mihon repository URL.'")],
}
for lang, pairs in replacements.items():
    p = Path(f'lib/l10n/app_locale_{lang}.dart')
    t = p.read_text(encoding='utf-8')
    for a, b in pairs:
        if a in t:
            t = t.replace(a, b, 1)
    p.write_text(t, encoding='utf-8')

print('Library Tachiyomi/Mihon repository UI patch applied')
