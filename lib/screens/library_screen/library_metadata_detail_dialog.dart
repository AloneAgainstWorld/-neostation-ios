import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// Presents metadata-only provider results without pretending that the provider
/// supplies readable chapters or book files.
///
/// Genuine HTTPS trailer/video URLs preserved by the provider adapter are
/// exposed as explicit external actions. NeoStation never fabricates media URLs.
Future<void> showLibraryMetadataDetailDialog(
  BuildContext context, {
  required LibraryCatalogItem item,
  required String providerName,
}) async {
  final locale = Localizations.localeOf(context).languageCode;
  final fr = locale == 'fr';
  final theme = Theme.of(context);

  List<String> stringList(dynamic value) {
    if (value is Iterable && value is! String) {
      return value
          .map((entry) => entry?.toString().trim() ?? '')
          .where((entry) => entry.isNotEmpty && entry != 'null')
          .toList(growable: false);
    }
    final text = value?.toString().trim() ?? '';
    return text.isEmpty || text == 'null' ? const <String>[] : <String>[text];
  }

  String firstValue(List<String> keys) {
    for (final key in keys) {
      final values = stringList(item.raw[key]);
      if (values.isNotEmpty) return values.join(', ');
    }
    return '';
  }

  final metadata = <(String, String)>[
    (
      fr ? 'Auteur(s)' : 'Author(s)',
      firstValue(const <String>['authors', 'author', 'creator']),
    ),
    (
      fr ? 'Éditeur(s)' : 'Publisher(s)',
      firstValue(const <String>['publishers', 'publisher']),
    ),
    (fr ? 'Année' : 'Year', firstValue(const <String>['year'])),
    (fr ? 'Statut' : 'Status', firstValue(const <String>['status'])),
    (fr ? 'Chapitres' : 'Chapters', firstValue(const <String>['chapters'])),
    (fr ? 'Volumes' : 'Volumes', firstValue(const <String>['volumes'])),
    (fr ? 'Note' : 'Score', firstValue(const <String>['score', 'rating'])),
    (
      fr ? 'Genres / sujets' : 'Genres / subjects',
      firstValue(const <String>['genres', 'subjects', 'categories']),
    ),
    (
      fr ? 'Langue(s)' : 'Language(s)',
      firstValue(const <String>['languages', 'language']),
    ),
    ('ISBN', firstValue(const <String>['isbn', 'isbn13', 'isbn10'])),
  ].where((entry) => entry.$2.trim().isNotEmpty).toList(growable: false);

  final sourceUrl = Uri.tryParse(item.raw['sourceUrl']?.toString() ?? '');
  final hasSourceUrl =
      sourceUrl != null && sourceUrl.scheme == 'https' && sourceUrl.host.isNotEmpty;

  Future<void> openExternal(String rawUrl) async {
    final uri = Uri.tryParse(rawUrl);
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  await showDialog<void>(
    context: context,
    builder: (dialogContext) {
      final size = MediaQuery.sizeOf(dialogContext);
      return Dialog(
        insetPadding: EdgeInsets.symmetric(horizontal: 24.r, vertical: 18.r),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: size.width * 0.9,
            maxHeight: size.height * 0.88,
          ),
          child: Padding(
            padding: EdgeInsets.all(18.r),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (item.coverUrl != null)
                      ClipRRect(
                        borderRadius: BorderRadius.circular(10.r),
                        child: Image.network(
                          item.coverUrl!,
                          width: 105.r,
                          height: 150.r,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => SizedBox(
                            width: 105.r,
                            height: 150.r,
                            child: Icon(Symbols.menu_book_rounded, size: 42.r),
                          ),
                        ),
                      ),
                    if (item.coverUrl != null) SizedBox(width: 16.r),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.title,
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          SizedBox(height: 5.r),
                          Text(
                            providerName,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: theme.colorScheme.primary,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          if (item.subtitle.trim().isNotEmpty) ...[
                            SizedBox(height: 5.r),
                            Text(item.subtitle),
                          ],
                          SizedBox(height: 9.r),
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: 9.r,
                              vertical: 5.r,
                            ),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.secondaryContainer,
                              borderRadius: BorderRadius.circular(999.r),
                            ),
                            child: Text(
                              fr ? 'Métadonnées uniquement' : 'Metadata only',
                              style: theme.textTheme.labelMedium?.copyWith(
                                color: theme.colorScheme.onSecondaryContainer,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      onPressed: () => Navigator.of(dialogContext).pop(),
                      icon: const Icon(Symbols.close_rounded),
                    ),
                  ],
                ),
                if (item.description.trim().isNotEmpty) ...[
                  SizedBox(height: 16.r),
                  Flexible(
                    child: SingleChildScrollView(
                      child: Text(
                        item.description,
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                  ),
                ],
                if (metadata.isNotEmpty) ...[
                  SizedBox(height: 14.r),
                  Wrap(
                    spacing: 14.r,
                    runSpacing: 8.r,
                    children: [
                      for (final entry in metadata)
                        ConstrainedBox(
                          constraints: BoxConstraints(maxWidth: 300.r),
                          child: Text.rich(
                            TextSpan(
                              children: [
                                TextSpan(
                                  text: '${entry.$1}: ',
                                  style: const TextStyle(fontWeight: FontWeight.w700),
                                ),
                                TextSpan(text: entry.$2),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
                SizedBox(height: 16.r),
                Text(
                  fr
                      ? 'Cette source enrichit la bibliothèque. Elle ne fournit pas de chapitre ou de téléchargement de livre à NeoStation.'
                      : 'This source enriches the Library. It does not provide NeoStation with chapters or book downloads.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                if (item.videoUrls.isNotEmpty || hasSourceUrl) ...[
                  SizedBox(height: 14.r),
                  Wrap(
                    spacing: 10.r,
                    runSpacing: 8.r,
                    children: [
                      for (var index = 0; index < item.videoUrls.length; index++)
                        FilledButton.icon(
                          onPressed: () => openExternal(item.videoUrls[index]),
                          icon: const Icon(Symbols.play_circle_rounded),
                          label: Text(
                            item.videoUrls.length == 1
                                ? (fr ? 'Vidéo' : 'Video')
                                : '${fr ? 'Vidéo' : 'Video'} ${index + 1}',
                          ),
                        ),
                      if (hasSourceUrl)
                        OutlinedButton.icon(
                          onPressed: () => openExternal(sourceUrl.toString()),
                          icon: const Icon(Symbols.open_in_new_rounded),
                          label: Text(fr ? 'Fiche source' : 'Source page'),
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    },
  );
}
