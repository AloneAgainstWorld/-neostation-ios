import 'dart:async';

import 'package:flutter/material.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/home_music_service.dart';
import 'package:neostation/widgets/shimmering_logo.dart';
import 'my_systems_section/my_systems_grid.dart';
import 'my_systems_section/initial_setup_widget.dart';
import 'custom_main_menu_background.dart';
import 'fork_first_run_onboarding.dart';

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
  static const _forkOnboardingKey = 'neostation_fork_onboarding_v1';

  DateTime? _splashShownAt;
  Timer? _releaseTimer;
  bool? _lastHomeMusicActive;

  bool _onboardingCheckStarted = false;
  bool _forkOnboardingResolved = false;
  bool _showForkOnboarding = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_onboardingCheckStarted) {
      _onboardingCheckStarted = true;
      unawaited(_resolveForkOnboarding());
    }
  }

  @override
  void dispose() {
    _releaseTimer?.cancel();
    unawaited(HomeMusicService().setMainMenuActive(false));
    super.dispose();
  }

  /// Decides whether this installation should see the fork introduction.
  ///
  /// Existing NeoStation users upgrading to this fork are silently marked as
  /// migrated when they already have setup history, so the new welcome flow is
  /// reserved for genuinely fresh installs rather than interrupting upgrades.
  Future<void> _resolveForkOnboarding() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final alreadyCompleted = prefs.getBool(_forkOnboardingKey) ?? false;

      if (alreadyCompleted) {
        if (mounted) {
          setState(() {
            _forkOnboardingResolved = true;
            _showForkOnboarding = false;
          });
        }
        return;
      }

      if (!mounted) return;
      final configProvider = context.read<SqliteConfigProvider>();
      final existingInstall =
          configProvider.config.setupCompleted ||
          configProvider.hasDetectedSystems ||
          configProvider.config.lastScan != null;

      if (existingInstall) {
        await prefs.setBool(_forkOnboardingKey, true);
      }

      if (mounted) {
        setState(() {
          _forkOnboardingResolved = true;
          _showForkOnboarding = !existingInstall;
        });
      }
    } catch (_) {
      // A preferences failure should never trap the application before its
      // normal setup. Skip the optional introduction for this launch.
      if (mounted) {
        setState(() {
          _forkOnboardingResolved = true;
          _showForkOnboarding = false;
        });
      }
    }
  }

  Future<void> _completeForkOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_forkOnboardingKey, true);
    if (!mounted) return;
    setState(() => _showForkOnboarding = false);
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

  /// Keeps audio side effects outside build while still following route
  /// visibility. A pushed game library leaves this widget mounted underneath,
  /// so checking [ModalRoute.isCurrent] is what prevents ambience from leaking
  /// beyond the main console-selection screen.
  void _syncHomeMusic(bool active) {
    if (_lastHomeMusicActive == active) return;
    _lastHomeMusicActive = active;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted && active) return;
      unawaited(HomeMusicService().setMainMenuActive(active));
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<SqliteConfigProvider, ThemeProvider>(
      builder: (context, configProvider, themeProvider, child) {
        final isLoading = configProvider.isLoading || configProvider.isScanning;
        final normalSplash = isLoading || _holdSplash(isLoading);
        final showSplash = normalSplash || !_forkOnboardingResolved;
        final showForkOnboarding =
            !showSplash && _forkOnboardingResolved && _showForkOnboarding;

        final showInitialSetup =
            !showSplash &&
            !showForkOnboarding &&
            !configProvider.hasDetectedSystems &&
            configProvider.scanCompleted;

        final showContent =
            !showSplash &&
            !showForkOnboarding &&
            configProvider.scanCompleted &&
            !showInitialSetup;

        final routeIsCurrent = ModalRoute.of(context)?.isCurrent ?? true;
        _syncHomeMusic(showContent && routeIsCurrent);

        final Widget phase;
        if (showSplash) {
          phase = KeyedSubtree(
            key: const ValueKey('splash'),
            child: _buildSplash(context, configProvider),
          );
        } else if (showForkOnboarding) {
          phase = KeyedSubtree(
            key: const ValueKey('fork_onboarding'),
            child: ForkFirstRunOnboarding(
              onFinished: _completeForkOnboarding,
            ),
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
        // Splash/setup/onboarding screens and pushed playlists remain unchanged.
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
