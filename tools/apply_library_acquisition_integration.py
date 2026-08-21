from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found for {label}: {old[:120]!r}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Library catalog model + offline EPUB parsing
# ---------------------------------------------------------------------------
catalog_path = "lib/services/library_catalog_service.dart"
catalog = read(catalog_path)

if "class LibraryAcquisitionLink" not in catalog:
    catalog = replace_once(
        catalog,
        "import 'dart:convert';\n",
        "import 'dart:convert';\nimport 'dart:io';\n",
        label="catalog dart:io import",
    )
    enum_anchor = """enum LibraryMediaType {\n  book,\n  manga,\n  novel,\n  comic,\n  anime,\n  unknown,\n}\n\n"""
    acquisition_class = """enum LibraryMediaType {\n  book,\n  manga,\n  novel,\n  comic,\n  anime,\n  unknown,\n}\n\n/// A source-declared acquisition action for a Library item.\n///\n/// NeoStation never discovers alternate copies on its own: every URL in this\n/// model must come directly from the selected provider or user-installed\n/// Library source.\nclass LibraryAcquisitionLink {\n  const LibraryAcquisitionLink({\n    required this.label,\n    required this.url,\n    required this.action,\n    this.format = '',\n    this.mimeType = '',\n  });\n\n  final String label;\n  final String url;\n\n  /// `download` stores the provider-supplied file locally. `read` opens the\n  /// provider's official web reader.\n  final String action;\n  final String format;\n  final String mimeType;\n\n  bool get canDownload => action == 'download';\n  bool get isExternalReader => action == 'read';\n\n  Map<String, dynamic> toJson() => <String, dynamic>{\n    'label': label,\n    'url': url,\n    'action': action,\n    if (format.isNotEmpty) 'format': format,\n    if (mimeType.isNotEmpty) 'mimeType': mimeType,\n  };\n}\n\n"""
    catalog = replace_once(
        catalog,
        enum_anchor,
        acquisition_class,
        label="acquisition model",
    )

if "this.acquisitionLinks = const <LibraryAcquisitionLink>[]" not in catalog:
    catalog = replace_once(
        catalog,
        "    required this.pageUrls,\n    required this.raw,\n  });",
        "    required this.pageUrls,\n    required this.raw,\n    this.acquisitionLinks = const <LibraryAcquisitionLink>[],\n  });",
        label="catalog constructor acquisition field",
    )
    catalog = replace_once(
        catalog,
        "  final List<String> pageUrls;\n  final Map<String, dynamic> raw;",
        "  final List<String> pageUrls;\n  final Map<String, dynamic> raw;\n  final List<LibraryAcquisitionLink> acquisitionLinks;",
        label="catalog acquisition field",
    )

