from pathlib import Path

p = Path('lib/screens/scraper_screen/new_scraper_options_screen.dart')
s = p.read_text(encoding='utf-8')

old_import = "import 'package:flutter/material.dart';\n"
new_import = "import 'dart:io';\n\nimport 'package:flutter/foundation.dart';\nimport 'package:flutter/material.dart';\n"
if old_import not in s:
    raise SystemExit('material import anchor not found')
s = s.replace(old_import, new_import, 1)

old_build = '''  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      color: Colors
          .transparent, // Transparent to show the shared background shader
      padding: EdgeInsets.only(top: 46.r),
      child: Row(
'''
new_build = '''  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final safePadding = MediaQuery.viewPaddingOf(context);
    // Match Settings: protect ScreenScraper's body from an iPhone notch or
    // Dynamic Island in landscape without moving the shared global header.
    // viewPadding follows whichever side owns the cutout after rotation.
    final iosSafeLeft = !kIsWeb && Platform.isIOS ? safePadding.left : 0.0;
    final iosSafeRight = !kIsWeb && Platform.isIOS ? safePadding.right : 0.0;

    return Container(
      color: Colors
          .transparent, // Transparent to show the shared background shader
      padding: EdgeInsets.fromLTRB(iosSafeLeft, 46.r, iosSafeRight, 0),
      child: Row(
'''
if old_build not in s:
    raise SystemExit('build block anchor not found')
s = s.replace(old_build, new_build, 1)

p.write_text(s, encoding='utf-8')
