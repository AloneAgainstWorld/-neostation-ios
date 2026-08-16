import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/services/screenscraper/screenscraper_client.dart';
import 'package:neostation/services/screenscraper_service.dart';
import 'package:neostation/widgets/custom_notification.dart';

class IosScraperLoginScreen extends StatefulWidget {
  final VoidCallback? onLoginSuccess;

  const IosScraperLoginScreen({super.key, this.onLoginSuccess});

  @override
  State<IosScraperLoginScreen> createState() => _IosScraperLoginScreenState();
}

class _IosScraperLoginScreenState extends State<IosScraperLoginScreen> {
  static const _baseUrl = 'https://api.screenscraper.fr/api2';

  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _passwordFocus = FocusNode();

  bool _obscurePassword = true;
  bool _isLoading = false;
  String? _status;

  static String get _devId {
    const compileTime = String.fromEnvironment('SCREENSCRAPER_DEV_ID');
    if (compileTime.isNotEmpty) return compileTime;
    return Platform.environment['SCREENSCRAPER_DEV_ID'] ?? '';
  }

  static String get _devPassword {
    const compileTime = String.fromEnvironment('SCREENSCRAPER_DEV_PASSWORD');
    if (compileTime.isNotEmpty) return compileTime;
    return Platform.environment['SCREENSCRAPER_DEV_PASSWORD'] ?? '';
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  void _setStatus(String value) {
    if (!mounted) return;
    setState(() => _status = value);
  }

  Future<_LoginProbeResult> _verifyCredentials(
    String username,
    String password,
  ) async {
    if (_devId.trim().isEmpty || _devPassword.trim().isEmpty) {
      return const _LoginProbeResult.failure(
        'Les identifiants développeur ScreenScraper ne sont pas présents dans cette IPA.',
      );
    }

    try {
      final softname = await ScreenscraperClient.getSoftname().timeout(
        const Duration(seconds: 7),
        onTimeout: () => 'NeoStation-iOS',
      );

      final url = Uri.parse('$_baseUrl/ssuserInfos.php').replace(
        queryParameters: {
          'devid': _devId.trim(),
          'devpassword': _devPassword.trim(),
          'softname': softname,
          'output': 'json',
          'ssid': username,
          'sspassword': password,
        },
      );

      final response = await ScreenscraperClient.httpGetWithRetry(
        url,
        headers: const {
          'User-Agent': 'NeoStation/1.0',
          'Accept': 'application/json',
        },
        maxRetries: 1,
        timeout: const Duration(seconds: 20),
      );

      if (response.statusCode != 200) {
        return _LoginProbeResult.failure(
          'ScreenScraper a répondu HTTP ${response.statusCode}.',
        );
      }

      final decoded = json.decode(response.body);
      if (decoded is! Map<String, dynamic>) {
        return const _LoginProbeResult.failure(
          'Réponse ScreenScraper invalide : le JSON reçu est inattendu.',
        );
      }

      final responseNode = decoded['response'];
      if (responseNode is Map) {
        final ssuser = responseNode['ssuser'];
        if (ssuser is Map) {
          return _LoginProbeResult.success(
            decoded,
            Map<String, dynamic>.from(ssuser),
          );
        }
      }

      final header = decoded['header'];
      String? apiError;
      if (header is Map) {
        apiError = header['error']?.toString();
      }

      return _LoginProbeResult.failure(
        apiError == null || apiError.isEmpty
            ? 'ScreenScraper a répondu, mais aucun profil utilisateur valide n’a été retourné.'
            : 'ScreenScraper : $apiError',
      );
    } on TimeoutException {
      return const _LoginProbeResult.failure(
        'Délai dépassé lors de la connexion à ScreenScraper.',
      );
    } catch (e) {
      return _LoginProbeResult.failure('Erreur de connexion : $e');
    }
  }

  Future<void> _performLogin() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      _setStatus(AppLocale.pleaseCompleteAllFields.getString(context));
      return;
    }

    setState(() {
      _isLoading = true;
      _status = '1/3 — Vérification du compte ScreenScraper…';
    });

    final probe = await _verifyCredentials(username, password);
    if (!mounted) return;

