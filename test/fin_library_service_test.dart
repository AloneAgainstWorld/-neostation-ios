import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/fin_library_service.dart';

void main() {
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('neostation_fin_test_');
  });

  tearDown(() async {
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  test('classifies GameCube RVZ from WIA header 2 disc_type', () async {
    final file = File('${tempDir.path}/Wind Waker.rvz');
    await file.writeAsBytes(
      _rvzHeader(
        discType: 1,
        gameId: 'GZLE01',
        title: 'The Legend of Zelda: The Wind Waker',
      ),
    );

    final game = await FinLibraryService.inspectGameFile(file.path);

    expect(game, isNotNull);
    expect(game!.systemFolder, 'gc');
    expect(game.gameId, 'GZLE01');
    expect(game.title, 'The Legend of Zelda: The Wind Waker');
  });

  test('classifies Wii RVZ from WIA header 2 disc_type', () async {
    final file = File('${tempDir.path}/Mario Kart Wii.rvz');
    await file.writeAsBytes(
      _rvzHeader(
        discType: 2,
        gameId: 'RMCE01',
        title: 'Mario Kart Wii',
      ),
    );

    final game = await FinLibraryService.inspectGameFile(file.path);

    expect(game, isNotNull);
    expect(game!.systemFolder, 'wii');
    expect(game.gameId, 'RMCE01');
    expect(game.title, 'Mario Kart Wii');
  });

  test('classifies uncompressed disc images from standard magic', () async {
    final bytes = Uint8List(0x80);
    final data = ByteData.sublistView(bytes);
    data.setUint32(0x1c, 0xc2339f3d, Endian.big);
    _writeAscii(bytes, 0, 'GM8E01');
    _writeAscii(bytes, 0x20, 'Metroid Prime');

    final file = File('${tempDir.path}/Metroid Prime.iso');
    await file.writeAsBytes(bytes);

    final game = await FinLibraryService.inspectGameFile(file.path);

    expect(game, isNotNull);
    expect(game!.systemFolder, 'gc');
    expect(game.gameId, 'GM8E01');
    expect(game.title, 'Metroid Prime');
  });
}

Uint8List _rvzHeader({
  required int discType,
  required String gameId,
  required String title,
}) {
  final bytes = Uint8List(0xd8);
  bytes.setRange(0, 4, const [0x52, 0x56, 0x5a, 0x01]);
  final data = ByteData.sublistView(bytes);
  data.setUint32(0x48, discType, Endian.big);

  const discHeader = 0x58;
  _writeAscii(bytes, discHeader, gameId);
  _writeAscii(bytes, discHeader + 0x20, title);
  return bytes;
}

void _writeAscii(Uint8List target, int offset, String value) {
  final encoded = ascii.encode(value);
  target.setRange(offset, offset + encoded.length, encoded);
}
