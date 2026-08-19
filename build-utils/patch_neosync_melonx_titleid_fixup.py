#!/usr/bin/env python3
from pathlib import Path

p = Path('lib/providers/neosync/neosync_path_resolver.dart')
s = p.read_text(encoding='utf-8')
old = '''    String? gameName;\n    final preferredTitleId = await _meloNXTitleIdForGame(\n      preferredGame ??\n          GameModel(\n            name: '',\n            realname: '',\n            romname: '',\n            year: '',\n            developer: '',\n            publisher: '',\n            genre: '',\n            players: '',\n            rating: 0,\n          ),\n    );\n    if (preferredGame != null &&\n        preferredTitleId != null &&\n        preferredTitleId.toLowerCase() == location.titleId.toLowerCase()) {\n      gameName = preferredGame.name.trim();\n    }'''
new = '''    String? gameName;\n    String? preferredTitleId;\n    if (preferredGame != null) {\n      preferredTitleId = await _meloNXTitleIdForGame(preferredGame);\n    }\n    if (preferredGame != null &&\n        preferredTitleId != null &&\n        preferredTitleId.toLowerCase() == location.titleId.toLowerCase()) {\n      gameName = preferredGame.name.trim();\n    }'''
if old not in s:
    if new in s:
        print('MeloNX resolver fixup already applied')
        raise SystemExit(0)
    raise SystemExit('MeloNX resolver fixup marker not found')
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('MeloNX resolver fixup applied')
