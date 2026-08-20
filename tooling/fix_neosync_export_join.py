from pathlib import Path
p = Path('lib/screens/neo_sync_screen/login_screen/neo_sync_content.dart')
s = p.read_text(encoding='utf-8')
old1 = "var candidate = File(p.join(root.path, ...directorySegments, baseName));"
new1 = "var candidate = File(p.joinAll(<String>[root.path, ...directorySegments, baseName]));"
old2 = "p.join(root.path, ...directorySegments, '$stem-$suffix$extension'),"
new2 = "p.joinAll(<String>[root.path, ...directorySegments, '$stem-$suffix$extension']),"
if old1 not in s or old2 not in s:
    raise SystemExit('NeoSync export join anchors not found')
s = s.replace(old1, new1, 1).replace(old2, new2, 1)
p.write_text(s, encoding='utf-8')
