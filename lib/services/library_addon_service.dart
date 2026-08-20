import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Versioned, declarative Library source manifest.
///
/// Add-ons do not execute arbitrary Dart/JavaScript code. They only describe a
/// remote catalog that NeoStation can consume through a stable schema. Catalog
/// fetching/parsing is layered on top of this model in the next Library stage.
class LibraryAddon {
  const LibraryAddon({
    required this.id,
    required this.name,
    required this.version,
    required this.baseUrl,
    required this.description,
    required this.iconUrl,
    required this.origin,
    required this.installedAt,
    required this.manifest,
  });

  static const String schemaV1 = 'neostation.library.v1';

  final String id;
  final String name;
  final String version;
  final String baseUrl;
  final String description;
  final String? iconUrl;
  final String origin;
  final DateTime installedAt;
  final Map<String, dynamic> manifest;

  factory LibraryAddon.fromManifest(
    Map<String, dynamic> manifest, {
    required String origin,
    DateTime? installedAt,
  }) {
    String requiredString(String key) {
      final value = manifest[key]?.toString().trim() ?? '';
      if (value.isEmpty) {
        throw LibraryAddonException('Missing required manifest field: $key');
      }
      return value;
    }

    final schema = requiredString('schema');
    if (schema != schemaV1) {
      throw LibraryAddonException(
        'Unsupported manifest schema "$schema". Expected $schemaV1.',
      );
    }

    final id = requiredString('id');
    if (!RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{1,99}$').hasMatch(id)) {
      throw LibraryAddonException('Invalid add-on id: $id');
    }

    final name = requiredString('name');
    final version = requiredString('version');
    final baseUrl = requiredString('baseUrl');
    _validateHttpsUrl(baseUrl, field: 'baseUrl');

    final iconValue = manifest['icon']?.toString().trim();
    final iconUrl = iconValue == null || iconValue.isEmpty ? null : iconValue;
    if (iconUrl != null) {
      _validateHttpsUrl(iconUrl, field: 'icon');
    }

    final endpoints = manifest['endpoints'];
    if (endpoints != null && endpoints is! Map) {
      throw LibraryAddonException(
        'Manifest field "endpoints" must be an object.',
      );
    }

    return LibraryAddon(
      id: id,
      name: name,
      version: version,
      baseUrl: baseUrl,
      description: manifest['description']?.toString().trim() ?? '',
      iconUrl: iconUrl,
      origin: origin,
      installedAt: installedAt ?? DateTime.now(),
      manifest: Map<String, dynamic>.from(manifest),
    );
  }

  static void _validateHttpsUrl(String value, {required String field}) {
    final uri = Uri.tryParse(value);
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw LibraryAddonException('$field must be a valid HTTPS URL.');
    }
  }

  Map<String, dynamic> toJson() => {
    'origin': origin,
    'installedAt': installedAt.toIso8601String(),
    'manifest': manifest,
  };

  factory LibraryAddon.fromJson(Map<String, dynamic> value) {
    final rawManifest = value['manifest'];
    if (rawManifest is! Map) {
      throw const LibraryAddonException('Stored add-on manifest is invalid.');
    }
    return LibraryAddon.fromManifest(
      Map<String, dynamic>.from(rawManifest),
      origin: value['origin']?.toString() ?? 'local',
      installedAt: DateTime.tryParse(value['installedAt']?.toString() ?? ''),
    );
  }
}

class LibraryAddonInstallResult {
  const LibraryAddonInstallResult({required this.addon, required this.updated});

  final LibraryAddon addon;
  final bool updated;
}

class LibraryAddonException implements Exception {
  const LibraryAddonException(this.message);

  final String message;

  @override
  String toString() => message;
}

class LibraryAddonService {
  LibraryAddonService._();

  static final LibraryAddonService instance = LibraryAddonService._();
  static const String _prefsKey = 'neostation_library_addons_v1';
  static const int _maxManifestBytes = 1024 * 1024;

  final List<LibraryAddon> _addons = [];
  bool _loaded = false;

  List<LibraryAddon> get addons => List.unmodifiable(_addons);

  Future<List<LibraryAddon>> load() async {
    if (_loaded) return addons;
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_prefsKey);
    _addons.clear();

    if (raw != null && raw.isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          for (final item in decoded) {
            if (item is! Map) continue;
            try {
              _addons.add(
                LibraryAddon.fromJson(Map<String, dynamic>.from(item)),
              );
            } catch (_) {
              // One corrupt/obsolete source must not make the whole Library
              // unusable; valid manifests still load normally.
            }
          }
        }
      } catch (_) {
        // Keep a clean empty list if the preference itself is malformed.
      }
    }

    _addons.sort(
      (a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()),
    );
    _loaded = true;
    return addons;
  }

  Future<LibraryAddonInstallResult> installFromUrl(String manifestUrl) async {
    final uri = Uri.tryParse(manifestUrl.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const LibraryAddonException('Manifest URL must use HTTPS.');
    }

    http.Response response;
    try {
      response = await http
          .get(uri, headers: const {'Accept': 'application/json'})
          .timeout(const Duration(seconds: 15));
    } catch (e) {
      throw LibraryAddonException('Unable to download manifest: $e');
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw LibraryAddonException(
        'Manifest server returned HTTP ${response.statusCode}.',
      );
    }
    if (response.bodyBytes.length > _maxManifestBytes) {
      throw const LibraryAddonException('Manifest is larger than 1 MB.');
    }

    return installFromJson(
      utf8.decode(response.bodyBytes),
      origin: uri.toString(),
    );
  }

  Future<LibraryAddonInstallResult> installFromJson(
    String rawJson, {
    required String origin,
  }) async {
    dynamic decoded;
    try {
      decoded = jsonDecode(rawJson);
    } catch (_) {
      throw const LibraryAddonException('Manifest is not valid JSON.');
    }
    if (decoded is! Map) {
      throw const LibraryAddonException('Manifest root must be a JSON object.');
    }

    final addon = LibraryAddon.fromManifest(
      Map<String, dynamic>.from(decoded),
      origin: origin,
    );
    await load();

    final existingIndex = _addons.indexWhere((item) => item.id == addon.id);
    final updated = existingIndex >= 0;
    if (updated) {
      _addons[existingIndex] = addon;
    } else {
      _addons.add(addon);
    }
    _addons.sort(
      (a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()),
    );
    await _persist();
    return LibraryAddonInstallResult(addon: addon, updated: updated);
  }

  Future<bool> remove(String id) async {
    await load();
    final before = _addons.length;
    _addons.removeWhere((addon) => addon.id == id);
    if (_addons.length == before) return false;
    await _persist();
    return true;
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _prefsKey,
      jsonEncode(_addons.map((addon) => addon.toJson()).toList()),
    );
  }
}
