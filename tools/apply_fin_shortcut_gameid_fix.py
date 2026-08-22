from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIN = ROOT / "lib/services/fin_library_service.dart"

text = FIN.read_text(encoding="utf-8")

old_virtual = """        final virtualPath = Uri(
          scheme: _virtualScheme,
          host: 'launch',
          queryParameters: <String, String>{
            'system': game.systemFolder,
            'path': game.relativePath,
            'game': game.fileName,
          },
        ).toString();
"""
new_virtual = """        final launchParameters = <String, String>{
          'system': game.systemFolder,
          'path': game.relativePath,
          'game': game.fileName,
        };
        final gameId = game.gameId?.trim();
        if (gameId != null && gameId.isNotEmpty) {
          launchParameters['id'] = gameId;
        }
        final virtualPath = Uri(
          scheme: _virtualScheme,
          host: 'launch',
          queryParameters: launchParameters,
        ).toString();
"""
if old_virtual in text:
    text = text.replace(old_virtual, new_virtual, 1)

old_launch = """  /// Launches a Fin-backed row through the user-created Apple Shortcut. The
  /// input is deliberately the relative path under Fin/Games, not an absolute
  /// app-container path, so it survives Fin updates and reinstalls.
  static Future<bool> launchGameByRomPath(String romPath) async {
    String? relativePath;

    if (isVirtualLibraryPath(romPath)) {
      final uri = Uri.tryParse(romPath);
      relativePath =
          uri?.queryParameters['path'] ?? uri?.queryParameters['game'];
    } else {
      await loadCachedLibrary();
      final normalized = path.basename(romPath).toLowerCase();
      for (final game in _cache ?? const <FinLibraryGame>[]) {
        if (game.fileName.toLowerCase() == normalized) {
          relativePath = game.relativePath;
          break;
        }
      }
    }

    final input = relativePath?.trim();
    if (input == null || input.isEmpty) return false;

    try {
      return await IosShortcutJitLaunchService.run(
        shortcutName: IosShortcutJitLaunchService.finShortcutName,
        input: input.replaceAll('\\\\', '/'),
      );
    } catch (error) {
      _log.e('FinLibraryService: Shortcut launch failed: $error');
      return false;
    }
  }
"""
new_launch = """  /// Launches a Fin-backed row through the user-created Apple Shortcut.
  /// NeoStation passes Fin's Nintendo Game ID (for example RMCP01), because
  /// the Shortcut searches Fin's Game entity by its `ID du jeu` field. Older
  /// Fin rows are upgraded lazily from SQLite/cache so users do not need to
  /// rescan the library just to use the new Shortcut contract.
  static Future<bool> launchGameByRomPath(String romPath) async {
    String? gameId;
    String? relativePath;

    if (isVirtualLibraryPath(romPath)) {
      final uri = Uri.tryParse(romPath);
      gameId = uri?.queryParameters['id']?.trim();
      relativePath =
          uri?.queryParameters['path'] ?? uri?.queryParameters['game'];
    }

    // Rows created before the Game-ID Shortcut contract already store the
    // detected Nintendo ID in user_roms.title_id. Reuse it without requiring
    // the user to relink or resync Fin/Games.
    if (gameId == null || gameId.isEmpty) {
      try {
        final db = await SqliteService.getDatabase();
        final rows = await db.rawQuery(
          'SELECT title_id FROM user_roms WHERE rom_path = ? LIMIT 1',
          [romPath],
        );
        if (rows.isNotEmpty) {
          gameId = rows.first['title_id']?.toString().trim();
        }
      } catch (error) {
        _log.w('FinLibraryService: could not read Game ID from SQLite: $error');
      }
    }

    // Final compatibility fallback: resolve the game from the cached Fin scan
    // by relative path or filename and use the Game ID captured from RVZ/WIA.
    if (gameId == null || gameId.isEmpty) {
      await loadCachedLibrary();
      final normalizedPath = (relativePath ?? romPath)
          .replaceAll('\\\\', '/')
          .toLowerCase();
      final normalizedName = path.basename(romPath).toLowerCase();
      for (final game in _cache ?? const <FinLibraryGame>[]) {
        final cachedRelative = game.relativePath
            .replaceAll('\\\\', '/')
            .toLowerCase();
        if (cachedRelative == normalizedPath ||
            game.fileName.toLowerCase() == normalizedName) {
          gameId = game.gameId?.trim();
          if (gameId != null && gameId.isNotEmpty) break;
        }
      }
    }

    final input = gameId?.trim();
    if (input == null || input.isEmpty) {
      _log.e(
        'FinLibraryService: no Nintendo Game ID available for Shortcut launch: $romPath',
      );
      return false;
    }

    try {
      return await IosShortcutJitLaunchService.run(
        shortcutName: IosShortcutJitLaunchService.finShortcutName,
        input: input,
      );
    } catch (error) {
      _log.e('FinLibraryService: Shortcut launch failed: $error');
      return false;
    }
  }
"""
if old_launch not in text:
    raise RuntimeError("Fin launchGameByRomPath anchor not found")
text = text.replace(old_launch, new_launch, 1)

FIN.write_text(text, encoding="utf-8")
print("Applied Fin Shortcut Nintendo Game ID launch contract.")
