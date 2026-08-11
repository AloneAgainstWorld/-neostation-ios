part of '../neo_sync_provider.dart';

extension NeoSyncStatus on NeoSyncProvider {
  /// Loads the list of cloud files
  Future<bool> loadFiles() async {
    if (!isNeoSyncAuthenticated) return false;

    _isLoadingOnlineFiles = true;
    _error = null;
    notify();

    try {
      final result = await _neoSyncService.getFiles();

      if (result['success']) {
        _files = result['files'];
        notify();
        return true;
      } else {
        _error = result['message'];
        notify();
        return false;
      }
    } catch (e) {
      _error = 'Error loading files: $e';
      notify();
      return false;
    } finally {
      _isLoadingOnlineFiles = false;
      notify();
    }
  }

  /// Loads the quota information
  Future<bool> loadQuota() async {
    if (!isNeoSyncAuthenticated) return false;

    try {
      final result = await _neoSyncService.getQuota();

      if (result['success']) {
        _quota = result['quota'];
        notify();
        return true;
      } else {
        NeoSyncProvider._log.e('Failed to load quota: ${result['message']}');
        return false;
      }
    } catch (e) {
      NeoSyncProvider._log.e('Error loading quota: $e');
      return false;
    }
  }

  /// Deletes a file
  Future<bool> deleteFile(NeoSyncFile file) async {
    if (!isNeoSyncAuthenticated) return false;

    try {
      final result = await _neoSyncService.deleteFile(file.id);

      if (result['success']) {
        // Remove from local list for immediate response
        _files.removeWhere((f) => f.id == file.id);
        notify();
        return true;
      } else {
        return false;
      }
    } catch (e) {
      return false;
    }
  }

  /// Loads the list of online files for the user (used in NeoSyncContent)
  Future<void> loadOnlineFiles() async {
    _isLoadingOnlineFiles = true;
    notify();

    try {
      final result = await _neoSyncService.getFiles();
      if (result['success']) {
        _onlineFiles = result['files'];
      } else {
        NeoSyncProvider._log.e(
          'Failed to load online files: ${result['message']}',
        );
        _onlineFiles = [];
      }
    } catch (e) {
      NeoSyncProvider._log.e('Error loading online files: $e');
      _onlineFiles = [];
    } finally {
      _isLoadingOnlineFiles = false;
      notify();
    }
  }

  /// Deletes an online file (used in NeoSyncContent)
  Future<bool> deleteOnlineFile(String fileId) async {
    try {
      final result = await _neoSyncService.deleteFile(fileId);
      if (result['success']) {
        // Remove the file from the local list
        _onlineFiles.removeWhere((file) => file.id == fileId);
        notify();
        return true;
      } else {
        NeoSyncProvider._log.e(
          'Failed to delete online file: ${result['message']}',
        );
        return false;
      }
    } catch (e) {
      NeoSyncProvider._log.e('Error deleting online file: $e');
      return false;
    }
  }
}
