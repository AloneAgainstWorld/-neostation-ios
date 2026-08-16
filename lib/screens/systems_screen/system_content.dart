import 'dart:async';

import 'package:flutter/material.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:provider/provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/widgets/shimmering_logo.dart';
import 'my_systems_section/my_systems_grid.dart';
import 'my_systems_section/initial_setup_widget.dart';
import 'custom_main_menu_background.dart';

/// Orchestrator for the 'Systems' tab content.
///
/// The optional user-selected custom background is deliberately rendered only
/// behind the primary systems grid/carousel. Game playlists are pushed as new
/// routes and therefore keep their existing backgrounds unchanged.
class SystemContent extends StatefulWidget {
  const SystemContent({super.key, this.selectedIndex = 0, this.onCardTapped});

  final int selectedIndex;
  final Function(int index)? onCardTapped;

  @override
  State<SystemContent> createState() => _SystemContentState();
}

class _SystemContentState extends State<SystemContent> {
  static const _minSplashDuration = Duration(milliseconds: 2500);

  DateTime? _splashShownAt;
  Timer? _releaseTimer;

  @override
  void dispose() {
    _releaseTimer?.cancel();
    super.dispose();
  }

  bool _holdSplash(bool isLoading) {
    if (isLoading) {
      _splashShownAt ??= DateTime.now();
      _releaseTimer?.cancel();
      _releaseTimer = null;
      return false;
    }
    final shownAt = _splashShownAt;
    if (shownAt == null) return false;

    final remaining = _minSplashDuration - DateTime.now().difference(shownAt);
    if (remaining <= Duration.zero) {
      _splashShownAt = null;
      return false;
    }
    _releaseTimer ??= Timer(remaining, () {
      if (mounted) setState(() => _splashShownAt = null);
    });
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<SqliteConfigProvider, ThemeProvider>(
      builder: (context, configProvider, themeProvider, child) {
        final isLoading = configProvider.isLoading || configProvider.isScanning;
        final showSplash = isLoading || _holdSplash(isLoading);

        final showInitialSetup =
            !showSplash &&
            !configProvider.hasDetectedSystems &&
            configProvider.scanCompleted;

        final showContent =
            !showSplash && configProvider.scanCompleted && !showInitialSetup;

        final Widget phase;
        if (showSplash) {
          phase = KeyedSubtree(
            key: const ValueKey('splash'),
            child: _buildSplash(context, configProvider),
          );
        } else if (showInitialSetup) {
          phase = KeyedSubtree(
            key: const ValueKey('setup'),
            child: InitialSetupWidget(),
          );
        } else if (showContent) {
          phase = KeyedSubtree(
            key: const ValueKey('content'),
            child: MySystems(
              selectedIndex: widget.selectedIndex,
              onCardTapped: widget.onCardTapped,
            ),
          );
        } else {
          phase = const SizedBox.shrink(key: ValueKey('empty'));
        }

        final content = AnimatedSwitcher(
          duration: const Duration(milliseconds: 400),
          child: phase,
        );

        // Only the actual Systems main menu receives the custom background.
        // Splash/setup screens and pushed playlists remain unchanged.
        final customBackground = showContent
            ? themeProvider.customBackgroundPath
            : null;
        if (customBackground == null) return content;

        return Stack(
          fit: StackFit.expand,
          children: [
            CustomMainMenuBackground(path: customBackground),
            content,
          ],
        );
      },
    );
  }

  Widget _buildSplash(
    BuildContext context,
    SqliteConfigProvider configProvider,
  ) {
    return Stack(
      children: [
        Center(
          child: ShimmeringLogo(
            progress:
                configProvider.isScanning && configProvider.scanProgress > 0
                ? configProvider.scanProgress
                : null,
          ),
        ),
        if (configProvider.isScanning)
          Align(
            alignment: const Alignment(0, 0.55),
            child: Container(
              constraints: const BoxConstraints(maxWidth: 480),
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 220,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(2),
                      child: LinearProgressIndicator(
                        value: configProvider.scanProgress,
                        minHeight: 3,
                        backgroundColor: Theme.of(
                          context,
                        ).colorScheme.onSurface.withValues(alpha: 0.12),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    configProvider.scanStatus.isNotEmpty
                        ? configProvider.scanStatus
                        : AppLocale.scanningSystemsRoms.getString(context),
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      fontSize: 17,
                      color: Theme.of(
                        context,
                      ).colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