    if (!probe.success) {
      setState(() {
        _isLoading = false;
        _status = probe.message;
      });
      AppNotification.showNotification(
        context,
        probe.message,
        type: NotificationType.error,
      );
      return;
    }

    _setStatus('2/3 — Compte accepté. Enregistrement local…');

    final saved = await ScreenScraperService.saveCredentials(
      username,
      password,
      probe.userInfo,
    );
    if (!mounted) return;

    if (!saved) {
      setState(() {
        _isLoading = false;
        _status =
            'Le compte est valide, mais iOS n’a pas pu enregistrer les identifiants localement (Keychain/stockage).';
      });
      return;
    }

    final stored = await ScreenScraperService.getSavedCredentials();
    if (!mounted) return;

    if (stored == null ||
        stored['username'] != username ||
        stored['password'] != password) {
      setState(() {
        _isLoading = false;
        _status =
            'Le compte est valide, mais la relecture des identifiants échoue. Cela pointe vers le Keychain/signature iOS.';
      });
      return;
    }

    _setStatus('3/3 — Connexion réussie. Ouverture du scraper…');

    // Do not block navigation on the system-ID synchronization. On iOS this
    // can involve another network request and previously kept the login screen
    // waiting for tens of seconds even after authentication had succeeded.
    widget.onLoginSuccess?.call();

    unawaited(
      Future<void>(() async {
        try {
          await ScreenScraperService.syncSystemIds();
        } catch (_) {
          // The scraper screen is already usable. A later refresh can retry.
        }
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: EdgeInsets.all(24.r),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: 420.r),
              child: Container(
                padding: EdgeInsets.all(20.r),
                decoration: BoxDecoration(
                  color: theme.cardColor.withValues(alpha: 0.28),
                  borderRadius: BorderRadius.circular(14.r),
                  border: Border.all(
                    color: theme.colorScheme.primary.withValues(alpha: 0.2),
                  ),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      AppLocale.screenScraperLogin.getString(context),
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.bold,
                        fontSize: 16.r,
                      ),
                    ),
                    SizedBox(height: 14.r),
                    TextField(
                      controller: _usernameController,
                      enabled: !_isLoading,
                      textInputAction: TextInputAction.next,
                      onSubmitted: (_) => _passwordFocus.requestFocus(),
                      decoration: InputDecoration(
                        labelText: AppLocale.username.getString(context),
                        hintText: AppLocale.enterUsername.getString(context),
                      ),
                    ),
                    SizedBox(height: 10.r),
                    TextField(
                      controller: _passwordController,
                      focusNode: _passwordFocus,
                      enabled: !_isLoading,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.done,
                      onSubmitted: (_) => _performLogin(),
                      decoration: InputDecoration(
                        labelText: AppLocale.password.getString(context),
                        hintText: AppLocale.enterPassword.getString(context),
                        suffixIcon: IconButton(
                          onPressed: () => setState(
                            () => _obscurePassword = !_obscurePassword,
                          ),
                          icon: Icon(
                            _obscurePassword
                                ? Icons.visibility
                                : Icons.visibility_off,
                          ),
                        ),
                      ),
                    ),
                    SizedBox(height: 14.r),
                    SizedBox(
                      height: 42.r,
                      child: ElevatedButton(
                        onPressed: _isLoading ? null : _performLogin,
                        child: _isLoading
                            ? SizedBox(
                                width: 18.r,
                                height: 18.r,
                                child: const CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : Text(AppLocale.login.getString(context)),
                      ),
                    ),
                    if (_status != null) ...[
                      SizedBox(height: 12.r),
                      Container(
                        padding: EdgeInsets.all(10.r),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surface.withValues(alpha: 0.45),
                          borderRadius: BorderRadius.circular(8.r),
                        ),
                        child: Text(
                          _status!,
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontSize: 10.r,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _LoginProbeResult {
  final Map<String, dynamic>? payload;
  final Map<String, dynamic>? userInfo;
  final String message;

  const _LoginProbeResult._(this.payload, this.userInfo, this.message);

  const _LoginProbeResult.failure(String message) : this._(null, null, message);

  const _LoginProbeResult.success(
    Map<String, dynamic> payload,
    Map<String, dynamic> userInfo,
  ) : this._(payload, userInfo, 'OK');

  bool get success => payload != null && userInfo != null;
}