if "final acquisitionLinks = <LibraryAcquisitionLink>[];" not in catalog:
    anchor = """    final inlineContent =\n        text(const ['content', 'text', 'body', 'markdown']);\n\n"""
    block = """    final acquisitionLinks = <LibraryAcquisitionLink>[];\n    final acquisitionUrls = <String>{};\n\n    void addAcquisition(\n      dynamic value, {\n      String fallbackLabel = 'Download',\n      String fallbackAction = 'download',\n      String fallbackFormat = '',\n      String fallbackMimeType = '',\n    }) {\n      if (value == null) return;\n      if (value is Iterable && value is! String) {\n        for (final entry in value) {\n          addAcquisition(\n            entry,\n            fallbackLabel: fallbackLabel,\n            fallbackAction: fallbackAction,\n            fallbackFormat: fallbackFormat,\n            fallbackMimeType: fallbackMimeType,\n          );\n        }\n        return;\n      }\n\n      dynamic rawUrl = value;\n      var label = fallbackLabel;\n      var action = fallbackAction;\n      var format = fallbackFormat;\n      var mimeType = fallbackMimeType;\n      if (value is Map) {\n        rawUrl = value['url'] ?? value['href'] ?? value['downloadUrl'];\n        label = value['label']?.toString().trim() ?? label;\n        action = value['action']?.toString().trim().toLowerCase() ?? action;\n        format = value['format']?.toString().trim().toLowerCase() ?? format;\n        mimeType = value['mimeType']?.toString().trim().toLowerCase() ??\n            value['type']?.toString().trim().toLowerCase() ??\n            mimeType;\n      }\n\n      final url = resolveUrl(rawUrl);\n      if (url == null || !acquisitionUrls.add(url)) return;\n      if (action != 'read' && action != 'download') action = 'download';\n      acquisitionLinks.add(\n        LibraryAcquisitionLink(\n          label: label.isEmpty ? fallbackLabel : label,\n          url: url,\n          action: action,\n          format: format,\n          mimeType: mimeType,\n        ),\n      );\n    }\n\n    addAcquisition(raw['acquisitionLinks']);\n    addAcquisition(raw['downloadUrl']);\n    addAcquisition(raw['downloadUrls']);\n    addAcquisition(\n      raw['epubUrl'],\n      fallbackLabel: 'EPUB',\n      fallbackFormat: 'epub',\n      fallbackMimeType: 'application/epub+zip',\n    );\n    addAcquisition(\n      raw['pdfUrl'],\n      fallbackLabel: 'PDF',\n      fallbackFormat: 'pdf',\n      fallbackMimeType: 'application/pdf',\n    );\n\n    final inlineContent =\n        text(const ['content', 'text', 'body', 'markdown']);\n\n"""
    catalog = replace_once(catalog, anchor, block, label="generic acquisition parsing")
    catalog = replace_once(
        catalog,
        "      pageUrls: List.unmodifiable(pageUrls),\n      raw: Map<String, dynamic>.unmodifiable(raw),",
        "      pageUrls: List.unmodifiable(pageUrls),\n      raw: Map<String, dynamic>.unmodifiable(raw),\n      acquisitionLinks: List.unmodifiable(acquisitionLinks),",
        label="generic acquisitions constructor",
    )

if "Future<String> loadReadableFile(String filePath)" not in catalog:
    insertion = """  Future<String> loadReadableFile(String filePath) async {\n    final file = File(filePath);\n    if (!await file.exists()) {\n      throw const LibraryAddonException('Downloaded Library file no longer exists.');\n    }\n    final bytes = await file.readAsBytes();\n    if (bytes.isEmpty) {\n      throw const LibraryAddonException('Downloaded Library file is empty.');\n    }\n    if (bytes.length > _maxReaderBytes) {\n      throw const LibraryAddonException(\n        'This downloaded item is too large for the integrated text reader.',\n      );\n    }\n\n    final extension = path.extension(file.path).toLowerCase();\n    if (extension == '.epub') {\n      return _decodeEpubText(bytes);\n    }\n    if (extension == '.txt' ||\n        extension == '.md' ||\n        extension == '.html' ||\n        extension == '.htm' ||\n        extension == '.xhtml') {\n      final body = utf8.decode(bytes, allowMalformed: true);\n      final text = _markupToText(body);\n      if (text.isNotEmpty) return text;\n    }\n    throw const LibraryAddonException(\n      'This downloaded format is not supported by the integrated text reader.',\n    );\n  }\n\n"""
    catalog = replace_once(
        catalog,
        "  static List<LibraryCatalogItem> parseGallicaOpdsDocument(",
        insertion + "  static List<LibraryCatalogItem> parseGallicaOpdsDocument(",
        label="offline readable file method",
    )

if "return _decodeEpubText(response.bodyBytes);" not in catalog:
    start = catalog.find("  Future<String> _loadEpubText(Uri uri) async {\n")
    end = catalog.find("  static List<ArchiveFile> _epubReadingOrder(", start)
    if start < 0 or end < 0:
      raise RuntimeError("Could not find EPUB loader block")
    old = catalog[start:end]
    body_start = old.find("    Archive archive;\n")
    if body_start < 0:
      raise RuntimeError("Could not find EPUB archive body")
    archive_body = old[body_start:]
    # Turn the downloaded-response parser into a reusable bytes parser.
    archive_body = archive_body.replace(
        "      archive = ZipDecoder().decodeBytes(response.bodyBytes);",
        "      archive = ZipDecoder().decodeBytes(bytes);",
        1,
    )
    archive_body = archive_body.replace(
        "        'Unable to open the EPUB returned by Gallica.',",
        "        'Unable to open this EPUB.',",
        1,
    )
    new = """  Future<String> _loadEpubText(Uri uri) async {\n    final response = await _get(\n      uri,\n      maxBytes: _maxReaderBytes,\n      accept: 'application/epub+zip, application/octet-stream',\n    );\n    return _decodeEpubText(response.bodyBytes);\n  }\n\n  static String _decodeEpubText(List<int> bytes) {\n""" + archive_body.replace("    Archive archive;\n", "    Archive archive;\n", 1)
    # archive_body closes the original method; it now closes _decodeEpubText.
    catalog = catalog[:start] + new + catalog[end:]

