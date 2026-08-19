#!/usr/bin/env python3
from pathlib import Path

p = Path('lib/providers/neosync/neosync_path_resolver.dart')
s = p.read_text(encoding='utf-8')
old = """  bool _isMeloNXTitleId(String value) =>\n      RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(value.trim());"""
new = """  bool _isMeloNXTitleId(String value) {\n    final normalized = value.trim();\n    return normalized.toLowerCase() != '0000000000000000' &&\n        RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(normalized);\n  }"""
if old not in s:
    if new in s:
        print('MeloNX zero-container exclusion already applied')
        raise SystemExit(0)
    raise SystemExit('MeloNX Title ID helper marker not found')
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('MeloNX zero-container exclusion applied')
