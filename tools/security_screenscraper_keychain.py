from pathlib import Path

credential_store = Path('lib/services/screenscraper/screenscraper_credential_store.dart')
credential_store.write_text("""import 'package:flutter_secure_storage/flutter_secure_storage.dart';

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
""", encoding='utf-8')

repo_path = Path('lib/repositories/scraper_repository.dart')
repo = repo_path.read_text(encoding='utf-8')

import_needle = "import '../data/datasources/sqlite_service.dart';\nimport 'package:neostation/services/logger_service.dart';"
import_replacement = "import '../data/datasources/sqlite_service.dart';\nimport 'package:flutter/foundation.dart';\nimport 'package:neostation/services/logger_service.dart';\nimport 'package:neostation/services/screenscraper/screenscraper_credential_store.dart';"
if import_needle not in repo:
    raise SystemExit('Repository import anchor not found')
repo = repo.replace(import_needle, import_replacement, 1)

class_needle = "class ScraperRepository {\n  static final _log = LoggerService.instance;\n"
class_replacement = """class ScraperRepository {
  static final _log = LoggerService.instance;
  static ScreenScraperCredentialStore _credentialStore =
      const SecureScreenScraperCredentialStore();

  @visibleForTesting
  static void setCredentialStoreForTesting(
    ScreenScraperCredentialStore credentialStore,
  ) {
    _credentialStore = credentialStore;
  }

  @visibleForTesting
  static void resetCredentialStoreForTesting() {
    _credentialStore = const SecureScreenScraperCredentialStore();
  }
"""
if class_needle not in repo:
    raise SystemExit('Repository class anchor not found')
repo = repo.replace(class_needle, class_replacement, 1)

credentials_start = repo.index('  // ── Credentials ')
scraper_config_start = repo.index('  // ── Scraper config ', credentials_start)
secure_credentials = """  // ── Credentials ───────────────────────────────────────────────────────────

  /// Persists the ScreenScraper username and account metadata in SQLite while
  /// keeping the password in the platform secure credential store.
  static Future<bool> saveCredentials(
    String username,
    String password, [
    Map<String, dynamic>? userInfo,
    String? preferredLanguage,
  ]) async {
    String? previousPassword;
    try {
      final db = await SqliteService.getDatabase();
      previousPassword = await _credentialStore.readPassword();
      await _credentialStore.writePassword(password);

      final dataToSave = <String, dynamic>{
        'id': 1,
        'username': username,
        // Keep the legacy column empty. It remains in the schema for backward
        // compatibility, but passwords are no longer persisted in SQLite.
        'password': '',
      };

      if (userInfo != null) {
        dataToSave['user_id'] = userInfo['numid']?.toString() ?? '';
        dataToSave['level'] = userInfo['niveau']?.toString() ?? '';
        dataToSave['contribution'] = userInfo['contribution']?.toString() ?? '';
        dataToSave['maxthreads'] = userInfo['maxthreads']?.toString() ?? '';
        dataToSave['requests_today'] =
            int.tryParse(userInfo['requeststoday']?.toString() ?? '0') ?? 0;
        dataToSave['max_requests_per_day'] =
            int.tryParse(userInfo['maxrequestsperday']?.toString() ?? '0') ?? 0;
        dataToSave['requests_ko_today'] =
            int.tryParse(userInfo['requestskotoday']?.toString() ?? '0') ?? 0;
        dataToSave['max_requests_ko_per_day'] =
            int.tryParse(userInfo['maxrequestskoperday']?.toString() ?? '0') ?? 0;
        dataToSave['max_download_speed'] =
            int.tryParse(userInfo['maxdownloadspeed']?.toString() ?? '0') ?? 0;
        dataToSave['visites'] =
            int.tryParse(userInfo['visites']?.toString() ?? '0') ?? 0;
        dataToSave['last_visit'] = userInfo['datedernierevisite']?.toString() ?? '';
        dataToSave['fav_region'] = userInfo['fav_region']?.toString() ?? '';
      }

      if (preferredLanguage != null) {
        dataToSave['preferred_language'] = preferredLanguage;
      }

      try {
        await db.insert(
          'user_screenscraper_credentials',
          dataToSave,
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      } catch (_) {
        if (previousPassword == null || previousPassword.isEmpty) {
          await _credentialStore.deletePassword();
        } else {
          await _credentialStore.writePassword(previousPassword);
        }
        rethrow;
      }

      return true;
    } catch (e) {
      _log.e('Error saving scraper credentials: $e');
      return false;
    }
  }

  /// Retrieves saved ScreenScraper credentials.
  ///
  /// Existing installations are migrated lazily: a legacy Base64 password is
  /// moved to secure storage on first read and immediately removed from SQLite.
  static Future<Map<String, String>?> getSavedCredentials() async {
    try {
      final db = await SqliteService.getDatabase();
      final result = await db.query('user_screenscraper_credentials');

      if (result.isEmpty) return null;

      final row = result.first;
      var password = await _credentialStore.readPassword();
      final legacyPassword = row['password']?.toString() ?? '';

      if ((password == null || password.isEmpty) && legacyPassword.isNotEmpty) {
        try {
          final migratedPassword = utf8.decode(base64Decode(legacyPassword));
          await _credentialStore.writePassword(migratedPassword);
          await db.update(
            'user_screenscraper_credentials',
            {'password': ''},
            where: 'id = ?',
            whereArgs: [1],
          );
          password = migratedPassword;
        } on FormatException {
          _log.e('Unable to migrate legacy ScreenScraper credentials.');
          return null;
        }
      } else if (password != null &&
          password.isNotEmpty &&
          legacyPassword.isNotEmpty) {
        await db.update(
          'user_screenscraper_credentials',
          {'password': ''},
          where: 'id = ?',
          whereArgs: [1],
        );
      }

      if (password == null || password.isEmpty) return null;

      return {
        'username': row['username'].toString(),
        'password': password,
        'id': row['user_id']?.toString() ?? '',
        'level': row['level']?.toString() ?? '',
        'contribution': row['contribution']?.toString() ?? '',
        'maxthreads': row['maxthreads']?.toString() ?? '',
        'requests_today':
            (int.tryParse(row['requests_today']?.toString() ?? '0') ?? 0).toString(),
        'max_requests_per_day':
            (int.tryParse(row['max_requests_per_day']?.toString() ?? '0') ?? 0).toString(),
        'requests_ko_today':
            (int.tryParse(row['requests_ko_today']?.toString() ?? '0') ?? 0).toString(),
        'max_requests_ko_per_day':
            (int.tryParse(row['max_requests_ko_per_day']?.toString() ?? '0') ?? 0).toString(),
        'max_download_speed':
            (int.tryParse(row['max_download_speed']?.toString() ?? '0') ?? 0).toString(),
        'visites':
            (int.tryParse(row['visites']?.toString() ?? '0') ?? 0).toString(),
        'last_visit': row['last_visit']?.toString() ?? '',
        'fav_region': row['fav_region']?.toString() ?? '',
        'preferred_language': row['preferred_language']?.toString() ?? 'en',
      };
    } catch (e) {
      _log.e('Error getting scraper credentials: $e');
      return null;
    }
  }

  /// Deletes the ScreenScraper password from secure storage and removes the
  /// associated non-secret account metadata from SQLite.
  static Future<bool> clearCredentials() async {
    try {
      await _credentialStore.deletePassword();
      final db = await SqliteService.getDatabase();
      await db.delete('user_screenscraper_credentials');
      return true;
    } catch (e) {
      _log.e('Error clearing scraper credentials: $e');
      return false;
    }
  }

"""
repo = repo[:credentials_start] + secure_credentials + repo[scraper_config_start:]
repo_path.write_text(repo, encoding='utf-8')

