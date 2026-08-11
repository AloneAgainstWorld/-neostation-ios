/// RomM sync provider (community skeleton).
///
/// Connects to a self-hosted RomM instance via its REST API using a
/// user-supplied base URL and API key.
///
/// API reference: https://github.com/rommapp/romm
///
/// ## pubspec.yaml dependencies to add
/// ```yaml
/// http: ^1.2.0   # already present in most Flutter projects
/// ```
///
/// ## Register in main.dart
/// ```dart
/// // Load url + key from SqliteConfigProvider or SharedPreferences first.
/// SyncManager.instance.register(
///   RomMProvider(baseUrl: config.rommUrl, apiKey: config.rommApiKey),
/// );
/// ```
library;

import 'dart:io';
// import 'dart:convert';
// import 'package:http/http.dart' as http;

import '../i_sync_provider.dart';

class RomMProvider extends ISyncProvider {
  static const String kProviderId = 'romm';

  final String? _baseUrl;
  final String? _apiKey;

  SyncProviderStatus _status = SyncProviderStatus.disconnected;
  bool _isAuthenticated = false;
  String? _lastError;

  /// [baseUrl] — user's RomM instance, e.g. "https://romm.example.com".
  /// [apiKey]  — API key from RomM Settings → API Keys.
  RomMProvider({String? baseUrl, String? apiKey})
    : _baseUrl = baseUrl,
      _apiKey = apiKey;

  bool get _isConfigured {
    final url = _baseUrl;
    final key = _apiKey;
    return url != null && url.isNotEmpty && key != null && key.isNotEmpty;
  }

  // ignore: unused_element
  Map<String, String> get _headers => {
    'Authorization': 'Bearer $_apiKey',
    'Accept': 'application/json',
  };

  // ── Identity ───────────────────────────────────────────────────────────────

  @override
  String get providerId => kProviderId;

  @override
  SyncProviderMeta get meta => const SyncProviderMeta(
    id: kProviderId,
    name: 'RomM',
    description:
        'Self-hosted sync via your own RomM instance. Bring your own server.',
    author: 'Community',
    iconAssetPath: 'assets/icons/romm.png',
  );

  @override
  SyncProviderStatus get status => _status;

  @override
  bool get isAuthenticated => _isAuthenticated;

  @override
  String? get lastError => _lastError;

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  @override
  Future<void> initialize() async {
    if (!_isConfigured) return;
    // TODO: Ping $_baseUrl/api/heartbeat (or /api/users/me) to verify
    // the instance is reachable and the key is valid.
    // On HTTP 200 → _status = connected, _isAuthenticated = true.
    // On HTTP 401 → _status = error, _lastError = 'Invalid API key'.
    // On SocketException → _status = error, _lastError = 'Unreachable'.
  }

  @override
  void dispose() {}

  // ── Authentication ─────────────────────────────────────────────────────────

  @override
  Future<SyncResult> login() async {
    if (!_isConfigured) {
      return SyncResult.fail(
        SyncError.configInvalid,
        message: 'Set RomM URL and API Key in Settings → Sync → RomM',
      );
    }
    _status = SyncProviderStatus.connecting;
    try {
      // TODO:
      // final response = await http.get(
      //   Uri.parse('$_baseUrl/api/users/me'),
      //   headers: _headers,
      // );
      // if (response.statusCode == 401) {
      //   throw Exception('Invalid API key');
      // }
      // response.statusCode == 200 → success
      _isAuthenticated = true;
      _status = SyncProviderStatus.connected;
      return SyncResult.ok(message: 'Connected to RomM at $_baseUrl');
    } catch (e) {
      _status = SyncProviderStatus.error;
      _lastError = e.toString();
      return SyncResult.fail(SyncError.networkError, message: e.toString());
    }
  }

  @override
  Future<void> logout() async {
    _isAuthenticated = false;
    _status = SyncProviderStatus.disconnected;
  }

  // ── Core Sync Operations ───────────────────────────────────────────────────

  @override
  Future<SyncResult> uploadSave(
    String gameId,
    File file, {
    String? customFileName,
  }) async {
    // TODO: POST $_baseUrl/api/saves
    // Multipart form-data: file + game_id field.
    // RomM save upload endpoint: POST /api/saves?rom_id={gameId}
    //
    // final request = http.MultipartRequest(
    //   'POST',
    //   Uri.parse('$_baseUrl/api/saves').replace(queryParameters: {'rom_id': gameId}),
    // );
    // request.headers.addAll(_headers);
    // request.files.add(await http.MultipartFile.fromPath('saves', file.path));
    // final response = await request.send();
    throw UnimplementedError('RomMProvider.uploadSave');
  }

  @override
  Future<SyncResult> downloadSave(String gameId, String fileId) async {
    // TODO: GET $_baseUrl/api/saves/{fileId}/download
    // Stream response bytes → write to temp file → SyncResult.data = File.
    throw UnimplementedError('RomMProvider.downloadSave');
  }

  @override
  Future<List<SyncFile>> listSaves({String? gameId}) async {
    // TODO: GET $_baseUrl/api/saves[?rom_id={gameId}]
    // Parse JSON array → List<SyncFile>.
    //
    // final uri = Uri.parse('$_baseUrl/api/saves').replace(
    //   queryParameters: gameId != null ? {'rom_id': gameId} : null,
    // );
    // final response = await http.get(uri, headers: _headers);
    // final List<dynamic> json = jsonDecode(response.body);
    // return json.map((s) => SyncFile(
    //   id: s['id'].toString(),
    //   fileName: s['file_name'],
    //   gameName: s['rom_name'],
    //   fileSize: s['file_size_bytes'] ?? 0,
    //   uploadedAt: DateTime.parse(s['created_at']),
    // )).toList();
    throw UnimplementedError('RomMProvider.listSaves');
  }

  @override
  Future<SyncResult> fullSync() async {
    // TODO: Bidirectional sync based on RomM save metadata timestamps.
    // 1. listSaves() → remote files
    // 2. Scan local save folders → local files
    // 3. Upload local-only / local-newer
    // 4. Download remote-only / remote-newer
    throw UnimplementedError('RomMProvider.fullSync');
  }

  @override
  Future<SyncResult> deleteRemote(String fileId) async {
    // TODO: DELETE $_baseUrl/api/saves/{fileId}
    throw UnimplementedError('RomMProvider.deleteRemote');
  }

  @override
  Future<SyncQuota?> getQuota() async => null;
}
