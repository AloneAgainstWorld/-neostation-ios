import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum LibrarySourceKind {
  catalog,
  localLibrary,
  metadataOnly,
}

/// Versioned, declarative Library source manifest.
///
/// Add-ons do not execute arbitrary Dart/JavaScript code. They only describe a
/// remote catalog that NeoStation can consume through a stable schema. The
/// Library also accepts Tachiyomi/Mihon extension-repository indexes as a
/// discovery format; Android APKs are preserved as metadata only on iOS.
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
  static const String tachiyomiProviderType = 'tachiyomi-extension-repository';

  final String id;
  final String name;
  final String version;
  final String? baseUrl;
  final String description;
  final String? iconUrl;
  final String origin;
  final DateTime installedAt;
  final Map<String, dynamic> manifest;

  bool get isTachiyomiRepositorySource {
    final provider = manifest['provider'];
    return provider is Map && provider['type'] == tachiyomiProviderType;
  }

  String? get language {
    final provider = manifest['provider'];
    if (provider is Map) {
      final value = provider['sourceLang']?.toString().trim();
      if (value != null && value.isNotEmpty) return value;
    }
    return null;
  }

  String? get androidPackage {
    final provider = manifest['provider'];
    if (provider is Map) {
      final value = provider['package']?.toString().trim();
      if (value != null && value.isNotEmpty) return value;
    }
    return null;
  }

  String? get androidApk {
    final provider = manifest['provider'];
    if (provider is Map) {
      final value = provider['apk']?.toString().trim();
      if (value != null && value.isNotEmpty) return value;
    }
    return null;
  }

  bool get isMetadataOnlyOnIos =>
      manifest['iosCompatibility']?.toString() == 'metadata-only';

  String? get minimumAppVersion {
    final value = manifest['minAppVersion']?.toString().trim();
    return value == null || value.isEmpty ? null : value;
  }

  LibrarySourceKind get sourceKind {
    if (isMetadataOnlyOnIos) return LibrarySourceKind.metadataOnly;
    final raw = (manifest['sourceType'] ?? manifest['kind'])
        ?.toString()
        .trim()
        .toLowerCase();
    if (raw == 'local' ||
        raw == 'local-library' ||
        raw == 'local_library' ||
        raw == 'locallibrary') {
      return LibrarySourceKind.localLibrary;
    }
    return LibrarySourceKind.catalog;
  }

  bool get canBrowseOnIos =>
      sourceKind == LibrarySourceKind.catalog && catalogEndpoint != null;

  String? get catalogEndpoint {
    final endpoints = manifest['endpoints'];
    if (endpoints is! Map) return null;
    for (final key in const ['catalog', 'browse']) {
      final value = endpoints[key]?.toString().trim();
      if (value != null && value.isNotEmpty) return value;
    }
    return null;
  }

  String? get searchEndpoint {
    final endpoints = manifest['endpoints'];
    if (endpoints is! Map) return null;
    final value = endpoints['search']?.toString().trim();
    return value == null || value.isEmpty ? null : value;
  }

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
    final rawKind = (manifest['sourceType'] ?? manifest['kind'])
        ?.toString()
        .trim()
        .toLowerCase();
    final isLocal =
        rawKind == 'local' ||
        rawKind == 'local-library' ||
        rawKind == 'local_library' ||
        rawKind == 'locallibrary';

    final baseUrlValue = manifest['baseUrl']?.toString().trim();
    final baseUrl =
        baseUrlValue == null || baseUrlValue.isEmpty ? null : baseUrlValue;
    if (!isLocal && baseUrl == null) {
      throw const LibraryAddonException(
        'Missing required manifest field: baseUrl',
      );
    }
    if (baseUrl != null) {
      _validateHttpsUrl(baseUrl, field: 'baseUrl');
    }

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

enum LibraryAddonDocumentFormat { neoStationManifest, tachiyomiRepository }

class LibraryAddonInstallResult {
  const LibraryAddonInstallResult({required this.addon, required this.updated});

  final LibraryAddon addon;
  final bool updated;
}

class LibraryAddonBatchInstallResult {
  const LibraryAddonBatchInstallResult({
    required this.addons,
    required this.addedCount,
    required this.updatedCount,
    required this.format,
  });

  final List<LibraryAddon> addons;
  final int addedCount;
  final int updatedCount;
  final LibraryAddonDocumentFormat format;

  int get totalCount => addons.length;
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

  /// Tachiyomi/Mihon repositories can contain hundreds of extension entries,
  /// so the old 1 MB single-manifest limit was too small for a directory index.
  static const int _maxDocumentBytes = 20 * 1024 * 1024;
  static const int _maxRepositorySources = 10000;

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

