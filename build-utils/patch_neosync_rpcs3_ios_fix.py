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

resolver = 'lib/providers/neosync/neosync_path_resolver.dart'

# The existing RPCS3 SFO parser remains test-scoped in its service. NeoSync
# intentionally reuses the exact same binary parser here; suppress only this
# deliberate cross-module use rather than widening the public RPCS3 API.
replace_once(
    resolver,
    '        final values = Rpcs3LibraryService.parseParamSfoBytes(await sfo.readAsBytes());',
    '''        // ignore: invalid_use_of_visible_for_testing_member\n        final values = Rpcs3LibraryService.parseParamSfoBytes(\n          await sfo.readAsBytes(),\n        );''',
)

replace_once(
    resolver,
    "    if (canonicalName.isEmpty) canonicalName = sfoTitle ?? '';",
    "    if (canonicalName.isEmpty) {\n      canonicalName = sfoTitle ?? '';\n    }",
)
replace_once(
    resolver,
    '    if (canonicalName.isEmpty) canonicalName = saveTitleId ?? location.saveDirectory;',
    '    if (canonicalName.isEmpty) {\n      canonicalName = saveTitleId ?? location.saveDirectory;\n    }',
)

print('RPCS3 NeoSync analyzer fixes applied')
