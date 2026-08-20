import 'dart:convert';

import 'package:http/http.dart' as http;

import 'library_addon_service.dart';

enum LibraryMediaType {
  book,
  manga,
  novel,
  comic,
  anime,
  unknown,
}

class LibraryCatalogItem {
  const LibraryCatalogItem({
    required this.id,
    required this.title,
    required this.mediaType,
    required this.subtitle,
    required this.description,
    required this.coverUrl,
    required this.content,
    required this.contentUrl,
    required this.pageUrls,
    required this.raw,
  });

  final String id;
  final String title;
  final LibraryMediaType mediaType;
  final String subtitle;
  final String description;
  final String? coverUrl;
  final String? content;
  final String? contentUrl;
  final List<String> pageUrls;
  final Map<String, dynamic> raw;

  bool get hasReadableContent =>
      (content != null && content!.trim().isNotEmpty) ||
      contentUrl != null ||
      pageUrls.isNotEmpty;

  factory LibraryCatalogItem.fromJson(
    Map<String, dynamic> raw, {
    required Uri baseUri,
  }) {
    String text(List<String> keys) {
      for (final key in keys) {
        final value = raw[key]?.toString().trim();
        if (value != null && value.isNotEmpty) return value;
      }
      return '';
    }

    String? resolveUrl(dynamic value) {
      final candidate = value?.toString().trim();
      if (candidate == null || candidate.isEmpty) return null;
      final parsed = Uri.tryParse(candidate);
      final resolved =
          parsed != null && parsed.hasScheme ? parsed : baseUri.resolve(candidate);
      if (resolved.scheme != 'https' || resolved.host.isEmpty) return null;
      return resolved.toString();
    }

    final title = text(const ['title', 'name']);
    if (title.isEmpty) {
      throw const LibraryAddonException(
        'Catalog item is missing both "title" and "name".',
      );
    }

    final id = text(const ['id', 'slug', 'key', 'url']);
    final type = text(const ['type', 'mediaType', 'media_type']).toLowerCase();
    final mediaType = switch (type) {
      'book' => LibraryMediaType.book,
      'manga' => LibraryMediaType.manga,
      'novel' || 'light-novel' || 'light_novel' => LibraryMediaType.novel,
      'comic' || 'comics' => LibraryMediaType.comic,
      'anime' => LibraryMediaType.anime,
      _ => LibraryMediaType.unknown,
    };

    final pageUrls = <String>[];
    final rawPages = raw['pages'] ?? raw['images'];
    if (rawPages is List) {
      for (final page in rawPages) {
        final resolved = resolveUrl(page);
        if (resolved != null) pageUrls.add(resolved);
      }
    }

    final inlineContent =
        text(const ['content', 'text', 'body', 'markdown']);

    return LibraryCatalogItem(
      id: id.isEmpty ? title : id,
      title: title,
      mediaType: mediaType,
      subtitle: text(const ['subtitle', 'author', 'creator']),
      description: text(const ['description', 'summary', 'synopsis']),
      coverUrl: resolveUrl(
        raw['coverUrl'] ?? raw['cover'] ?? raw['thumbnail'] ?? raw['image'],
      ),
      content: inlineContent.isEmpty ? null : inlineContent,
      contentUrl: resolveUrl(
        raw['contentUrl'] ?? raw['readerUrl'] ?? raw['readUrl'],
      ),
      pageUrls: List.unmodifiable(pageUrls),
      raw: Map<String, dynamic>.unmodifiable(raw),
    );
  }
}

class LibraryCatalogService {
  LibraryCatalogService._();

  static final LibraryCatalogService instance = LibraryCatalogService._();

  static const Duration _timeout = Duration(seconds: 20);
  static const int _maxCatalogBytes = 12 * 1024 * 1024;
  static const int _maxReaderBytes = 8 * 1024 * 1024;

