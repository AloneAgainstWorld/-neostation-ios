import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../providers/sqlite_config_provider.dart';
import '../screens/systems_screen/fork_first_run_onboarding.dart';
import 'setup_wizard.dart';
import 'shimmering_logo.dart';

/// Widget that checks the initial configuration and shows the first-run flow if necessary.
class PermissionCheckWrapper extends StatefulWidget {
  final Widget child;

  static const String setupCompletedKey = 'setup_completed_prefs';

  const PermissionCheckWrapper({super.key, required this.child});

  @override
  State<PermissionCheckWrapper> createState() => _PermissionCheckWrapperState();
}

class _PermissionCheckWrapperState extends State<PermissionCheckWrapper> {
  bool _needsSetup = false;
  bool _isChecking = true;
  bool _showForkLanguageGate = false;

  static final _log = LoggerService.instance;

  @override
  void initState() {
    super.initState();

    // Check whether initial configuration is needed.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _checkInitialSetup();
    });
  }

  Future<void> _checkInitialSetup() async {
    try {
      final prefs = await SharedPreferences.getInstance();

      // Fast-path: this flag survives SD-card unavailability and early-launcher
      // boot races. Existing installations must never be interrupted by the
      // new first-run language gate.
      if (prefs.getBool(PermissionCheckWrapper.setupCompletedKey) == true) {
        await prefs.setBool(forkOnboardingCompletedKey, true);
        if (!mounted) return;
        _pushWizardActive(false);
        setState(() {
          _needsSetup = false;
          _showForkLanguageGate = false;
          _isChecking = false;
        });
        return;
      }

      if (!mounted) return;
      final configProvider = Provider.of<SqliteConfigProvider>(
        context,
        listen: false,
      );

      if (!configProvider.initialized) {
        await configProvider.initialize();
      }

      final hasRomFolder = configProvider.config.romFolder?.isNotEmpty == true;
      final setupCompleted = configProvider.config.setupCompleted;

      if (hasRomFolder || setupCompleted) {
        // Backfill both preferences for users upgrading from an older build.
        await prefs.setBool(PermissionCheckWrapper.setupCompletedKey, true);
        await prefs.setBool(forkOnboardingCompletedKey, true);
        if (!mounted) return;
        _pushWizardActive(false);
        setState(() {
          _needsSetup = false;
          _showForkLanguageGate = false;
          _isChecking = false;
        });
        return;
      }

      // Genuinely fresh install. The fork language choice is now the very first
      // interactive screen. If it was already confirmed before an interrupted
      // setup, resume directly in NeoStation's normal SetupWizard instead.
      final languageGateCompleted =
          prefs.getBool(forkOnboardingCompletedKey) ?? false;

      if (!mounted) return;
      _pushWizardActive(true);
      setState(() {
        _needsSetup = true;
        _showForkLanguageGate = !languageGateCompleted;
        _isChecking = false;
      });
    } catch (e) {
      _log.e('Error checking initial setup: $e');
      if (!mounted) return;
      _pushWizardActive(false);
      setState(() {
        _needsSetup = false;
        _showForkLanguageGate = false;
        _isChecking = false;
      });
    }
  }

  /// Mirrors "the wizard is on screen" to the secondary display, which parks
  /// its app dock and launcher while setup runs. Pushed from here — the single
  /// place that decides whether the wizard shows — so a normal boot also clears
  /// a flag left behind by a run that was killed mid-wizard.
  void _pushWizardActive(bool active) {
    if (!mounted) return;
    Provider.of<SqliteConfigProvider>(
      context,
      listen: false,
    ).setSetupWizardActive(active);
  }

  Future<void> _completeForkLanguageGate() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(forkOnboardingCompletedKey, true);
    } catch (e) {
      // A preference write failure must not trap the user before setup. The
      // language itself is already persisted by SqliteConfigProvider.
      _log.w('Could not persist first-run language gate state: $e');
    }

    if (!mounted) return;
    setState(() => _showForkLanguageGate = false);
  }

  void _completeSetup() async {
    final configProvider = Provider.of<SqliteConfigProvider>(
      context,
      listen: false,
    );
    await configProvider.completeSetup();

    // Setup is done — let the secondary display bring in the dock/launcher.
    configProvider.setSetupWizardActive(false);

    // Persist flag to SharedPreferences so the wizard is never shown again
    // even if the SQLite DB is temporarily inaccessible (e.g. SD card not ready).
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(PermissionCheckWrapper.setupCompletedKey, true);
    await prefs.setBool(forkOnboardingCompletedKey, true);

    if (!mounted) return;
    setState(() {
      _needsSetup = false;
      _showForkLanguageGate = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isChecking) {
      // Show loading while checking — same shimmering logo as the rest of the
      // startup chain, so this gate doesn't read as a separate plain screen.
      return const Scaffold(body: Center(child: ShimmeringLogo()));
    }

    if (_needsSetup) {
      if (_showForkLanguageGate) {
        return Scaffold(
          body: ForkFirstRunOnboarding(
            onFinished: _completeForkLanguageGate,
          ),
        );
      }

      // Continue with NeoStation's original configuration wizard in the
      // language the user selected on the preceding screen.
      return SetupWizard(onComplete: _completeSetup);
    }

    // Show the normal app.
    return widget.child;
  }
}
