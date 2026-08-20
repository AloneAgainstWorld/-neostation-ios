#!/usr/bin/env python3
from pathlib import Path

p = Path('lib/screens/library_screen/library_screen.dart')
text = p.read_text(encoding='utf-8')
old = '    final next = (_selectedIndex + delta).clamp(0, 1);'
new = '    final next = (_selectedIndex + delta).clamp(0, 1).toInt();'
if old in text:
    p.write_text(text.replace(old, new, 1), encoding='utf-8')
elif new not in text:
    raise SystemExit('Library selection marker not found')
print('Library hub small fixes applied')
