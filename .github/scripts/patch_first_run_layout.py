from pathlib import Path

path = Path('lib/widgets/setup_wizard.dart')
text = path.read_text(encoding='utf-8')

anchor = """            // Main action button
            ElevatedButton(
"""
start = text.find(anchor)
if start < 0:
    raise SystemExit('Main action button anchor not found')

end_marker = """
            ),
          ],
        );
"""
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit('Main action button end marker not found')
end += len("\n            ),")

old_block = text[start:end]
if 'FittedBox(' in old_block or 'Flexible(' in old_block:
    print('Responsive art-pack button patch already present.')
    raise SystemExit(0)

new_block = """            SizedBox(width: 12.r),

            // Main action button. Keep the original visual treatment but let
            // localized labels shrink inside the available width instead of
            // pushing the button beyond the right edge on iPhone/iPad.
            Flexible(
              child: ElevatedButton(
                onPressed:
                    (_isSelectingFolder ||
                        _isImportingEsde ||
                        _isDownloadingArt ||
                        artLoading)
                    ? null
                    : () => _handleMainAction(),
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.primary,
                  foregroundColor: theme.colorScheme.onPrimary,
                  padding: EdgeInsets.symmetric(
                    horizontal: 20.r,
                    vertical: 12.r,
                  ),
                  elevation: 4,
                  shadowColor: theme.colorScheme.primary.withValues(alpha: 0.4),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16.r),
                  ),
                  disabledBackgroundColor: theme.colorScheme.primary.withValues(
                    alpha: 0.3,
                  ),
                ),
                child: (_isSelectingFolder || artLoading)
                    ? SizedBox(
                        width: 20.r,
                        height: 20.r,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.r,
                          valueColor: AlwaysStoppedAnimation<Color>(
                            theme.colorScheme.onPrimary,
                          ),
                        ),
                      )
                    : FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Image.asset(
                              'assets/images/gamepad/Xbox_A_button.png',
                              width: 20.r,
                              height: 20.r,
                              color: theme.colorScheme.onPrimary,
                            ),
                            SizedBox(width: 8.r),
                            Text(
                              _getButtonText(),
                              maxLines: 1,
                              style: TextStyle(
                                fontSize: 14.r,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
              ),
            ),"""

text = text[:start] + new_block + text[end:]
path.write_text(text, encoding='utf-8')
print('Patched SetupWizard primary action button for localized labels.')
