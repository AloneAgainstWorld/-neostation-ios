from pathlib import Path

path = Path('lib/widgets/setup_wizard.dart')
text = path.read_text(encoding='utf-8')

import_anchor = "import 'package:neostation/l10n/app_locale.dart';\n"
locale_import = "import 'package:neostation/l10n/ios_setup_locale.dart';\n"
if locale_import not in text:
    if import_anchor not in text:
        raise SystemExit('AppLocale import anchor not found')
    text = text.replace(import_anchor, import_anchor + locale_import, 1)

old_ios_copy = """    if (Platform.isIOS) {
      icon = Symbols.sports_esports_rounded;
      title = 'Link RetroArch';
      description = _selectedFolder != null
          ? 'Linked and synced.\\n\\n$_selectedFolder'
          : 'Link RetroArch\\'s own folder so NeoStation can see your '
                'games and launch them directly with one tap.';
    } else {
"""
new_ios_copy = """    if (Platform.isIOS) {
      icon = Symbols.sports_esports_rounded;
      title = IosSetupLocale.linkTitle(context);
      description = _selectedFolder != null
          ? '${IosSetupLocale.linked(context)}\\n\\n$_selectedFolder'
          : IosSetupLocale.linkDescription(context);
    } else {
"""
if old_ios_copy not in text:
    raise SystemExit('iOS RetroArch copy block not found')
text = text.replace(old_ios_copy, new_ios_copy, 1)

old_folder_button = """    if (_currentStep == _stepFolder) {
      return Platform.isIOS
          ? (_selectedFolder != null ? 'Continue' : 'Link RetroArch')
          : AppLocale.selectFolder.getString(context);
    }
"""
new_folder_button = """    if (_currentStep == _stepFolder) {
      return Platform.isIOS
          ? (_selectedFolder != null
                ? IosSetupLocale.continueLabel(context)
                : IosSetupLocale.linkTitle(context))
          : AppLocale.selectFolder.getString(context);
    }
"""
if old_folder_button not in text:
    raise SystemExit('iOS folder action label block not found')
text = text.replace(old_folder_button, new_folder_button, 1)

nav_start = text.find("""        return Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            if (showSkip)
""")
if nav_start < 0:
    raise SystemExit('Navigation row start not found')
nav_end_marker = """          ],
        );
      },
    );
  }

  String _getButtonText() {
"""
nav_end = text.find(nav_end_marker, nav_start)
if nav_end < 0:
    raise SystemExit('Navigation row end not found')
nav_end += len("""          ],
        );
""")

new_nav = """        return Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // Reserve a stable half of the navigation row for the optional
            // secondary action. This keeps long translations from stealing
            // width from the primary button.
            Expanded(
              child: showSkip
                  ? Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton(
                        onPressed: () => _handleSkip(),
                        style: TextButton.styleFrom(
                          padding: EdgeInsets.symmetric(
                            horizontal: 16.r,
                            vertical: 8.r,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Image.asset(
                              'assets/images/gamepad/Xbox_B_button.png',
                              width: 20.r,
                              height: 20.r,
                              color: theme.colorScheme.onSurface.withValues(
                                alpha: 0.6,
                              ),
                            ),
                            SizedBox(width: 8.r),
                            Flexible(
                              child: Text(
                                AppLocale.skipForNow.getString(context),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 12.r,
                                  color: theme.colorScheme.onSurface.withValues(
                                    alpha: 0.6,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
            SizedBox(width: 16.r),

            // Keep the original large-button treatment. The primary action
            // owns the other half of the row, so translated labels stay at a
            // normal readable size instead of being scaled down to fit.
            Expanded(
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
                  minimumSize: Size(0, 52.r),
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
                    : Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Image.asset(
                            'assets/images/gamepad/Xbox_A_button.png',
                            width: 20.r,
                            height: 20.r,
                            color: theme.colorScheme.onPrimary,
                          ),
                          SizedBox(width: 8.r),
                          Flexible(
                            child: Text(
                              _getButtonText(),
                              maxLines: 2,
                              textAlign: TextAlign.center,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 14.r,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
              ),
            ),
          ],
        );
"""
text = text[:nav_start] + new_nav + text[nav_end:]

# Guard against the previous tiny-text workaround reappearing in this block.
if 'FittedBox(' in text[text.find('Widget _buildNavigationButtons'):text.find('String _getButtonText')]:
    raise SystemExit('FittedBox still present in navigation block')

path.write_text(text, encoding='utf-8')
