#!/usr/bin/env python3
from pathlib import Path

p = Path('lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart')
text = p.read_text(encoding='utf-8')

old = """      final isArmsx2Save = lowerPath.startsWith('v2/saves/ps2/armsx2/');\n      final isArmsx2State = lowerPath.startsWith('v2/states/ps2/armsx2/');\n\n      String key;\n      String label;\n      if (isMeloNX) {\n        label = file.gameName.trim().isNotEmpty\n            ? file.gameName.trim()\n            : _readableGameNameFromV2Path(file.fileName);\n        key = 'melonx:${label.toLowerCase()}';\n      } else if (isArmsx2Save || isArmsx2State) {\n"""
new = """      final isArmsx2Save = lowerPath.startsWith('v2/saves/ps2/armsx2/');\n      final isArmsx2State = lowerPath.startsWith('v2/states/ps2/armsx2/');\n      final isRpcs3 =\n          lowerPath.startsWith('v2/saves/ps3/rpcs3/game/') ||\n          lowerPath.startsWith('v2/states/ps3/rpcs3/game/');\n\n      String key;\n      String label;\n      if (isMeloNX) {\n        label = file.gameName.trim().isNotEmpty\n            ? file.gameName.trim()\n            : _readableGameNameFromV2Path(file.fileName);\n        key = 'melonx:${label.toLowerCase()}';\n      } else if (isRpcs3) {\n        label = file.gameName.trim().isNotEmpty\n            ? file.gameName.trim()\n            : _readableGameNameFromV2Path(file.fileName);\n        key = 'rpcs3:${label.toLowerCase()}';\n      } else if (isArmsx2Save || isArmsx2State) {\n"""

if new in text:
    print('RPCS3 grouping already applied')
elif old not in text:
    raise SystemExit('RPCS3 grouping marker not found')
else:
    p.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RPCS3 grouping applied')
