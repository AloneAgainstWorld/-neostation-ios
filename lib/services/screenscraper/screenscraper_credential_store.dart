import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Storage abstraction for the ScreenScraper user password.
///
/// Production builds use the platform secure credential store (Keychain on
/// iOS). The abstraction also keeps repository tests independent from native
/// plugin channels.
abstract interface class ScreenScraperCredentialStore {
  Future<void> writePassword(String password);
  Future<String?> readPassword();
  Future<void> deletePassword();
}

/// Stores the ScreenScraper password in the platform secure credential store.
class SecureScreenScraperCredentialStore
    implements ScreenScraperCredentialStore {
  static const String _passwordKey = 'screenscraper_user_password';

  final FlutterSecureStorage _storage;

  const SecureScreenScraperCredentialStore({
    FlutterSecureStorage storage = const FlutterSecureStorage(
      aOptions: AndroidOptions(resetOnError: false, migrateWithBackup: true),
      mOptions: MacOsOptions(usesDataProtectionKeychain: false),
    ),
  }) : _storage = storage;

  @override
  Future<void> writePassword(String password) =>
      _storage.write(key: _passwordKey, value: password);

  @override
  Future<String?> readPassword() => _storage.read(key: _passwordKey);

  @override
  Future<void> deletePassword() => _storage.delete(key: _passwordKey);
}