write(catalog_path, catalog)


# ---------------------------------------------------------------------------
# Seven-provider adapter: preserve official acquisition links, no video media.
# ---------------------------------------------------------------------------
provider_path = "lib/services/library_metadata_provider_service.dart"
provider = read(provider_path)

if "googleBooksAcquisitionsFromAccessInfo" not in provider:
    marker = "  Future<List<LibraryCatalogItem>> _searchGoogleBooks(\n"
    helper = """  /// Extracts only official acquisition/read links explicitly returned by\n  /// Google Books. No alternate-copy lookup is performed.\n  static List<LibraryAcquisitionLink> googleBooksAcquisitionsFromAccessInfo(\n    Map<String, dynamic>? accessInfo,\n  ) {\n    if (accessInfo == null) return const <LibraryAcquisitionLink>[];\n    final links = <LibraryAcquisitionLink>[];\n    final seen = <String>{};\n\n    void addDownload(String label, String format, String mimeType, dynamic node) {\n      final map = _asMap(node);\n      if (map == null || map['isAvailable'] != true) return;\n      final url = _https(map['downloadLink']);\n      if (url == null || !seen.add(url)) return;\n      links.add(\n        LibraryAcquisitionLink(\n          label: label,\n          url: url,\n          action: 'download',\n          format: format,\n          mimeType: mimeType,\n        ),\n      );\n    }\n\n    addDownload('EPUB', 'epub', 'application/epub+zip', accessInfo['epub']);\n    addDownload('PDF', 'pdf', 'application/pdf', accessInfo['pdf']);\n\n    final webReader = _https(accessInfo['webReaderLink']);\n    if (webReader != null && seen.add(webReader)) {\n      links.add(\n        LibraryAcquisitionLink(\n          label: 'Google Books',\n          url: webReader,\n          action: 'read',\n        ),\n      );\n    }\n    return List<LibraryAcquisitionLink>.unmodifiable(links);\n  }\n\n"""
    provider = replace_once(provider, marker, helper + marker, label="Google Books acquisition helper")

if "final acquisitions = googleBooksAcquisitionsFromAccessInfo(accessInfo);" not in provider:
    provider = replace_once(
        provider,
        "      final accessInfo = _asMap(raw['accessInfo']);\n      final sourceUrl = _firstHttps(<dynamic>[",
        "      final accessInfo = _asMap(raw['accessInfo']);\n      final acquisitions = googleBooksAcquisitionsFromAccessInfo(accessInfo);\n      final epubDownload = acquisitions\n          .where((link) => link.canDownload && link.format == 'epub')\n          .map((link) => link.url)\n          .firstOrNull;\n      final sourceUrl = _firstHttps(<dynamic>[",
        label="Google Books acquisition extraction",
    )
    provider = replace_once(
        provider,
        "        'webReaderLink': _https(accessInfo?['webReaderLink']),\n      };",
        "        'webReaderLink': _https(accessInfo?['webReaderLink']),\n        'acquisitionLinks': acquisitions.map((link) => link.toJson()).toList(),\n      };",
        label="Google Books normalized acquisitions",
    )
    provider = replace_once(
        provider,
        "          raw: normalized,\n        ),\n      );\n    }\n    return List.unmodifiable(items);\n  }\n\n  LibraryCatalogItem _item({",
        "          raw: normalized,\n          contentUrl: epubDownload,\n          contentType: epubDownload == null ? null : 'application/epub+zip',\n          acquisitionLinks: acquisitions,\n        ),\n      );\n    }\n    return List.unmodifiable(items);\n  }\n\n  LibraryCatalogItem _item({",
        label="Google Books item acquisition args",
    )

