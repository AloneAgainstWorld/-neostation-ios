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


upload = 'lib/providers/neosync/neosync_upload.dart'
replace_once(
    upload,
    '''  Future<bool> _uploadArmsx2File(File file, String root) async {\n    final resolved = _resolveArmsx2FileForCloud(file, root);''',
    '''  Future<bool> _uploadArmsx2File(\n    File file,\n    String root, {\n    GameModel? preferredGame,\n  }) async {\n    final resolved = _resolveArmsx2FileForCloud(file, root);''',
)

replace_once(
    upload,
    '''    final isMemoryCard =\n        resolved.category == 'memcards' &&\n        file.path.toLowerCase().endsWith('.ps2');\n    File uploadFile = file;''',
    '''    final preferredGameName = preferredGame?.name.trim();\n    final displayGameName =\n        preferredGameName != null && preferredGameName.isNotEmpty\n        ? '$preferredGameName — ${resolved.isState ? 'Save State' : 'Memory Card'}'\n        : resolved.gameName;\n\n    final isMemoryCard =\n        resolved.category == 'memcards' &&\n        file.path.toLowerCase().endsWith('.ps2');\n    File uploadFile = file;''',
)

replace_once(
    upload,
    '''        uploadFile,\n        resolved.gameName,\n        customFilename: resolved.cloudPath,''',
    '''        uploadFile,\n        displayGameName,\n        customFilename: resolved.cloudPath,''',
)
replace_once(
    upload,
    '''        _processedItems.add('NeoSync: ${resolved.gameName}');\n        return true;''',
    '''        _processedItems.add('NeoSync: $displayGameName');\n        return true;''',
)
replace_once(
    upload,
    '''      _processedItems.add(\n        'Failed to upload ${resolved.gameName}: $errorMessage',\n      );''',
    '''      _processedItems.add(\n        'Failed to upload $displayGameName: $errorMessage',\n      );''',
)

core = 'lib/providers/neosync/neosync_core.dart'
replace_once(
    core,
    '''        return await _uploadArmsx2File(file, armsx2Root);''',
    '''        return await _uploadArmsx2File(\n          file,\n          armsx2Root,\n          preferredGame: game,\n        );''',
)

print('ARMSX2 game label patch applied')
