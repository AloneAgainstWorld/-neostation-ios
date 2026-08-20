import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/neo_glass.dart';

/// First-stage Library hub.
///
/// The Library is intentionally content-agnostic: local books/manga and future
/// external add-ons live under the same top-level tab without mixing with the
/// game database. Add-on execution/fetching is introduced in a later stage.
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  static LibraryScreenState? _currentState;

  static bool navigateLeft() => _currentState?._moveSelection(-1) ?? false;
  static bool navigateRight() => _currentState?._moveSelection(1) ?? false;
  static bool navigateUp() => false;
  static bool navigateDown() => false;
  static void selectCurrent() => _currentState?._activateSelection();

  @override
  State<LibraryScreen> createState() => LibraryScreenState();
}

class LibraryScreenState extends State<LibraryScreen> {
  int _selectedIndex = 0;

  @override
  void initState() {
    super.initState();
    LibraryScreen._currentState = this;
  }

  @override
  void dispose() {
    if (identical(LibraryScreen._currentState, this)) {
      LibraryScreen._currentState = null;
    }
    super.dispose();
  }

  bool _moveSelection(int delta) {
    final next = (_selectedIndex + delta).clamp(0, 1).toInt();
    if (next == _selectedIndex) return false;
    setState(() => _selectedIndex = next);
    return true;
  }

  void _activateSelection() {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(AppLocale.libraryNextStep.getString(context)),
          duration: const Duration(seconds: 2),
        ),
      );
  }

  void _tapCard(int index) {
    SfxService().playNavSound();
    setState(() => _selectedIndex = index);
    _activateSelection();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(24.r, 54.r, 24.r, 18.r),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(12.r),
                  child: Image.asset(
                    'assets/images/icons/library-manga.webp',
                    width: 54.r,
                    height: 54.r,
                    fit: BoxFit.cover,
                  ),
                ),
                SizedBox(width: 14.r),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        AppLocale.library.getString(context),
                        style: theme.textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 3.r),
                      Text(
                        AppLocale.libraryIntro.getString(context),
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(
                            alpha: 0.68,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            SizedBox(height: 22.r),
            Row(
              children: [
                Expanded(
                  child: _LibraryEntryCard(
                    selected: _selectedIndex == 0,
                    icon: Symbols.extension_rounded,
                    title: AppLocale.libraryAddons.getString(context),
                    subtitle: AppLocale.libraryAddonsSubtitle.getString(
                      context,
                    ),
                    onTap: () => _tapCard(0),
                  ),
                ),
                SizedBox(width: 14.r),
                Expanded(
                  child: _LibraryEntryCard(
                    selected: _selectedIndex == 1,
                    icon: Symbols.folder_open_rounded,
                    title: AppLocale.libraryLocal.getString(context),
                    subtitle: AppLocale.libraryLocalSubtitle.getString(context),
                    onTap: () => _tapCard(1),
                  ),
                ),
              ],
            ),
            SizedBox(height: 18.r),
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Symbols.collections_bookmark_rounded,
                      size: 38.r,
                      color: theme.colorScheme.onSurface.withValues(
                        alpha: 0.35,
                      ),
                    ),
                    SizedBox(height: 10.r),
                    Text(
                      AppLocale.libraryEmptyTitle.getString(context),
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: 4.r),
                    Text(
                      AppLocale.libraryEmptySubtitle.getString(context),
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.55,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LibraryEntryCard extends StatelessWidget {
  const _LibraryEntryCard({
    required this.selected,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(12.r);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: selected ? theme.colorScheme.primary : Colors.transparent,
          width: selected ? 2.r : 0,
        ),
        boxShadow: selected
            ? [
                BoxShadow(
                  color: theme.colorScheme.primary.withValues(alpha: 0.18),
                  blurRadius: 12.r,
                  spreadRadius: 1.r,
                ),
              ]
            : null,
      ),
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: radius,
        enableBackdropBlur: false,
        showSheen: true,
        padding: EdgeInsets.all(14.r),
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: Row(
            children: [
              Container(
                width: 42.r,
                height: 42.r,
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(10.r),
                ),
                child: Icon(icon, size: 24.r, color: theme.colorScheme.primary),
              ),
              SizedBox(width: 12.r),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 3.r),
                    Text(
                      subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.62,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: 6.r),
              Icon(
                Symbols.chevron_right_rounded,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
