from pathlib import Path

root = Path(__file__).resolve().parents[1]
library = root / 'lib/screens/library_screen/library_screen.dart'
reader = root / 'lib/screens/library_screen/library_reader_screen.dart'

source = library.read_text(encoding='utf-8')
start_marker = "\n) async {\n    const layerId = 'library_page_reader';"
end_marker = "\n  Future<void> _openMangaDexTitle(LibraryCatalogItem item) async {"
start = source.find(start_marker)
end = source.find(end_marker, start + 1) if start >= 0 else -1
if start < 0 or end < 0:
    raise SystemExit('Old page-reader residue not found')
source = source[:start] + "\n" + source[end:]

replacements = {
    "_addonSelectedIndex = (_addonSelectionCount - 1).clamp(0, 9999);":
        "_addonSelectedIndex = (_addonSelectionCount - 1).clamp(0, 9999).toInt();",
    "final next = (_addonSelectedIndex + delta).clamp(0, 2);":
        "final next = (_addonSelectedIndex + delta).clamp(0, 2).toInt();",
    "final next = (_hubSelectedIndex + delta).clamp(0, 1);":
        "final next = (_hubSelectedIndex + delta).clamp(0, 1).toInt();",
    "final next = (_filterSelectedIndex + delta).clamp(0, 2);":
        "final next = (_filterSelectedIndex + delta).clamp(0, 2).toInt();",
    "final right = (size.width - 360.r).clamp(24.0, size.width - 48.0);":
        "final right = (size.width - 360.r).clamp(24.0, size.width - 48.0).toDouble();",
}
for old, new in replacements.items():
    if old in source:
        source = source.replace(old, new)

source = source.replace(
    "final next = (_librarySelectedIndex + delta).clamp(\n          0,\n          visible.length - 1,\n        );",
    "final next = (_librarySelectedIndex + delta).clamp(\n          0,\n          visible.length - 1,\n        ).toInt();",
)
source = source.replace(
    "final next = (_addonSelectedIndex + delta).clamp(\n        0,\n        _addonSelectionCount - 1,\n      );",
    "final next = (_addonSelectedIndex + delta).clamp(\n        0,\n        _addonSelectionCount - 1,\n      ).toInt();",
)
source = source.replace(
    "_librarySelectedIndex = _librarySelectedIndex.clamp(\n            0,\n            visible.length - 1,\n          );",
    "_librarySelectedIndex = _librarySelectedIndex.clamp(\n            0,\n            visible.length - 1,\n          ).toInt();",
)
source = source.replace(
    "final clamped = next.clamp(0, visible.length - 1);",
    "final clamped = next.clamp(0, visible.length - 1).toInt();",
)
library.write_text(source, encoding='utf-8')

reader_source = reader.read_text(encoding='utf-8')
reader_source = reader_source.replace(
    "fontSize: 16.r.clamp(14.0, 21.0),",
    "fontSize: 16.r.clamp(14.0, 21.0).toDouble(),",
)
reader.write_text(reader_source, encoding='utf-8')
print('Removed stale reader body and normalized numeric clamp types.')
