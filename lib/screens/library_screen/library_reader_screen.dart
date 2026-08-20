import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../l10n/app_locale.dart';
import '../../services/gamepad/gamepad_navigation_manager.dart';
import '../../themes/chrome_surface.dart';
import '../../utils/gamepad_nav.dart';
import '../../widgets/neo_glass.dart';

/// Full-screen Library reader using the same navigation contract as the game
/// manual reader: it owns a modal gamepad layer, so B always closes it.
///
/// Reading position, zoom and pan can be stored as a local bookmark. Page-based
/// books are fitted to the available landscape viewport at 100% and may be
/// pinched down below 100% when the reader wants to see more of the page.
class LibraryReaderScreen extends StatefulWidget {
  const LibraryReaderScreen({
    super.key,
    required this.title,
    this.subtitle = '',
    this.coverUrl,
    this.text,
    this.pages = const [],
    this.imageHeaders,
    this.bookmarkId,
  });

  final String title;
  final String subtitle;
  final String? coverUrl;
  final String? text;
  final List<String> pages;
  final Map<String, String>? imageHeaders;

  /// Stable identity used to persist a bookmark.
  /// When omitted, the reader derives one from the visible title/subtitle and content type.
  final String? bookmarkId;

  bool get hasPages => pages.isNotEmpty;

  @override
  State<LibraryReaderScreen> createState() => _LibraryReaderScreenState();
}

class _LibraryReaderScreenState extends State<LibraryReaderScreen> {
  late final GamepadNavigation _gamepadNav;
  final TransformationController _transformationController =
      TransformationController();
  final ScrollController _scrollController = ScrollController();
  late final String _layerId;

  bool _hasBookmark = false;
  double? _pendingBookmarkProgress;

  String get _bookmarkKey {
    final identity = widget.bookmarkId?.trim().isNotEmpty == true
        ? widget.bookmarkId!.trim()
        : '${widget.hasPages ? 'pages' : 'text'}|${widget.title}|${widget.subtitle}';
    final digest = sha1.convert(utf8.encode(identity));
    return 'library_reader_bookmark_$digest';
  }

  bool get _isFrench =>
      mounted && Localizations.localeOf(context).languageCode == 'fr';

  @override
  void initState() {
    super.initState();
    _layerId = 'library_reader_${identityHashCode(this)}';
    _gamepadNav = GamepadNavigation(
      onBack: _close,
      onFavorite: () => _saveBookmark(),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
      _restoreBookmark();
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(_layerId);
    _gamepadNav.dispose();
    _transformationController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _close() {
    if (mounted) Navigator.of(context).pop();
  }

  void _fitToScreen() {
    _transformationController.value = Matrix4.identity();
  }

  Future<void> _saveBookmark() async {
    final maxScrollExtent = _scrollController.hasClients
        ? _scrollController.position.maxScrollExtent
        : 0.0;
    final progress = _scrollController.hasClients && maxScrollExtent > 0
        ? (_scrollController.offset / maxScrollExtent).clamp(0.0, 1.0)
        : 0.0;

    final payload = <String, dynamic>{
      'progress': progress,
      'matrix': _transformationController.value.storage.toList(),
      'savedAt': DateTime.now().toIso8601String(),
    };

    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_bookmarkKey, jsonEncode(payload));
    if (!mounted) return;
    setState(() => _hasBookmark = true);
    _showReaderMessage(
      _isFrench ? 'Marque-page enregistré.' : 'Bookmark saved.',
    );
  }

  Future<void> _restoreBookmark() async {
    final preferences = await SharedPreferences.getInstance();
    final raw = preferences.getString(_bookmarkKey);
    if (!mounted || raw == null || raw.trim().isEmpty) return;

    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;

      final matrixValue = decoded['matrix'];
      if (matrixValue is List && matrixValue.length == 16) {
        final matrix = matrixValue
            .map((value) => (value as num).toDouble())
            .toList(growable: false);
        _transformationController.value = Matrix4.fromList(matrix);
      }

      final progressValue = decoded['progress'];
      if (progressValue is num) {
        _pendingBookmarkProgress = progressValue.toDouble().clamp(0.0, 1.0);
      }

      setState(() => _hasBookmark = true);
      _scheduleBookmarkRestore();
    } catch (_) {
      // Ignore malformed legacy bookmark data rather than blocking the reader.
    }
  }

