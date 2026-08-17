import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/fork_onboarding_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:provider/provider.dart';

/// One-time fork introduction shown before NeoStation's existing library setup.
///
/// The device language is preselected and applied immediately when supported,
/// while all twelve application languages remain available. The second page is
/// therefore rendered directly in the language the user just chose.
class ForkFirstRunOnboarding extends StatefulWidget {
  const ForkFirstRunOnboarding({super.key, required this.onFinished});

  final Future<void> Function() onFinished;

  @override
  State<ForkFirstRunOnboarding> createState() =>
      _ForkFirstRunOnboardingState();
}

class _ForkFirstRunOnboardingState extends State<ForkFirstRunOnboarding> {
  int _step = 0;
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

  Future<void> _continueToWelcome() async {
    await _applyLanguage(_selectedLanguage);
    if (!mounted) return;
    setState(() => _step = 1);
  }

  Future<void> _finish() async {
    if (_finishing) return;
    setState(() => _finishing = true);
    await widget.onFinished();
    if (mounted) setState(() => _finishing = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: 760.w),
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: 28.w, vertical: 24.h),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: _step == 0
                  ? _buildLanguageStep(theme)
                  : _buildWelcomeStep(theme),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLanguageStep(ThemeData theme) {
    final entries = AppLocale.supportedLanguages.entries.toList();

    return Column(
      key: const ValueKey('fork_language_step'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.language_rounded,
          size: 48.r,
          color: theme.colorScheme.primary,
        ),
        SizedBox(height: 14.h),
        Text(
          ForkOnboardingLocale.languageTitle(context),
          textAlign: TextAlign.center,
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
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
                    onSelected: (_) => _applyLanguage(entry.key),
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
          onPressed: _continueToWelcome,
          icon: const Icon(Icons.arrow_forward_rounded),
          label: Text(ForkOnboardingLocale.continueLabel(context)),
        ),
      ],
    );
  }

  Widget _buildWelcomeStep(ThemeData theme) {
    return SingleChildScrollView(
      key: const ValueKey('fork_welcome_step'),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Image.asset(
            'assets/images/logo_transparent.png',
            width: 92.r,
            height: 92.r,
          ),
          SizedBox(height: 18.h),
          Text(
            ForkOnboardingLocale.welcomeTitle(context),
            textAlign: TextAlign.center,
            style: theme.textTheme.headlineMedium?.copyWith(
              fontWeight: FontWeight.w900,
            ),
          ),
          SizedBox(height: 14.h),
          ConstrainedBox(
            constraints: BoxConstraints(maxWidth: 560.w),
            child: Text(
              ForkOnboardingLocale.welcomeBody(context),
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyLarge?.copyWith(
                height: 1.45,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.78),
              ),
            ),
          ),
          SizedBox(height: 28.h),
          FilledButton.icon(
            onPressed: _finishing ? null : _finish,
            icon: _finishing
                ? SizedBox(
                    width: 16.r,
                    height: 16.r,
                    child: const CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.sports_esports_rounded),
            label: Text(ForkOnboardingLocale.startLabel(context)),
          ),
        ],
      ),
    );
  }
}