    _sortAddons();
    _loaded = true;
    return addons;
  }

  /// Installs either a native NeoStation manifest object or a Tachiyomi/Mihon
  /// extension-repository JSON array from HTTPS.
  Future<LibraryAddonBatchInstallResult> installDocumentFromUrl(
    String documentUrl,
  ) async {
    final uri = Uri.tryParse(documentUrl.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const LibraryAddonException('Repository URL must use HTTPS.');
    }

    http.Response response;
    try {
      response = await http
          .get(uri, headers: const {'Accept': 'application/json'})
          .timeout(const Duration(seconds: 20));
    } catch (e) {
      throw LibraryAddonException('Unable to download repository: $e');
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw LibraryAddonException(
        'Repository server returned HTTP ${response.statusCode}.',
      );
    }
    if (response.bodyBytes.length > _maxDocumentBytes) {
      throw const LibraryAddonException('Repository is larger than 20 MB.');
    }

    return installDocumentFromJson(
      utf8.decode(response.bodyBytes),
      origin: uri.toString(),
    );
  }

  Future<LibraryAddonBatchInstallResult> installDocumentFromJson(
    String rawJson, {
    required String origin,
  }) async {
    dynamic decoded;
    try {
      decoded = jsonDecode(rawJson);
    } catch (_) {
      throw const LibraryAddonException('Document is not valid JSON.');
    }

    if (decoded is Map) {
      final manifest = Map<String, dynamic>.from(decoded);
      _rejectKnownExternalManifest(manifest);
      final addon = LibraryAddon.fromManifest(
        manifest,
        origin: origin,
      );
      await _validateMinimumAppVersion(addon);
      return _upsertMany(
        [addon],
        format: LibraryAddonDocumentFormat.neoStationManifest,
      );
    }

    if (decoded is List) {
      final parsed = _parseTachiyomiRepository(decoded, origin: origin);
      return _upsertMany(
        parsed,
        format: LibraryAddonDocumentFormat.tachiyomiRepository,
      );
    }

    throw const LibraryAddonException(
      'Document root must be a NeoStation manifest object or a Tachiyomi/Mihon repository array.',
    );
  }

  /// Backward-compatible single-manifest API.
  Future<LibraryAddonInstallResult> installFromUrl(String manifestUrl) async {
    final batch = await installDocumentFromUrl(manifestUrl);
    if (batch.format != LibraryAddonDocumentFormat.neoStationManifest ||
        batch.addons.length != 1) {
      throw const LibraryAddonException(
        'This URL contains a repository. Use the repository import API.',
      );
    }
    return LibraryAddonInstallResult(
      addon: batch.addons.single,
      updated: batch.updatedCount == 1,
    );
  }

  /// Backward-compatible single-manifest API.
  Future<LibraryAddonInstallResult> installFromJson(
    String rawJson, {
    required String origin,
  }) async {
    final batch = await installDocumentFromJson(rawJson, origin: origin);
    if (batch.format != LibraryAddonDocumentFormat.neoStationManifest ||
        batch.addons.length != 1) {
      throw const LibraryAddonException(
        'This JSON contains a repository. Use the repository import API.',
      );
    }
    return LibraryAddonInstallResult(
      addon: batch.addons.single,
      updated: batch.updatedCount == 1,
    );
  }

  void _rejectKnownExternalManifest(Map<String, dynamic> manifest) {
    if (manifest.containsKey('schema')) return;

    final looksLikeObsidianPlugin =
        manifest['id'] != null &&
        manifest['name'] != null &&
        manifest['version'] != null &&
        manifest['minAppVersion'] != null &&
        (manifest['author'] != null || manifest['isDesktopOnly'] != null);

    if (looksLikeObsidianPlugin) {
      throw const LibraryAddonException(
        'This is an Obsidian plugin manifest. Its minAppVersion targets '
        'Obsidian, not NeoStation. A NeoStation source must declare '
        'schema "neostation.library.v1".',
      );
    }
  }

  Future<void> _validateMinimumAppVersion(LibraryAddon addon) async {
    final minimum = addon.minimumAppVersion;
    if (minimum == null) return;

    final requiredParts = _parseSemanticVersion(minimum);
    if (requiredParts == null) {
      throw LibraryAddonException(
        'Invalid minAppVersion "$minimum". Expected a semantic version such as 0.9.9.',
      );
    }

    final info = await PackageInfo.fromPlatform();
    final current = info.version.trim();
    final currentParts = _parseSemanticVersion(current);
    if (currentParts == null) {
      throw LibraryAddonException(
        'Unable to compare the current NeoStation version "$current".',
      );
    }

    if (_compareVersionParts(currentParts, requiredParts) < 0) {
      throw LibraryAddonException(
        'This source requires NeoStation $minimum or newer. '
        'Installed version: $current.',
      );
    }
  }

  static List<int>? _parseSemanticVersion(String value) {
    final core = value.trim().split(RegExp(r'[-+]')).first;
    if (core.isEmpty) return null;
    final result = <int>[];
    for (final piece in core.split('.')) {
      final parsed = int.tryParse(piece);
      if (parsed == null || parsed < 0) return null;
      result.add(parsed);
    }
    return result.isEmpty ? null : result;
  }

  static int _compareVersionParts(List<int> a, List<int> b) {
    final length = a.length > b.length ? a.length : b.length;
    for (var index = 0; index < length; index++) {
      final left = index < a.length ? a[index] : 0;
      final right = index < b.length ? b[index] : 0;
      if (left != right) return left.compareTo(right);
    }
    return 0;
  }

  List<LibraryAddon> _parseTachiyomiRepository(
    List<dynamic> entries, {
    required String origin,
  }) {
    final result = <LibraryAddon>[];
    final seenIds = <String>{};

    for (final rawEntry in entries) {
      if (rawEntry is! Map) continue;
      final entry = Map<String, dynamic>.from(rawEntry);
      final packageName = entry['pkg']?.toString().trim() ?? '';
      if (packageName.isEmpty) continue;

      final extensionName = entry['name']?.toString().trim() ?? packageName;
      final version = entry['version']?.toString().trim().isNotEmpty == true
          ? entry['version'].toString().trim()
          : (entry['code']?.toString() ?? '0');
      final apk = entry['apk']?.toString().trim() ?? '';
      final extensionLang = entry['lang']?.toString().trim() ?? 'all';
      final code = entry['code'];
      final nsfw = entry['nsfw'];
      final rawSources = entry['sources'];
      if (rawSources is! List) continue;

      for (var sourceIndex = 0;
          sourceIndex < rawSources.length;
          sourceIndex++) {
        if (result.length >= _maxRepositorySources) {
          throw const LibraryAddonException(
            'Repository contains more than 10000 sources.',
          );
        }

        final rawSource = rawSources[sourceIndex];
        if (rawSource is! Map) continue;
        final source = Map<String, dynamic>.from(rawSource);
        final baseUrl = source['baseUrl']?.toString().trim() ?? '';
        final uri = Uri.tryParse(baseUrl);
        // Keep iOS network sources HTTPS-only. Invalid entries are ignored
        // rather than making a large third-party repository entirely unusable.
        if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) continue;

        final sourceId = source['id']?.toString().trim().isNotEmpty == true
            ? source['id'].toString().trim()
            : sourceIndex.toString();
        final sourceName = source['name']?.toString().trim().isNotEmpty == true
            ? source['name'].toString().trim()
            : extensionName;
        final sourceLang = source['lang']?.toString().trim().isNotEmpty == true
            ? source['lang'].toString().trim()
            : extensionLang;
        final id = _tachiyomiAddonId(packageName, sourceId);
        if (!seenIds.add(id)) continue;

        final manifest = <String, dynamic>{
          'schema': LibraryAddon.schemaV1,
          'id': id,
          'name': sourceName,
          'version': version,
          'baseUrl': baseUrl,
          'description':
              'Tachiyomi/Mihon repository source • $sourceLang • $extensionName',
          'iosCompatibility': 'metadata-only',
          'provider': <String, dynamic>{
            'type': LibraryAddon.tachiyomiProviderType,
            'package': packageName,
            'apk': apk,
            'extensionName': extensionName,
            'extensionLang': extensionLang,
            'extensionCode': code,
            'sourceId': sourceId,
            'sourceLang': sourceLang,
            'nsfw': nsfw,
            'repositoryOrigin': origin,
          },
        };

        result.add(LibraryAddon.fromManifest(manifest, origin: origin));
      }
    }

    if (result.isEmpty) {
      throw const LibraryAddonException(
        'No HTTPS Tachiyomi/Mihon sources were found in this repository.',
      );
    }
    return result;
  }

  static String _tachiyomiAddonId(String packageName, String sourceId) {
    String clean(String value) => value
        .replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_')
        .replaceAll(RegExp(r'_+'), '_');

    final safePackage = clean(packageName);
    final safeSource = clean(sourceId);
    var id = 'tachiyomi.$safeSource.$safePackage';
    if (id.length > 100) id = id.substring(0, 100);
    if (id.length < 2) id = 'tachiyomi.source';
    return id;
  }

  Future<LibraryAddonBatchInstallResult> _upsertMany(
    List<LibraryAddon> incoming, {
    required LibraryAddonDocumentFormat format,
  }) async {
    await load();
    var addedCount = 0;
    var updatedCount = 0;

    for (final addon in incoming) {
      final existingIndex = _addons.indexWhere((item) => item.id == addon.id);
      if (existingIndex >= 0) {
        _addons[existingIndex] = addon;
        updatedCount++;
      } else {
        _addons.add(addon);
        addedCount++;
      }
    }

    _sortAddons();
    await _persist();
    return LibraryAddonBatchInstallResult(
      addons: List.unmodifiable(incoming),
      addedCount: addedCount,
      updatedCount: updatedCount,
      format: format,
    );
  }

  void _sortAddons() {
    _addons.sort(
      (a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()),
    );
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
