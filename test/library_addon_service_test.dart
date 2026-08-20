import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('LibraryAddon manifest validation', () {
    test('accepts NeoStation Library v1 HTTPS manifest', () {
      final addon = LibraryAddon.fromManifest({
        'schema': 'neostation.library.v1',
        'id': 'com.example.manga',
        'name': 'Example Manga',
        'version': '1.0.0',
        'baseUrl': 'https://example.com/api',
        'description': 'Example catalog',
        'endpoints': {'search': '/search?q={query}'},
      }, origin: 'https://example.com/manifest.json');

      expect(addon.id, 'com.example.manga');
      expect(addon.name, 'Example Manga');
      expect(addon.version, '1.0.0');
      expect(addon.baseUrl, 'https://example.com/api');
    });

    test('rejects unsupported schema', () {
      expect(
        () => LibraryAddon.fromManifest({
          'schema': 'other.schema',
          'id': 'com.example.manga',
          'name': 'Example Manga',
          'version': '1.0.0',
          'baseUrl': 'https://example.com/api',
        }, origin: 'local'),
        throwsA(isA<LibraryAddonException>()),
      );
    });

    test('rejects non-HTTPS catalog base URL', () {
      expect(
        () => LibraryAddon.fromManifest({
          'schema': 'neostation.library.v1',
          'id': 'com.example.manga',
          'name': 'Example Manga',
          'version': '1.0.0',
          'baseUrl': 'http://example.com/api',
        }, origin: 'local'),
        throwsA(isA<LibraryAddonException>()),
      );
    });
  });

  group('Tachiyomi/Mihon repository import', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('imports repository array and expands nested sources', () async {
      final raw = jsonEncode([
        {
          'name': 'Outdated App',
          'pkg': 'eu.kanade.tachiyomi.extension.all.keiyoushi',
          'apk': 'tachiyomi-all.keiyoushi-v1.4.1.apk',
          'lang': 'all',
          'code': 1,
          'version': '1.4.1',
          'nsfw': 0,
          'sources': [
            {
              'name': 'Outdated App',
              'lang': 'all',
              'id': '1',
              'baseUrl': 'https://keiyoushi.github.io',
            },
          ],
        },
        {
          'name': 'Update to Mihon 0.20.1+',
          'pkg': 'eu.kanade.tachiyomi.extension.all.mihon',
          'apk': 'tachiyomi-all.mihon-v1.4.1.apk',
          'lang': 'all',
          'code': 1,
          'version': '1.4.1',
          'nsfw': 0,
          'sources': [
            {
              'name': 'Update to Mihon 0.20.1+',
              'lang': 'all',
              'id': '1',
              'baseUrl': 'https://mihon.app',
            },
          ],
        },
      ]);

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin: 'https://example.com/index.min.json',
      );

      expect(result.format, LibraryAddonDocumentFormat.tachiyomiRepository);
      expect(result.totalCount, 2);
      expect(result.addedCount, 2);
      expect(result.updatedCount, 0);
      expect(result.addons.first.isTachiyomiRepositorySource, isTrue);
      expect(result.addons.first.isMetadataOnlyOnIos, isTrue);
      expect(result.addons.first.language, 'all');
      expect(result.addons.first.androidApk, isNotEmpty);
      expect(result.addons.map((item) => item.id).toSet().length, 2);
    });

    test('ignores non-HTTPS repository sources', () async {
      final raw = jsonEncode([
        {
          'name': 'Mixed',
          'pkg': 'eu.example.mixed',
          'version': '1.0.0',
          'sources': [
            {
              'name': 'Unsafe',
              'id': '1',
              'baseUrl': 'http://example.com',
            },
            {
              'name': 'Safe',
              'id': '2',
              'baseUrl': 'https://example.com',
            },
          ],
        },
      ]);

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin: 'file:test.json',
      );
      expect(result.totalCount, 1);
      expect(result.addons.single.name, 'Safe');
    });
  });
}
