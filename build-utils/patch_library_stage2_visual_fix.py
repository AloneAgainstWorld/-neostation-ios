#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:200]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

screen = 'lib/screens/library_screen/library_screen.dart'

# This fork uses the static FilePicker API (same pattern as Theme import).
replace_once(
    screen,
    'final result = await FilePicker.platform.pickFiles(',
    'final result = await FilePicker.pickFiles(',
)

# Preserve the full red/blue Library artwork next to the title. The previous
# square ClipRRect + BoxFit.cover cropped the outer frame on landscape devices
# and made the artwork look distorted.
replace_once(
    screen,
    '''        ClipRRect(\n          borderRadius: BorderRadius.circular(12.r),\n          child: Image.asset(\n            'assets/images/icons/library-manga.webp',\n            width: 54.r,\n            height: 54.r,\n            fit: BoxFit.cover,\n          ),\n        ),''',
    '''        SizedBox(\n          width: 58.r,\n          height: 58.r,\n          child: Padding(\n            padding: EdgeInsets.all(2.r),\n            child: Image.asset(\n              'assets/images/icons/library-manga.webp',\n              fit: BoxFit.contain,\n              alignment: Alignment.center,\n              filterQuality: FilterQuality.high,\n            ),\n          ),\n        ),''',
)

print('Library stage 2 visual/picker fix applied')
