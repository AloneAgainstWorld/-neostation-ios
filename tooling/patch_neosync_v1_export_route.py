from pathlib import Path

provider = Path('lib/providers/neo_sync_provider.dart')
source = provider.read_text(encoding='utf-8')
old = """  Future<List<int>> downloadOnlineFileBytes(NeoSyncFile cloudFile) async {
    final result = await _neoSyncService.downloadFile(cloudFile.id);
    if (result['success'] != true || result['data'] == null) {
      throw Exception(result['message'] ?? 'Failed to download file');
    }
"""
new = """  Future<List<int>> downloadOnlineFileBytes(NeoSyncFile cloudFile) async {
    final result = LegacyNeoSyncService.isLegacyId(cloudFile.id)
        ? await _legacyNeoSyncService.downloadFile(cloudFile.id)
        : await _neoSyncService.downloadFile(cloudFile.id);
    if (result['success'] != true || result['data'] == null) {
      throw Exception(result['message'] ?? 'Failed to download file');
    }
"""
if old not in source:
    raise SystemExit('downloadOnlineFileBytes anchor not found')
source = source.replace(old, new, 1)
provider.write_text(source, encoding='utf-8')

pubspec = Path('pubspec.yaml')
pub = pubspec.read_text(encoding='utf-8')
old_version = 'version: 1.0.0+142'
new_version = 'version: 1.0.0+143'
if old_version not in pub:
    raise SystemExit('expected Beta 1.0 build 142 version not found')
pubspec.write_text(pub.replace(old_version, new_version, 1), encoding='utf-8')
