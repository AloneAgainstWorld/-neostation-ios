import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../l10n/app_locale.dart';
import '../../services/gamepad/gamepad_navigation_manager.dart';
import '../../themes/chrome_surface.dart';
import '../../utils/gamepad_nav.dart';
import '../../widgets/neo_glass.dart';

/// Full-screen Library reader using the same navigation contract as the game
/// manual reader: it owns a modal gamepad layer, so B always closes it.
/// The reading surface is wrapped in InteractiveViewer for touch pinch zoom.
class LibraryReaderScreen extends StatefulWidget {
  const LibraryReaderScreen({
    super.key,
    required this.title,
    this.subtitle = '',
    this.coverUrl,
    this.text,
    this.pages = const [],
  });

  final String title;
  final String subtitle;
  final String? coverUrl;
  final String? text;
  final List<String> pages;

  bool get hasPages => pages.isNotEmpty;

  @override
  State<LibraryReaderScreen> createState() => _LibraryReaderScreenState();
}

class _LibraryReaderScreenState extends State<LibraryReaderScreen> {
  late final GamepadNavigation _gamepadNav;
  final TransformationController _transformationController =
      TransformationController();
  late final String _layerId;

  @override
  void initState() {
    super.initState();
    _layerId = 'library_reader_${identityHashCode(this)}';
    _gamepadNav = GamepadNavigation(onBack: _close);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(_layerId);
    _gamepadNav.dispose();
    _transformationController.dispose();
    super.dispose();
  }

  void _close() {
    if (mounted) Navigator.of(context).pop();
  }

  void _resetZoom() {
    _transformationController.value = Matrix4.identity();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: widget.hasPages ? _buildPageReader(theme) : _buildTextReader(theme),
            ),
            Positioned(
              left: 12.r,
              right: 12.r,
              top: 8.r,
              child: _buildChrome(theme),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChrome(ThemeData theme) {
    return NeoGlass(
      role: GlassSurfaceRole.chrome,
      borderRadius: BorderRadius.circular(12.r),
      padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 7.r),
      child: Row(
        children: [
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: _close,
              borderRadius: BorderRadius.circular(8.r),
              child: Padding(
                padding: EdgeInsets.all(4.r),
                child: Icon(
                  Symbols.arrow_back_rounded,
                  size: 18.r,
                  color: theme.colorScheme.onSurface,
                ),
              ),
            ),
          ),
          SizedBox(width: 8.r),
          if (widget.coverUrl != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(5.r),
              child: SizedBox(
                width: 28.r,
                height: 38.r,
                child: Image.network(
                  widget.coverUrl!,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
            ),
            SizedBox(width: 8.r),
          ] else ...[
            Icon(
              Symbols.menu_book_rounded,
              size: 18.r,
              color: theme.colorScheme.primary,
            ),
            SizedBox(width: 7.r),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  widget.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 11.r,
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.onSurface,
                  ),
                ),
                if (widget.subtitle.isNotEmpty)
                  Text(
                    widget.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 8.5.r,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
                    ),
                  ),
              ],
            ),
          ),
          Text(
            AppLocale.pinchToZoom.getString(context),
            style: TextStyle(
              fontSize: 8.r,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
            ),
          ),
          SizedBox(width: 8.r),
          IconButton(
            tooltip: 'Reset zoom',
            onPressed: _resetZoom,
            icon: Icon(Symbols.fit_screen_rounded, size: 18.r),
          ),
        ],
      ),
    );
  }

  Widget _buildTextReader(ThemeData theme) {
    return LayoutBuilder(
      builder: (context, constraints) => InteractiveViewer(
        transformationController: _transformationController,
        minScale: 1.0,
        maxScale: 4.0,
        boundaryMargin: EdgeInsets.all(180.r),
        panEnabled: true,
        scaleEnabled: true,
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: EdgeInsets.fromLTRB(28.r, 72.r, 28.r, 42.r),
          child: ConstrainedBox(
            constraints: BoxConstraints(minWidth: constraints.maxWidth - 56.r),
            child: SelectableText(
              widget.text ?? '',
              style: theme.textTheme.bodyLarge?.copyWith(
                height: 1.62,
                fontSize: 16.r.clamp(14.0, 21.0),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPageReader(ThemeData theme) {
    return InteractiveViewer(
      transformationController: _transformationController,
      minScale: 1.0,
      maxScale: 4.0,
      boundaryMargin: EdgeInsets.all(180.r),
      panEnabled: true,
      scaleEnabled: true,
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: EdgeInsets.fromLTRB(16.r, 68.r, 16.r, 32.r),
        child: Column(
          children: [
            for (var index = 0; index < widget.pages.length; index++) ...[
              Image.network(
                widget.pages[index],
                fit: BoxFit.contain,
                loadingBuilder: (context, child, progress) {
                  if (progress == null) return child;
                  return SizedBox(
                    height: 300.r,
                    child: const Center(child: CircularProgressIndicator()),
                  );
                },
                errorBuilder: (_, __, ___) => SizedBox(
                  height: 160.r,
                  child: const Center(child: Icon(Symbols.broken_image_rounded)),
                ),
              ),
              if (index + 1 < widget.pages.length) SizedBox(height: 10.r),
            ],
          ],
        ),
      ),
    );
  }
}
