import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';

void main() {
  group('LibraryAddon manifest validation', () {
    test('accepts NeoStation Library v1 HTTPS manifest', () {
      final addon = LibraryAddon.fromManifest(
        {
          'schema': 'neostation.library.v1',
          'id': 'com.example.manga',
          'name': 'Example Manga',
          'version': '1.0.0',
          'baseUrl': 'https://example.com/api',
          'description': 'Example catalog',
          'endpoints': {'search': '/search?q={query}'},
        },
        origin: 'https://example.com/manifest.json',
      );

      expect(addon.id, 'com.example.manga');
      expect(addon.name, 'Example Manga');
      expect(addon.version, '1.0.0');
      expect(addon.baseUrl, 'https://example.com/api');
    });

    test('rejects unsupported schema', () {
      expect(
        () => LibraryAddon.fromManifest(
          {
            'schema': 'other.schema',
            'id': 'com.example.manga',
            'name': 'Example Manga',
            'version': '1.0.0',
            'baseUrl': 'https://example.com/api',
          },
          origin: 'local',
        ),
        throwsA(isA<LibraryAddonException>()),
      );
    });

    test('rejects non-HTTPS catalog base URL', () {
      expect(
        () => LibraryAddon.fromManifest(
          {
            'schema': 'neostation.library.v1',
            'id': 'com.example.manga',
            'name': 'Example Manga',
            'version': '1.0.0',
            'baseUrl': 'http://example.com/api',
          },
          origin: 'local',
        ),
        throwsA(isA<LibraryAddonException>()),
      );
    });
  });
}