if "List<LibraryAcquisitionLink> acquisitionLinks" not in provider:
    provider = replace_once(
        provider,
        "    List<String> authors = const <String>[],\n    String year = '',\n  }) {",
        "    List<String> authors = const <String>[],\n    String year = '',\n    String? contentUrl,\n    String? contentType,\n    List<LibraryAcquisitionLink> acquisitionLinks = const <LibraryAcquisitionLink>[],\n  }) {",
        label="provider item acquisition params",
    )
    provider = replace_once(
        provider,
        "      content: null,\n      contentUrl: null,\n      pageUrls: const <String>[],\n      raw: Map<String, dynamic>.unmodifiable(<String, dynamic>{",
        "      content: null,\n      contentUrl: contentUrl,\n      pageUrls: const <String>[],\n      acquisitionLinks: List<LibraryAcquisitionLink>.unmodifiable(acquisitionLinks),\n      raw: Map<String, dynamic>.unmodifiable(<String, dynamic>{",
        label="provider item acquisition fields",
    )
    provider = replace_once(
        provider,
        "        'metadataOnly': true,\n      }),",
        "        'metadataOnly': true,\n        if (contentType != null && contentType.isNotEmpty) 'contentType': contentType,\n      }),",
        label="provider content type",
    )

write(provider_path, provider)


# ---------------------------------------------------------------------------
# Library UI: source-declared read/download actions only.
# ---------------------------------------------------------------------------
screen_path = "lib/screens/library_screen/library_screen.dart"
screen = read(screen_path)

if "library_download_service.dart" not in screen:
    screen = replace_once(
        screen,
        "import 'package:neostation/services/library_catalog_service.dart';\n",
        "import 'package:neostation/services/library_catalog_service.dart';\n"
        "import 'package:neostation/services/library_download_service.dart';\n",
        label="download service import",
    )
    screen = replace_once(
        screen,
        "import 'package:material_symbols_icons/symbols.dart';\n",
        "import 'package:material_symbols_icons/symbols.dart';\nimport 'package:url_launcher/url_launcher.dart';\n",
        label="url launcher import",
    )
    screen = replace_once(
        screen,
        "import 'library_reader_screen.dart';\n",
        "import 'library_reader_screen.dart';\nimport 'library_pdf_reader_screen.dart';\n",
        label="Library PDF reader import",
    )

old_provider_branch = """    if (_metadataProviderService.isProviderId(entry.providerId)) {\n      final item = entry.item;\n      if (item.pageUrls.isNotEmpty) {\n        await _showPageReader(item.title, item.pageUrls, subtitle: item.subtitle);\n        return;\n      }\n      if ((item.content?.trim().isNotEmpty ?? false) || item.contentUrl != null) {\n        try {\n          final text = await _catalogService.loadReadableText(item);\n          if (!mounted) return;\n          await _showTextReader(item, text);\n        } on LibraryAddonException catch (error) {\n          _showMessage(error.message);\n        }\n        return;\n      }\n\n      final fr = Localizations.localeOf(context).languageCode == 'fr';\n      _showMessage(\n        fr\n            ? 'Cette source ne fournit pas de pages lisibles pour ce titre.'\n            : 'This source does not provide readable pages for this title.',\n      );\n      return;\n    }\n\n"""
if "_openMetadataProviderItem(entry)" not in screen:
    screen = replace_once(
        screen,
        old_provider_branch,
        """    if (_metadataProviderService.isProviderId(entry.providerId)) {\n      await _openMetadataProviderItem(entry);\n      return;\n    }\n\n""",
        label="provider open branch",
    )