  void _scheduleBookmarkRestore() {
    WidgetsBinding.instance.addPostFrameCallback((_) => _applyBookmarkProgress());
    Future<void>.delayed(
      const Duration(milliseconds: 320),
      _applyBookmarkProgress,
    );
    Future<void>.delayed(
      const Duration(milliseconds: 950),
      _applyBookmarkProgress,
    );
  }

  void _applyBookmarkProgress() {
    if (!mounted || _pendingBookmarkProgress == null) return;
    if (!_scrollController.hasClients) return;
    final maxScrollExtent = _scrollController.position.maxScrollExtent;
    if (maxScrollExtent <= 0) return;
    final target = maxScrollExtent * _pendingBookmarkProgress!;
    _scrollController.jumpTo(
      target.clamp(0.0, maxScrollExtent).toDouble(),
    );
    _pendingBookmarkProgress = null;
  }

  void _showReaderMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          duration: const Duration(seconds: 2),
        ),
      );
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
              child: widget.hasPages
                  ? _buildPageReader(theme)
                  : _buildTextReader(theme),
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
    final showZoomHint = MediaQuery.sizeOf(context).width >= 720.r;
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
          if (showZoomHint) ...[
            Text(
              AppLocale.pinchToZoom.getString(context),
              style: TextStyle(
                fontSize: 8.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
            SizedBox(width: 6.r),
          ],
          IconButton(
            tooltip: _isFrench
                ? (_hasBookmark
                      ? 'Mettre à jour le marque-page'
                      : 'Ajouter un marque-page')
                : (_hasBookmark ? 'Update bookmark' : 'Add bookmark'),
            onPressed: _saveBookmark,
            icon: Icon(
              _hasBookmark ? Icons.bookmark_rounded : Icons.bookmark_add_rounded,
              size: 19.r,
              color: _hasBookmark
                  ? theme.colorScheme.primary
                  : theme.colorScheme.onSurface,
            ),
          ),
          IconButton(
            tooltip: _isFrench ? 'Adapter à l’écran' : 'Fit to screen',
            onPressed: _fitToScreen,
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
        minScale: 0.5,
        maxScale: 5.0,
        boundaryMargin: EdgeInsets.all(320.r),
        alignment: Alignment.topCenter,
        panEnabled: true,
        scaleEnabled: true,
        child: SingleChildScrollView(
          controller: _scrollController,
          physics: const BouncingScrollPhysics(),
          padding: EdgeInsets.fromLTRB(28.r, 72.r, 28.r, 42.r),
          child: ConstrainedBox(
            constraints: BoxConstraints(minWidth: constraints.maxWidth - 56.r),
            child: SelectableText(
              widget.text ?? '',
              style: theme.textTheme.bodyLarge?.copyWith(
                height: 1.62,
                fontSize: 16.r.clamp(14.0, 21.0).toDouble(),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPageReader(ThemeData theme) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final availableHeight = constraints.maxHeight - 96.r;
        final pageHeight = availableHeight > 180.r
            ? availableHeight
            : constraints.maxHeight;
        final availableWidth = constraints.maxWidth - 28.r;
        final pageWidth = availableWidth > 180.r
            ? availableWidth
            : constraints.maxWidth;

        return InteractiveViewer(
          transformationController: _transformationController,
          minScale: 0.35,
          maxScale: 5.0,
          boundaryMargin: EdgeInsets.all(360.r),
          alignment: Alignment.topCenter,
          panEnabled: true,
          scaleEnabled: true,
          child: SingleChildScrollView(
            controller: _scrollController,
            physics: const BouncingScrollPhysics(),
            padding: EdgeInsets.fromLTRB(14.r, 68.r, 14.r, 28.r),
            child: Column(
              children: [
                for (var index = 0; index < widget.pages.length; index++) ...[
                  SizedBox(
                    width: pageWidth,
                    height: pageHeight,
                    child: Image.network(
                      widget.pages[index],
                      headers: widget.imageHeaders,
                      fit: BoxFit.contain,
                      loadingBuilder: (context, child, progress) {
                        if (progress == null) return child;
                        return const Center(child: CircularProgressIndicator());
                      },
                      errorBuilder: (_, __, ___) => Center(
                        child: Icon(
                          Symbols.broken_image_rounded,
                          size: 42.r,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                        ),
                      ),
                    ),
                  ),
                  if (index + 1 < widget.pages.length) SizedBox(height: 12.r),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}
