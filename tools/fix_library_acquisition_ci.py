from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "lib/services/library_metadata_provider_service.dart"

text = PROVIDER.read_text(encoding="utf-8")

# Library video support was intentionally removed. A legacy direct constructor
# still passed the old named argument in the BnF adapter, which breaks builds
# after LibraryCatalogItem no longer exposes videoUrls.
text = text.replace("          videoUrls: const <String>[],\n", "")
text = text.replace("      videoUrls: const <String>[],\n", "")

# html 0.15.6 exposes DocumentFragment.text as nullable. Keep metadata cleanup
# null-safe instead of calling trim() directly on String?.
text = text.replace(
    "return html_parser.parseFragment(text).text.trim();",
    "return (html_parser.parseFragment(text).text ?? '').trim();",
)

PROVIDER.write_text(text, encoding="utf-8")
print("Fixed Library acquisition compile leftovers.")