if "Future<void> _openMetadataProviderItem" not in screen:
    marker = "  Future<void> _openCatalogItem(_NativeLibraryEntry entry) async {\n"
    helper = r'''  Future<void> _openMetadataProviderItem(_NativeLibraryEntry entry) async {
    final item = entry.item;
    final hasReadable = item.pageUrls.isNotEmpty ||
        (item.content?.trim().isNotEmpty ?? false) ||
        item.contentUrl != null;
    final acquisitions = item.acquisitionLinks;

    if (acquisitions.isEmpty) {
      if (hasReadable) {
        await _readProviderItem(item);
        return;
      }
      final fr = Localizations.localeOf(context).languageCode == 'fr';
      _showMessage(
        fr
            ? 'Cette source ne fournit pas de pages lisibles pour ce titre.'
            : 'This source does not provide readable pages for this title.',
      );
      return;
    }

    final fr = Localizations.localeOf(context).languageCode == 'fr';
    const layerId = 'library_provider_acquisition_dialog';
    GamepadNavigationManager.pushLayer(
      layerId,
      onActivate: () {},
      onDeactivate: () {},
      modal: true,
    );
    String? choice;
    try {
      choice = await showDialog<String>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(item.title),
          content: Text(
            fr
                ? 'Choisis une action proposée directement par la source.'
                : 'Choose an action supplied directly by the source.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(fr ? 'Fermer' : 'Close'),
            ),
            if (hasReadable)
              FilledButton.icon(
                onPressed: () => Navigator.of(dialogContext).pop('read'),
                icon: const Icon(Symbols.menu_book_rounded),
                label: Text(fr ? 'Lire maintenant' : 'Read now'),
              ),
            for (var i = 0; i < acquisitions.length; i++)
              if (acquisitions[i].isExternalReader)
                OutlinedButton.icon(
                  onPressed: () => Navigator.of(dialogContext).pop('external:$i'),
                  icon: const Icon(Symbols.open_in_new_rounded),
                  label: Text(
                    fr
                        ? 'Lire sur ${acquisitions[i].label}'
                        : 'Read on ${acquisitions[i].label}',
                  ),
                )
              else if (acquisitions[i].canDownload)
                FilledButton.tonalIcon(
                  onPressed: () => Navigator.of(dialogContext).pop('download:$i'),
                  icon: const Icon(Symbols.download_rounded),
                  label: Text(
                    '${fr ? 'Télécharger' : 'Download'} ${acquisitions[i].label}',
                  ),
                ),
          ],
        ),
      );
    } finally {
      GamepadNavigationManager.popLayer(layerId);
    }

    if (!mounted || choice == null) return;
    if (choice == 'read') {
      await _readProviderItem(item);
      return;
    }
    final separator = choice.indexOf(':');
    if (separator <= 0) return;
    final index = int.tryParse(choice.substring(separator + 1));
    if (index == null || index < 0 || index >= acquisitions.length) return;
    final acquisition = acquisitions[index];

    if (choice.startsWith('external:')) {
      final uri = Uri.tryParse(acquisition.url);
      if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) return;
      await launchUrl(uri, mode: LaunchMode.externalApplication);
      return;
    }
    if (choice.startsWith('download:')) {
      await _downloadProviderAcquisition(item, acquisition);
    }
  }

  Future<void> _readProviderItem(LibraryCatalogItem item) async {
    if (item.pageUrls.isNotEmpty) {
      await _showPageReader(item.title, item.pageUrls, subtitle: item.subtitle);
      return;
    }
    try {
      final text = await _catalogService.loadReadableText(item);
      if (!mounted) return;
      await _showTextReader(item, text);
    } on LibraryAddonException catch (error) {
      _showMessage(error.message);
    }
  }

  Future<void> _downloadProviderAcquisition(
    LibraryCatalogItem item,
    LibraryAcquisitionLink acquisition,
  ) async {
    final fr = Localizations.localeOf(context).languageCode == 'fr';
    _showMessage(fr ? 'Téléchargement en cours…' : 'Downloading…');
    try {
      final result = await LibraryDownloadService.download(
        acquisition: acquisition,
        title: item.title,
      );
      if (!mounted) return;

      if (result.format == 'epub') {
        try {
          final text = await _catalogService.loadReadableFile(result.filePath);
          if (!mounted) return;
          await _showTextReader(item, text);
          return;
        } on LibraryAddonException catch (error) {
          _showMessage(
            fr
                ? '${result.fileName} téléchargé. ${error.message}'
                : '${result.fileName} downloaded. ${error.message}',
          );
          return;
        }
      }

      if (result.format == 'pdf') {
        await Navigator.of(context).push<void>(
          MaterialPageRoute<void>(
            builder: (_) => LibraryPdfReaderScreen(
              filePath: result.filePath,
              title: item.title,
            ),
          ),
        );
        return;
      }

      _showMessage(
        fr
            ? '${result.fileName} téléchargé dans Library/Downloads.'
            : '${result.fileName} downloaded to Library/Downloads.',
      );
    } catch (error) {
      if (!mounted) return;
      _showMessage(
        fr
            ? 'Téléchargement impossible : $error'
            : 'Download failed: $error',
      );
    }
  }

'''
    screen = replace_once(screen, marker, helper + marker, label="provider acquisition UI")

write(screen_path, screen)

print("Applied source-declared Library acquisition/download integration.")
