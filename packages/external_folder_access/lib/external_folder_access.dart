import 'dart:io';
import 'package:flutter/services.dart';

/// Thin Dart wrapper around the native iOS folder-bookmark plugin.
///
/// All methods are no-ops (return null) on platforms other than iOS, so
/// call sites don't need to guard on `Platform.isIOS` themselves — on
/// desktop/Android, NeoStation already has real filesystem/SAF access and
/// has no use for this.
class ExternalFolderAccess {
  ExternalFolderAccess._();

  static const MethodChannel _channel = MethodChannel(
    'neostation/external_folder_access',
  );

  /// Presents the system folder picker — which can browse into any app's
  /// exposed "On My iPhone" location, e.g. RetroArch's — and persists a
  /// security-scoped bookmark for the picked folder so it stays accessible
  /// across app relaunches.
  ///
  /// Returns the picked folder's absolute path, or `null` if the user
  /// cancelled, this isn't iOS, or the pick otherwise failed.
  static Future<String?> pickAndBookmarkFolder() async {
    if (!Platform.isIOS) return null;
    try {
      return await _channel.invokeMethod<String>('pickAndBookmarkFolder');
    } on PlatformException {
      return null;
    }
  }

  /// Resolves the previously-bookmarked folder (if any) and starts
  /// security-scoped access to it for this app session.
  ///
  /// Returns the folder's absolute path, or `null` if no folder has been
  /// linked yet (or this isn't iOS).
  static Future<String?> resolveBookmarkedFolder() async {
    if (!Platform.isIOS) return null;
    try {
      return await _channel.invokeMethod<String>('resolveBookmarkedFolder');
    } on PlatformException {
      return null;
    }
  }

  /// Forgets the linked folder. The next call to [resolveBookmarkedFolder]
  /// returns `null` until a new folder is picked via
  /// [pickAndBookmarkFolder].
  static Future<void> clearBookmark() async {
    if (!Platform.isIOS) return;
    try {
      await _channel.invokeMethod<void>('clearBookmark');
    } on PlatformException {
      // Nothing meaningful to recover here — worst case the bookmark
      // lingers and a future resolve attempt fails, which is handled.
    }
  }
}
