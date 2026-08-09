import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/services/sfx_service.dart';

/// A specialized frosted-glass action button designed for high-density toolbars.
///
/// Supports complex state management including visual feedback for gamepad focus,
/// active/toggle states, and background processing (loading). Implements a
/// glassmorphic aesthetic with dynamic color interpolation.
class GlassButton extends StatelessWidget {
  final FocusNode? focusNode;
  final VoidCallback? onTap;

  /// Primary icon asset path (Image-based).
  final String? iconPath;

  /// Primary vector icon (IconData-based).
  final IconData? iconData;
  final Color? iconColor;
  final String label;
  final bool isEnabled;
  final bool isLoading;

  /// Indicates if the button represents a toggled 'active' state (e.g. Favorite: true).
  final bool isActive;

  /// Optional secondary iconography for combo-actions or status indicators.
  final String? secondaryIconPath;

  const GlassButton({
    super.key,
    this.focusNode,
    this.onTap,
    this.iconPath,
    this.iconData,
    this.iconColor,
    required this.label,
    this.isEnabled = true,
    this.isLoading = false,
    this.isActive = false,
    this.secondaryIconPath,
  });

  @override
  Widget build(BuildContext context) {
    return Builder(
      builder: (context) {
        final isFocused = Focus.of(context).hasFocus;
        final theme = Theme.of(context);

        return AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          height: 40.r,
          decoration: BoxDecoration(
            color: isEnabled
                ? (isActive
                      ? theme.colorScheme.surface
                      : (isFocused
                            ? Colors.white.withValues(alpha: 0.3)
                            : theme.colorScheme.surface))
                : theme.colorScheme.surface.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(8.r),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.25),
                blurRadius: 2.r,
                offset: Offset(2.0.r, 2.0.r),
              ),
            ],
          ),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              canRequestFocus: false,
              focusColor: Colors.transparent,
              hoverColor: Colors.transparent,
              highlightColor: Colors.transparent,
              splashColor: Colors.white.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(12.r),
              onTap: isEnabled
                  ? () {
                      SfxService().playNavSound();
                      onTap?.call();
                    }
                  : null,
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: 6.r),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // State A: Async operation in progress.
                    if (isLoading)
                      SizedBox(
                        width: 16.r,
                        height: 16.r,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          color: theme.colorScheme.onSurface,
                        ),
                      )
                    else
                      // State B: Idle/Active with hybrid iconography.
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          if (iconData != null)
                            Icon(
                              iconData,
                              color: iconColor ?? theme.colorScheme.onSurface,
                              size: 16.r,
                            ),
                          if (iconPath != null)
                            Image.asset(
                              iconPath!,
                              width: 16.r,
                              height: 16.r,
                              color: isFocused
                                  ? Colors.white
                                  : theme.colorScheme.onSurface,
                            ),
                          if (secondaryIconPath != null) ...[
                            SizedBox(width: 4.r),
                            Image.asset(
                              secondaryIconPath!,
                              width: 16.r,
                              height: 16.r,
                              color: theme.colorScheme.onSurface,
                            ),
                          ],
                        ],
                      ),
                    SizedBox(height: 2.r),
                    Text(
                      label.toUpperCase(),
                      style: TextStyle(
                        color: isEnabled
                            ? (isFocused
                                  ? Colors.white
                                  : theme.colorScheme.onSurface)
                            : theme.colorScheme.onSurface.withValues(
                                alpha: 0.5,
                              ),
                        fontSize: 8.r,
                        fontWeight: isFocused
                            ? FontWeight.w900
                            : FontWeight.bold,
                        letterSpacing: 0.5,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
