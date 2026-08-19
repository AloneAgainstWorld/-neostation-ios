#!/usr/bin/env python3
from pathlib import Path

p = Path('lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart')
s = p.read_text(encoding='utf-8')

old_group = '''class _OnlineSaveGroup {
  final List<_OnlineSaveGroup> groups;
  final String displayName;'''
new_group = '''class _OnlineSaveGroup {
  final List<NeoSyncFile> files;
  final String displayName;'''
if old_group in s:
    s = s.replace(old_group, new_group, 1)
elif new_group not in s:
    raise SystemExit('Online save group field marker not found')

old_list = '''class OnlineSavesListView extends StatefulWidget {
  final List<NeoSyncFile> files;
  final int selectedIndex;'''
new_list = '''class OnlineSavesListView extends StatefulWidget {
  final List<_OnlineSaveGroup> groups;
  final int selectedIndex;'''
if old_list in s:
    s = s.replace(old_list, new_list, 1)
elif new_list not in s:
    raise SystemExit('Online saves list field marker not found')

s = s.replace('oldWidget.files.length', 'oldWidget.groups.length')

p.write_text(s, encoding='utf-8')
print('NeoSync grouped save UI model fixup applied')
