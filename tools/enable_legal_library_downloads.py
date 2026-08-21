from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel_path: str, old: str, new: str) -> None:
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Anchor not found in {rel_path}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Keep download support generic and source-driven. NeoStation never fabricates
# acquisition URLs: a provider/add-on must explicitly return one over HTTPS.
replace_once(
    "lib/services/library_catalog_service.dart",
    "    required this.pageUrls,\n    required this.raw,\n",
    "    required this.pageUrls,\n    required this.raw,\n    this.downloadUrl,\n",
)
replace_once(
    "lib/services/library_catalog_service.dart",
    "  final List<String> pageUrls;\n  final Map<String, dynamic> raw;\n",
    "  final List<String> pageUrls;\n  final Map<String, dynamic> raw;\n  final String? downloadUrl;\n",
)
replace_once(
    "lib/services/library_catalog_service.dart",
    "      pageUrls: List.unmodifiable(pageUrls),\n      raw: Map<String, dynamic>.unmodifiable(raw),\n",
    "      pageUrls: List.unmodifiable(pageUrls),\n      raw: Map<String, dynamic>.unmodifiable(raw),\n      downloadUrl: resolveUrl(\n        raw['downloadUrl'] ??\n            raw['acquisitionUrl'] ??\n            raw['epubUrl'] ??\n            raw['pdfUrl'],\n      ),\n",
)

# Provider adapters remain catalog/reading sources. Only pass through a
# provider-authorized download link when the upstream API actually exposes one.
provider = ROOT / "lib/services/library_metadata_provider_service.dart"
text = provider.read_text(encoding="utf-8")

old_google = """      final accessInfo = _asMap(raw['accessInfo']);\n      final sourceUrl = _firstHttps(<dynamic>[\n"""
new_google = """      final accessInfo = _asMap(raw['accessInfo']);\n      final epubAccess = _asMap(accessInfo?['epub']);\n      final pdfAccess = _asMap(accessInfo?['pdf']);\n      final downloadUrl = _firstHttps(<dynamic>[\n        epubAccess?['downloadLink'],\n        pdfAccess?['downloadLink'],\n      ]);\n      final sourceUrl = _firstHttps(<dynamic>[\n"""
if old_google not in text:
    raise RuntimeError("Google Books accessInfo anchor not found")
text = text.replace(old_google, new_google, 1)

old_norm = """        'previewUrl': _https(volume['previewLink']),\n        'webReaderLink': _https(accessInfo?['webReaderLink']),\n"""
new_norm = """        'previewUrl': _https(volume['previewLink']),\n        'webReaderLink': _https(accessInfo?['webReaderLink']),\n        'downloadUrl': downloadUrl,\n"""
if old_norm not in text:
    raise RuntimeError("Google Books normalized metadata anchor not found")
text = text.replace(old_norm, new_norm, 1)

old_item_call = """          description: _cleanText(volume['description']),\n          coverUrl: _firstHttps(<dynamic>[\n"""
new_item_call = """          description: _cleanText(volume['description']),\n          downloadUrl: downloadUrl,\n          coverUrl: _firstHttps(<dynamic>[\n"""
if old_item_call not in text:
    raise RuntimeError("Google Books item call anchor not found")
text = text.replace(old_item_call, new_item_call, 1)

old_signature = """    String description = '',\n    String? coverUrl,\n    List<String> authors = const <String>[],\n"""
new_signature = """    String description = '',\n    String? coverUrl,\n    String? downloadUrl,\n    List<String> authors = const <String>[],\n"""
if old_signature not in text:
    raise RuntimeError("_item signature anchor not found")
text = text.replace(old_signature, new_signature, 1)

old_return = """      pageUrls: const <String>[],\n      raw: Map<String, dynamic>.unmodifiable(<String, dynamic>{\n"""
new_return = """      pageUrls: const <String>[],\n      downloadUrl: _https(downloadUrl),\n      raw: Map<String, dynamic>.unmodifiable(<String, dynamic>{\n"""
if old_return not in text:
    raise RuntimeError("_item return anchor not found")
text = text.replace(old_return, new_return, 1)
provider.write_text(text, encoding="utf-8")

# When a Manga Provider result has no directly readable pages/content but does
# expose an authorized acquisition link, offer that link instead of pretending
# the synopsis is the book. This keeps downloads possible for lawful providers
# and user-added sources without turning NeoStation into a piracy search layer.
screen = ROOT / "lib/screens/library_screen/library_screen.dart"
text = screen.read_text(encoding="utf-8")
if "package:url_launcher/url_launcher.dart" not in text:
    import_anchor = "import 'package:material_symbols_icons/symbols.dart';\n"
    if import_anchor not in text:
        raise RuntimeError("LibraryScreen import anchor not found")
    text = text.replace(
        import_anchor,
        import_anchor + "import 'package:url_launcher/url_launcher.dart';\n",
        1,
    )

old_branch = """      if ((item.content?.trim().isNotEmpty ?? false) || item.contentUrl != null) {\n        try {\n          final text = await _catalogService.loadReadableText(item);\n          if (!mounted) return;\n          await _showTextReader(item, text);\n        } on LibraryAddonException catch (error) {\n          _showMessage(error.message);\n        }\n        return;\n      }\n\n      final fr = Localizations.localeOf(context).languageCode == 'fr';\n"""
new_branch = """      if ((item.content?.trim().isNotEmpty ?? false) || item.contentUrl != null) {\n        try {\n          final text = await _catalogService.loadReadableText(item);\n          if (!mounted) return;\n          await _showTextReader(item, text);\n        } on LibraryAddonException catch (error) {\n          _showMessage(error.message);\n        }\n        return;\n      }\n\n      final downloadUrl = item.downloadUrl;\n      if (downloadUrl != null) {\n        final uri = Uri.tryParse(downloadUrl);\n        if (uri != null && uri.scheme == 'https' && uri.host.isNotEmpty) {\n          final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);\n          if (opened || !mounted) return;\n        }\n      }\n\n      final fr = Localizations.localeOf(context).languageCode == 'fr';\n"""
if old_branch not in text:
    raise RuntimeError("Manga Provider readable-content branch not found")
text = text.replace(old_branch, new_branch, 1)
screen.write_text(text, encoding="utf-8")

print("Enabled source-provided lawful Library download/acquisition links.")
