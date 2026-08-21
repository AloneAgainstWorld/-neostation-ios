from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel_path: str, old: str, new: str) -> None:
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Anchor not found in {rel_path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def remove_between(rel_path: str, start: str, end: str) -> None:
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    a = text.find(start)
    b = text.find(end, a + len(start))
    if a < 0 or b < 0:
        raise RuntimeError(f"Block anchors not found in {rel_path}")
    path.write_text(text[:a] + text[b:], encoding="utf-8")


# Manga Provider is a simple Library source. Do not attach video/trailer media
# to catalog items; game video media is handled independently by the game-media
# pipeline (ScreenScraper / SteamGridDB fallback).
replace_once(
    "lib/services/library_catalog_service.dart",
    "    this.videoUrls = const <String>[],\n",
    "",
)
replace_once(
    "lib/services/library_catalog_service.dart",
    "  final List<String> videoUrls;\n",
    "",
)
remove_between(
    "lib/services/library_catalog_service.dart",
    "    final videoUrls = <String>[];\n",
    "    final inlineContent =\n",
)
replace_once(
    "lib/services/library_catalog_service.dart",
    "      videoUrls: List.unmodifiable(videoUrls),\n",
    "",
)

# Provider adapters remain focused on manga/book catalog data only.
provider_path = ROOT / "lib/services/library_metadata_provider_service.dart"
provider_text = provider_path.read_text(encoding="utf-8")
provider_text = provider_text.replace(
    "/// links, but this service never invents chapter/download URLs. Any video or\n"
    "/// trailer URL genuinely returned by a provider is preserved in `videoUrls` so\n"
    "/// the Library can expose it without changing that policy.\n",
    "/// links. The service never invents chapter/download URLs and deliberately\n"
    "/// ignores unrelated video/trailer media.\n",
)
provider_text = provider_text.replace(
    "      videoUrls: List<String>.unmodifiable(_extractVideoUrls(raw)),\n",
    "",
)
start = provider_text.find("  static List<String> _extractVideoUrls(dynamic value) {\n")
end = provider_text.find("  static dynamic _decodeJson", start)
if start >= 0 and end >= 0:
    provider_text = provider_text[:start] + provider_text[end:]
provider_path.write_text(provider_text, encoding="utf-8")

# Treat the seven Manga Provider definitions as ordinary Library source results.
# If a provider does not expose readable pages/content for a result, tell the
# user clearly instead of turning its synopsis into fake book content.
screen_path = ROOT / "lib/screens/library_screen/library_screen.dart"
screen_text = screen_path.read_text(encoding="utf-8")
screen_text = screen_text.replace(
    "import 'library_metadata_detail_dialog.dart';\n",
    "",
)
old_branch = """    if (_metadataProviderService.isProviderId(entry.providerId)) {\n      await showLibraryMetadataDetailDialog(\n        context,\n        item: entry.item,\n        providerName:\n            _metadataProviderService.labelFor(entry.providerId) ?? entry.providerId,\n      );\n      return;\n    }\n\n"""
new_branch = """    if (_metadataProviderService.isProviderId(entry.providerId)) {\n      final item = entry.item;\n      if (item.pageUrls.isNotEmpty) {\n        await _showPageReader(item.title, item.pageUrls, subtitle: item.subtitle);\n        return;\n      }\n      if ((item.content?.trim().isNotEmpty ?? false) || item.contentUrl != null) {\n        try {\n          final text = await _catalogService.loadReadableText(item);\n          if (!mounted) return;\n          await _showTextReader(item, text);\n        } on LibraryAddonException catch (error) {\n          _showMessage(error.message);\n        }\n        return;\n      }\n\n      final fr = Localizations.localeOf(context).languageCode == 'fr';\n      _showMessage(\n        fr\n            ? 'Cette source ne fournit pas de pages lisibles pour ce titre.'\n            : 'This source does not provide readable pages for this title.',\n      );\n      return;\n    }\n\n"""
if old_branch not in screen_text:
    raise RuntimeError("Manga Provider open-item branch not found")
screen_path.write_text(screen_text.replace(old_branch, new_branch, 1), encoding="utf-8")

# The temporary metadata-detail dialog is no longer part of the simple source
# flow. Remove it instead of leaving dead video/source-page UI behind.
detail = ROOT / "lib/screens/library_screen/library_metadata_detail_dialog.dart"
if detail.exists():
    detail.unlink()

# The patch and its bootstrap workflow are one-shot implementation helpers.
for rel in (
    "tools/simplify_manga_provider_sources.py",
    ".github/workflows/simplify-manga-provider.yml",
):
    candidate = ROOT / rel
    if candidate.exists():
        candidate.unlink()

print("Simplified Manga Provider integration: sources only, no Library video UI.")
