#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:180]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# The SFO parser is now a legitimate shared RPCS3 integration primitive, not
# merely a test helper.
replace_once(
    'lib/services/rpcs3_library_service.dart',
    '''  /// Parses Sony's binary PSF/SFO format used by PARAM.SFO.\n  @visibleForTesting\n  static Map<String, Object> parseParamSfoBytes(Uint8List bytes) {''',
    '''  /// Parses Sony's binary PSF/SFO format used by PARAM.SFO.\n  /// Shared by RPCS3 library discovery and NeoSync savedata metadata parsing.\n  static Map<String, Object> parseParamSfoBytes(Uint8List bytes) {''',
)

resolver = 'lib/providers/neosync/neosync_path_resolver.dart'
replace_once(
    resolver,
    '''    if (canonicalName.isEmpty) canonicalName = sfoTitle ?? '';\n    if (canonicalName.isEmpty)\n      canonicalName = saveTitleId ?? location.saveDirectory;''',
    '''    if (canonicalName.isEmpty) {\n      canonicalName = sfoTitle ?? '';\n    }\n    if (canonicalName.isEmpty) {\n      canonicalName = saveTitleId ?? location.saveDirectory;\n    }''',
)

print('RPCS3 NeoSync analyzer fixes applied')
