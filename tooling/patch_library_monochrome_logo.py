from pathlib import Path

path = Path('lib/screens/library_screen/library_screen.dart')
source = path.read_text(encoding='utf-8')
old = """        SizedBox(\n          width: 58.r,\n          height: 58.r,\n          child: Padding(\n            padding: EdgeInsets.all(2.r),\n            child: Image.asset(\n              'assets/images/icons/library-manga-clean.webp',\n              fit: BoxFit.contain,\n              alignment: Alignment.center,\n              filterQuality: FilterQuality.high,\n            ),\n          ),\n        ),\n"""
new = """        SizedBox(\n          width: 58.r,\n          height: 58.r,\n          child: Center(\n            child: Icon(\n              Symbols.menu_book_rounded,\n              size: 44.r,\n              color: theme.colorScheme.onSurface,\n            ),\n          ),\n        ),\n"""
if old not in source:
    raise SystemExit('Library artwork block not found; refusing unsafe patch')
path.write_text(source.replace(old, new, 1), encoding='utf-8')
print('Replaced Library artwork with monochrome book icon')

# Explicit trigger after workflow registration.
