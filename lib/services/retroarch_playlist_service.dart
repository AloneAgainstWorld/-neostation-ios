import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:neostation/services/config_service.dart';
import 'package:neostation/services/logger_service.dart';

/// Manipulates RetroArch's own playlist files (`.lpl`, JSON-formatted) to
/// enable a genuine one-tap launch on iOS.
///
/// Background: RetroArch's external integration points on iOS were all
/// tested and found not to accept a specific game as external input — the
/// Siri/Shortcuts "Play Game" action always falls back to its own picker
/// regardless of what's passed to it, confirmed by repeated on-device
/// testing. However, RetroArch also exposes a *parameter-less* "Resume Last
/// Game" Shortcuts action, which plays whatever sits at the front of
/// `content_history.lpl`. Since NeoStation has write access to RetroArch's
/// own folder (see ConfigService.linkedExternalFolderPath +
/// external_folder_access), it can make a specific game "the last one
/// played" itself, then trigger that parameter-less action.
///
/// Rather than constructing a playlist entry from scratch (which would mean
/// guessing at RetroArch's exact `db_name`/`core_path`/`crc32` conventions),
/// this copies the entry RetroArch itself already created when it scanned
/// the ROM into one of its per-system playlists — that entry is guaranteed
/// to be in a format RetroArch understands, since RetroArch wrote it.
class RetroArchPlaylistService {
  RetroArchPlaylistService._();

  static final _log = LoggerService.instance;

  static const String _historyFileName = 'content_history.lpl';
  static const Set<String> _skipFileNames = {
    'content_history.lpl',
    'content_image_history.lpl',
    'content_music_history.lpl',
    'content_video_history.lpl',
    'favorites.lpl',
  };

  /// Finds [romPath]'s existing entry in one of RetroArch's per-system
  /// playlists and copies it to the very front of `content_history.lpl`.
  ///
  /// Returns `true` if a matching entry was found and the history playlist
  /// was successfully updated — i.e. RetroArch's "Resume Last Game" action
  /// should now play this exact game. Returns `false` if nothing could be
  /// done (no linked RetroArch folder, ROM not yet scanned by RetroArch
  /// itself, or an I/O error) — callers should fall back to another launch
  /// path in that case rather than trigger "Resume Last Game" blind.
  static Future<bool> setAsMostRecent(String romPath) async {
    final root = ConfigService.linkedExternalFolderPath;
    if (root == null) return false;

    final playlistsDir = Directory(path.join(root, 'playlists'));
    if (!await playlistsDir.exists()) {
      _log.w('RetroArchPlaylistService: no playlists/ folder under $root');
      return false;
    }

    Map<String, dynamic>? matchingEntry;

    try {
      await for (final entity in playlistsDir.list()) {
        if (entity is! File || !entity.path.endsWith('.lpl')) continue;
        final name = path.basename(entity.path);
        if (_skipFileNames.contains(name)) continue;

        try {
          final decoded = jsonDecode(await entity.readAsString());
          if (decoded is! Map<String, dynamic>) continue;
          final items = decoded['items'];
          if (items is! List) continue;

          for (final item in items) {
            if (item is Map<String, dynamic> && item['path'] == romPath) {
              matchingEntry = Map<String, dynamic>.from(item);
              break;
            }
          }
        } catch (e) {
          // One corrupt/unreadable playlist file shouldn't stop the search
          // through the rest of them.
          _log.w('RetroArchPlaylistService: skipped unreadable ${entity.path}: $e');
          continue;
        }
        if (matchingEntry != null) break;
      }
    } catch (e) {
      _log.e('RetroArchPlaylistService: failed listing playlists/: $e');
      return false;
    }

    if (matchingEntry == null) {
      _log.w(
        'RetroArchPlaylistService: no existing playlist entry found for '
        '$romPath — RetroArch may not have scanned this folder yet.',
      );
      return false;
    }

    final historyFile = File(path.join(root, 'playlists', _historyFileName));
    Map<String, dynamic> history;
    if (await historyFile.exists()) {
      try {
        final decoded = jsonDecode(await historyFile.readAsString());
        if (decoded is! Map<String, dynamic>) {
          _log.e('RetroArchPlaylistService: $_historyFileName is not a JSON object');
          return false;
        }
        history = decoded;
      } catch (e) {
        _log.e('RetroArchPlaylistService: failed to parse $_historyFileName: $e');
        return false;
      }
    } else {
      // Minimal-but-valid shell, matching the fields seen in RetroArch's
      // own generated playlists — used only if content_history.lpl doesn't
      // exist yet (e.g. the user has never played anything via RetroArch's
      // own UI).
      history = {
        'version': '1.5',
        'default_core_path': '',
        'default_core_name': '',
        'label_display_mode': 0,
        'right_thumbnail_mode': 0,
        'left_thumbnail_mode': 0,
        'thumbnail_match_mode': 0,
        'sort_mode': 0,
        'items': <dynamic>[],
      };
    }

    final historyItems = (history['items'] as List?)?.toList() ?? <dynamic>[];
    historyItems.removeWhere(
      (item) => item is Map<String, dynamic> && item['path'] == romPath,
    );
    historyItems.insert(0, matchingEntry);
    history['items'] = historyItems;

    try {
      await historyFile.writeAsString(jsonEncode(history));
      return true;
    } catch (e) {
      _log.e('RetroArchPlaylistService: failed writing $_historyFileName: $e');
      return false;
    }
  }
}