  Future<List<LibraryCatalogItem>> loadCatalog(LibraryAddon addon) async {
    if (addon.sourceKind == LibrarySourceKind.metadataOnly) {
      throw const LibraryAddonException(
        'This Tachiyomi/Mihon source is metadata-only on iOS. '
        'Its Android extension runtime cannot execute inside NeoStation.',
      );
    }
    if (addon.sourceKind == LibrarySourceKind.localLibrary) {
      throw const LibraryAddonException(
        'This is a local library source. A local library location must be '
        'configured before it can be browsed.',
      );
    }

    final baseUrl = addon.baseUrl;
    if (baseUrl == null) {
      throw const LibraryAddonException('Catalog source has no baseUrl.');
    }
    final endpoint = addon.catalogEndpoint;
    if (endpoint == null) {
      throw const LibraryAddonException(
        'This NeoStation source does not expose endpoints.catalog or endpoints.browse.',
      );
    }

    final baseUri = Uri.parse(baseUrl);
    final uri = _resolveHttps(baseUri, endpoint, field: 'catalog endpoint');
    final response = await _get(uri, maxBytes: _maxCatalogBytes);

    dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      throw const LibraryAddonException(
        'Catalog endpoint did not return valid JSON.',
      );
    }

    final rawItems = _extractItems(decoded);
    final items = <LibraryCatalogItem>[];
    for (final raw in rawItems) {
      if (raw is! Map) continue;
      try {
        items.add(
          LibraryCatalogItem.fromJson(
            Map<String, dynamic>.from(raw),
            baseUri: baseUri,
          ),
        );
      } on LibraryAddonException {
        // One malformed entry should not make an otherwise valid catalog fail.
      }
    }
    return List.unmodifiable(items);
  }

  Future<String> loadReadableText(LibraryCatalogItem item) async {
    final inline = item.content?.trim();
    if (inline != null && inline.isNotEmpty) return inline;

    final contentUrl = item.contentUrl;
    if (contentUrl == null) {
      throw const LibraryAddonException(
        'This item does not expose readable text or a content URL.',
      );
    }

    final uri = Uri.parse(contentUrl);
    final response = await _get(uri, maxBytes: _maxReaderBytes);
    final body = utf8.decode(response.bodyBytes);

    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) {
        for (final key in const ['content', 'text', 'body', 'markdown']) {
          final value = decoded[key]?.toString();
          if (value != null && value.trim().isNotEmpty) return value;
        }
      }
    } catch (_) {
      // Plain text/Markdown is a supported reader response.
    }

    if (body.trim().isEmpty) {
      throw const LibraryAddonException('Reader response is empty.');
    }
    return body;
  }

  static List<dynamic> _extractItems(dynamic decoded) {
    if (decoded is List) return decoded;
    if (decoded is Map) {
      for (final key in const ['items', 'results', 'entries']) {
        final value = decoded[key];
        if (value is List) return value;
      }
      final data = decoded['data'];
      if (data is List) return data;
      if (data is Map) {
        for (final key in const ['items', 'results', 'entries']) {
          final value = data[key];
          if (value is List) return value;
        }
      }
    }
    throw const LibraryAddonException(
      'Catalog JSON must be a list or contain an items/results/entries list.',
    );
  }

  static Uri _resolveHttps(Uri base, String value, {required String field}) {
    final candidate = Uri.tryParse(value.trim());
    if (candidate == null) {
      throw LibraryAddonException('$field is not a valid URL.');
    }
    final resolved = candidate.hasScheme ? candidate : base.resolveUri(candidate);
    if (resolved.scheme != 'https' || resolved.host.isEmpty) {
      throw LibraryAddonException('$field must resolve to HTTPS.');
    }
    return resolved;
  }

  static Future<http.Response> _get(
    Uri uri, {
    required int maxBytes,
  }) async {
    http.Response response;
    try {
      response = await http
          .get(uri, headers: const {'Accept': 'application/json, text/plain'})
          .timeout(_timeout);
    } catch (error) {
      throw LibraryAddonException('Unable to load ${uri.host}: $error');
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw LibraryAddonException(
        '${uri.host} returned HTTP ${response.statusCode}.',
      );
    }
    if (response.bodyBytes.length > maxBytes) {
      throw const LibraryAddonException('Library response is too large.');
    }
    return response;
  }
}
