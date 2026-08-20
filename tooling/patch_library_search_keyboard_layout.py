from pathlib import Path

p = Path('lib/screens/library_screen/library_screen.dart')
s = p.read_text(encoding='utf-8')

old = '''          return Dialog(
            backgroundColor: Colors.transparent,
            insetPadding: EdgeInsets.symmetric(horizontal: 34.r, vertical: 24.r),
            child: NeoGlass(
              role: GlassSurfaceRole.card,
              borderRadius: BorderRadius.circular(18.r),
              enableBackdropBlur: true,
              showSheen: false,
              padding: EdgeInsets.fromLTRB(22.r, 20.r, 22.r, 18.r),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: 720.r),
                child: Column(
'''

new = '''          final media = MediaQuery.of(dialogContext);
          final keyboardInset = media.viewInsets.bottom;
          final keyboardVisible = keyboardInset > 0;
          final horizontalInset = 34.r;
          final topInset = keyboardVisible ? 8.r : 24.r;
          final bottomInset = keyboardVisible ? keyboardInset + 10.r : 24.r;
          final availableHeight =
              (media.size.height - topInset - bottomInset)
                  .clamp(180.0, media.size.height)
                  .toDouble();

          return AnimatedPadding(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutCubic,
            padding: EdgeInsets.fromLTRB(
              horizontalInset,
              topInset,
              horizontalInset,
              bottomInset,
            ),
            child: Align(
              alignment: Alignment.topCenter,
              child: Dialog(
                backgroundColor: Colors.transparent,
                insetPadding: EdgeInsets.zero,
                child: NeoGlass(
                  role: GlassSurfaceRole.card,
                  borderRadius: BorderRadius.circular(18.r),
                  enableBackdropBlur: true,
                  showSheen: false,
                  padding: EdgeInsets.fromLTRB(22.r, 16.r, 22.r, 14.r),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      maxWidth: 720.r,
                      maxHeight: availableHeight,
                    ),
                    child: SingleChildScrollView(
                      keyboardDismissBehavior:
                          ScrollViewKeyboardDismissBehavior.manual,
                      physics: const ClampingScrollPhysics(),
                      child: Column(
'''

if old not in s:
    raise SystemExit('search dialog start anchor not found')
s = s.replace(old, new, 1)

old_end = '''                  ],
                ),
              ),
            ),
          );
'''
new_end = '''                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          );
'''
start = s.index('          final media = MediaQuery.of(dialogContext);')
end = s.index(old_end, start)
s = s[:end] + new_end + s[end + len(old_end):]

old_field = '''                      textInputAction: TextInputAction.search,
                      textAlignVertical: TextAlignVertical.center,
'''
new_field = '''                      textInputAction: TextInputAction.search,
                      textAlignVertical: TextAlignVertical.center,
                      scrollPadding: EdgeInsets.only(
                        bottom: keyboardVisible ? keyboardInset + 18.r : 18.r,
                      ),
'''
if old_field not in s:
    raise SystemExit('search textfield anchor not found')
s = s.replace(old_field, new_field, 1)

p.write_text(s, encoding='utf-8')
