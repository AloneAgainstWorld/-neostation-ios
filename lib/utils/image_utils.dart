import 'package:path/path.dart' as path;

/// Utility functions for image file processing and validation.
class ImageUtils {
  /// Checks if the file at the given [filePath] is a GIF based on its extension.
  static bool isGif(String? filePath) {
    if (filePath == null || filePath.isEmpty) return false;
    final extension = path.extension(filePath).toLowerCase();
    return extension == '.gif';
  }
}
