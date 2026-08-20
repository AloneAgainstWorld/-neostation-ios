#!/usr/bin/env python3
from pathlib import Path

p = Path('lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart')
text = p.read_text(encoding='utf-8')
old = """      } else if (isRpcs3) {\n        label = file.gameName.trim().isNotEmpty\n            ? file.gameName.trim()\n            : _readableGameNameFromV2Path(file.fileName);\n        key = 'rpcs3:${label.toLowerCase()}';\n"""
new = """      } else if (isRpcs3) {\n        // RPCS3 saves are made of many constituent files. The backend's\n        // gameName metadata can vary between those files, so grouping must\n        // use the canonical game segment embedded in the v2 cloud path.\n        final pathGameName = _readableGameNameFromV2Path(file.fileName);\n        label = pathGameName;\n        key = 'rpcs3:${pathGameName.toLowerCase()}';\n"""
if old not in text:
    if new in text:
        print('RPCS3 grouping v2 already applied')
    else:
        raise SystemExit('RPCS3 grouping block not found')
else:
    p.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RPCS3 grouping v2 applied')
