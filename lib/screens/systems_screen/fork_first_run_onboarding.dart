import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/fork_onboarding_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:provider/provider.dart';

/// Shared preference used to record that the fork's first-run language gate
/// has already been completed.
const forkOnboardingCompletedKey = 'neostation_fork_onboarding_v1';

/// One-time language gate shown before NeoStation's existing setup wizard.
///
/// The device language is preselected and applied immediately when supported,
/// while all application languages remain available. Once the user confirms
/// the choice, the normal NeoStation setup continues in that language.
class ForkFirstRunOnboarding extends StatefulWidget {
  const ForkFirstRunOnboarding({super.key, required this.onFinished});

  final Future<void> Function() onFinished;

  @override
  State<ForkFirstRunOnboarding> createState() =>
      _ForkFirstRunOnboardingState();
}

class _ForkFirstRunOnboardingState extends State<ForkFirstRunOnboarding> {
  late String _selectedLanguage;
  bool _finishing = false;

  @override
  void initState() {
    super.initState();
    _selectedLanguage = _deviceLanguage();

    // Start the very first interactive screen in the device language whenever
    // NeoStation supports it, instead of forcing a new user to read English
    // before they can choose their language.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _applyLanguage(_selectedLanguage);
    });
  }

  String _deviceLanguage() {
    final locale = WidgetsBinding.instance.platformDispatcher.locale;

    if (locale.languageCode == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final region = locale.countryCode?.toUpperCase();
      if (script == 'hant' ||
          region == 'TW' ||
          region == 'HK' ||
          region == 'MO') {
        return 'zh_Hant';
      }
      return 'zh';
    }

    return AppLocale.supportedLanguages.containsKey(locale.languageCode)
        ? locale.languageCode
        : 'en';
  }

  Future<void> _applyLanguage(String code) async {
    if (!mounted) return;
    setState(() => _selectedLanguage = code);
    await context.read<SqliteConfigProvider>().updateAppLanguage(code);
  }

  Future<void> _continue() async {
    if (_finishing) return;
    setState(() => _finishing = true);
    await _applyLanguage(_selectedLanguage);
    await widget.onFinished();
    if (mounted) setState(() => _finishing = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final entries = AppLocale.supportedLanguages.entries.toList();

    return SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: 760.w),
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: 28.w, vertical: 24.h),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Image.asset(
                  'assets/images/logo_transparent.png',
                  width: 78.r,
                  height: 78.r,
                ),
                SizedBox(height: 16.h),
                Text(
                  ForkOnboardingLocale.welcomeTitle(context),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                  ),
                ),
                SizedBox(height: 8.h),
                Text(
                  ForkOnboardingLocale.languageTitle(context),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                    color: theme.colorScheme.primary,
                  ),
                ),
                SizedBox(height: 8.h),
                ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: 620.w),
                  child: Text(
                    ForkOnboardingLocale.languageSubtitle(context),
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                    ),
                  ),
                ),
                SizedBox(height: 22.h),
                Flexible(
                  child: SingleChildScrollView(
                    child: Wrap(
                      alignment: WrapAlignment.center,
                      spacing: 10.w,
                      runSpacing: 10.h,
                      children: [
                        for (final entry in entries)
                          ChoiceChip(
                            label: Text(entry.value),
                            selected: _selectedLanguage == entry.key,
                            onSelected: _finishing
                                ? null
                                : (_) => _applyLanguage(entry.key),
                            selectedColor: theme.colorScheme.primaryContainer,
                            side: BorderSide(
                              color: _selectedLanguage == entry.key
                                  ? theme.colorScheme.primary
                                  : theme.colorScheme.outlineVariant,
                            ),
                            labelStyle: TextStyle(
                              color: _selectedLanguage == entry.key
                                  ? theme.colorScheme.onPrimaryContainer
                                  : theme.colorScheme.onSurface,
                              fontWeight: _selectedLanguage == entry.key
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                SizedBox(height: 22.h),
                FilledButton.icon(
                  onPressed: _finishing ? null : _continue,
                  icon: _finishing
                      ? SizedBox(
                          width: 16.r,
                          height: 16.r,
                          child: const CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.arrow_forward_rounded),
                  label: Text(ForkOnboardingLocale.continueLabel(context)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