test_path = Path('test/scraper_repository_test.dart')
test = test_path.read_text(encoding='utf-8')
test = test.replace(
    "import 'package:flutter_test/flutter_test.dart';\nimport 'package:neostation/repositories/scraper_repository.dart';",
    "import 'dart:convert';\n\nimport 'package:flutter_test/flutter_test.dart';\nimport 'package:neostation/repositories/scraper_repository.dart';\nimport 'package:neostation/services/screenscraper/screenscraper_credential_store.dart';",
    1,
)
memory_store = """class _MemoryScreenScraperCredentialStore
    implements ScreenScraperCredentialStore {
  String? password;

  @override
  Future<void> writePassword(String password) async {
    this.password = password;
  }

  @override
  Future<String?> readPassword() async => password;

  @override
  Future<void> deletePassword() async {
    password = null;
  }
}

"""
test = test.replace('void main() {', memory_store + 'void main() {', 1)
test = test.replace(
    '  late dynamic db;\n\n  setUp(() async {\n    db = await dbHelper.setUp();',
    '  late dynamic db;\n  late _MemoryScreenScraperCredentialStore credentialStore;\n\n  setUp(() async {\n    credentialStore = _MemoryScreenScraperCredentialStore();\n    ScraperRepository.setCredentialStoreForTesting(credentialStore);\n    db = await dbHelper.setUp();',
    1,
)
test = test.replace(
    '  tearDown(() async {\n    await dbHelper.tearDown();\n  });',
    '  tearDown(() async {\n    ScraperRepository.resetCredentialStoreForTesting();\n    await dbHelper.tearDown();\n  });',
    1,
)

tests_start = test.index("    test('saveCredentials encrypts password with base64'")
tests_end = test.index("    test('getScraperConfig returns defaults", tests_start)
secure_tests = """    test('saveCredentials keeps password out of SQLite', () async {
      final saved = await ScraperRepository.saveCredentials('user', 'pass');
      expect(saved, isTrue);
      expect(credentialStore.password, 'pass');

      final rows = await db.rawQuery(
        'SELECT password FROM user_screenscraper_credentials WHERE id = 1',
      );
      expect(rows.single['password'], '');

      final creds = await ScraperRepository.getSavedCredentials();
      expect(creds, isNotNull);
      expect(creds!['username'], 'user');
      expect(creds['password'], 'pass');
    });

    test('getSavedCredentials migrates a legacy Base64 password', () async {
      final legacyPassword = base64Encode(utf8.encode('legacy-pass'));
      await db.insert('user_screenscraper_credentials', {
        'id': 1,
        'username': 'legacy-user',
        'password': legacyPassword,
      });

      final creds = await ScraperRepository.getSavedCredentials();
      expect(creds, isNotNull);
      expect(creds!['username'], 'legacy-user');
      expect(creds['password'], 'legacy-pass');
      expect(credentialStore.password, 'legacy-pass');

      final rows = await db.rawQuery(
        'SELECT password FROM user_screenscraper_credentials WHERE id = 1',
      );
      expect(rows.single['password'], '');
    });

    test('clearCredentials removes database and secure-store credentials', () async {
      await ScraperRepository.saveCredentials('user', 'pass');
      final cleared = await ScraperRepository.clearCredentials();
      expect(cleared, isTrue);
      expect(credentialStore.password, isNull);

      final creds = await ScraperRepository.getSavedCredentials();
      expect(creds, isNull);
    });

"""
test = test[:tests_start] + secure_tests + test[tests_end:]
test_path.write_text(test, encoding='utf-8')
