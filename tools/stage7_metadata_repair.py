from pathlib import Path

path = Path('lib/services/rpcs3_library_service.dart')
text = path.read_text(encoding='utf-8')

call = "    await _repairPersistedRpcs3Names(games, systemId);\n\n"
call_marker = "    final artworkFiles = await _writeArtwork(artwork);\n"
if call not in text:
    if call_marker not in text:
        raise SystemExit('RPCS3 artwork marker not found')
    text = text.replace(call_marker, call + call_marker, 1)

helper = r"""  static Future<void> _repairPersistedRpcs3Names(
    List<Rpcs3LibraryGame> games,
    String systemId,
  ) async {
    if (games.isEmpty) return;

    final db = await SqliteService.getDatabase();
    final romInfo = await db.rawQuery('PRAGMA table_info(user_roms)');
    final romColumns = romInfo
        .map((row) => row['name']?.toString() ?? '')
        .where((name) => name.isNotEmpty)
        .toSet();
    final metadataInfo = await db.rawQuery(
      'PRAGMA table_info(user_screenscraper_metadata)',
    );
    final metadataColumns = metadataInfo
        .map((row) => row['name']?.toString() ?? '')
        .where((name) => name.isNotEmpty)
        .toSet();

    final romRepairColumns = <String>[
      for (final column in const <String>[
        'real_name',
        'ss_real_name',
        'game_display_name',
      ])
        if (romColumns.contains(column)) column,
    ];
    final metadataRepairColumns = <String>[
      for (final column in const <String>[
        'real_name',
        'ss_real_name',
        'game_display_name',
      ])
        if (metadataColumns.contains(column)) column,
    ];
    final metadataHasFilename = metadataColumns.contains('filename');
    final metadataHasSystem = metadataColumns.contains('app_system_id');

    var repairedValues = 0;
    await db.transaction((txn) async {
      for (final game in games) {
        final titleId = game.titleId.trim().toUpperCase();
        final title = game.title.trim();
        if (titleId.isEmpty || title.isEmpty) continue;
        final normalizedTitle = title.toUpperCase();
        if (normalizedTitle == titleId ||
            normalizedTitle == '$titleId.RPCS3') {
          continue;
        }

        // Always refresh the authoritative local title. This migrates rows
        // created by earlier builds where title_name was only the serial.
        repairedValues += await txn.rawUpdate(
          '''
          UPDATE user_roms
          SET title_name = ?, updated_at = datetime('now')
          WHERE app_system_id = ?
            AND (
              UPPER(TRIM(COALESCE(title_id, ''))) = ?
              OR UPPER(TRIM(filename)) IN (?, ?)
            )
            AND (
              title_name IS NULL
              OR TRIM(title_name) = ''
              OR UPPER(TRIM(title_name)) IN (?, ?)
            )
          ''',
          <Object?>[
            title,
            systemId,
            titleId,
            titleId,
            '$titleId.RPCS3',
            titleId,
            '$titleId.RPCS3',
          ],
        );

        // Some historical databases carried presentation fields directly on
        // user_roms. Only clear values that normalize exactly to the serial.
        for (final column in romRepairColumns) {
          repairedValues += await txn.rawUpdate(
            '''
            UPDATE user_roms
            SET $column = NULL, updated_at = datetime('now')
            WHERE app_system_id = ?
              AND (
                UPPER(TRIM(COALESCE(title_id, ''))) = ?
                OR UPPER(TRIM(filename)) IN (?, ?)
              )
              AND UPPER(
                REPLACE(TRIM(COALESCE($column, '')), '.RPCS3', '')
              ) = ?
            ''',
            <Object?>[
              systemId,
              titleId,
              titleId,
              '$titleId.RPCS3',
              titleId,
            ],
          );
        }

        // Current ScreenScraper metadata is stored in a separate table. Query
        // its schema first because older installations may expose only a subset
        // of these columns.
        if (!metadataHasFilename) continue;
        for (final column in metadataRepairColumns) {
          final systemClause = metadataHasSystem
              ? 'AND app_system_id = ?'
              : '';
          final arguments = <Object?>[
            titleId,
            '$titleId.RPCS3',
            if (metadataHasSystem) systemId,
            titleId,
          ];
          repairedValues += await txn.rawUpdate(
            '''
            UPDATE user_screenscraper_metadata
            SET $column = NULL
            WHERE UPPER(TRIM(filename)) IN (?, ?)
              $systemClause
              AND UPPER(
                REPLACE(TRIM(COALESCE($column, '')), '.RPCS3', '')
              ) = ?
            ''',
            arguments,
          );
        }
      }
    });

    if (repairedValues > 0) {
      _log.i(
        'Rpcs3LibraryService: repaired $repairedValues legacy synthetic '
        'metadata value(s).',
      );
    }
  }

"""
helper_marker = '  static Future<int> _writeArtwork(\n'
if '_repairPersistedRpcs3Names(' not in text[text.find(call_marker):]:
    if helper_marker not in text:
        raise SystemExit('RPCS3 helper insertion marker not found')
    text = text.replace(helper_marker, helper + helper_marker, 1)

path.write_text(text, encoding='utf-8')
print('RPCS3 legacy metadata repair inserted.')
