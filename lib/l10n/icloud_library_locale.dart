import 'package:flutter/widgets.dart';

/// Localized strings for the iCloud ROM library integration.
abstract final class ICloudLibraryLocale {
  static const Map<String, Map<String, String>> _values = {
    'en': {
      'providerSubtitle': 'Remote ROM library',
      'title': 'iCloud Library',
      'subtitle': 'Browse ROMs in iCloud Drive and import only the games you choose.',
      'chooseFolder': 'Choose iCloud folder',
      'changeFolder': 'Change iCloud folder',
      'noFolder': 'Choose the iCloud folder that contains your console folders.',
      'empty': 'No compatible ROMs were found in this iCloud folder.',
      'refresh': 'Refresh',
      'importing': 'Downloading from iCloud…',
      'openIn': 'Send to emulator',
      'switchRule': 'The switch folder is read only at its top level. Subfolders are ignored.',
      'sentMelonx': 'The game was handed to iOS for MeloNX import. MeloNX will resync when you return.',
      'sentArmsx2': 'The game was handed to iOS for ARMSX2 import. ARMSX2 will resync when you return.',
      'sentRetroarch': 'The game was handed to iOS for RetroArch import. Resync RetroArch manually after importing it.',
      'importFailed': 'The game could not be prepared for import.',
      'back': 'Back',
    },
    'fr': {
      'providerSubtitle': 'Bibliothèque ROM distante',
      'title': 'Bibliothèque iCloud',
      'subtitle': 'Parcourir les ROMs dans iCloud Drive et importer uniquement les jeux choisis.',
      'chooseFolder': 'Choisir le dossier iCloud',
      'changeFolder': 'Changer le dossier iCloud',
      'noFolder': 'Choisissez le dossier iCloud qui contient vos dossiers de consoles.',
      'empty': 'Aucune ROM compatible trouvée dans ce dossier iCloud.',
      'refresh': 'Actualiser',
      'importing': 'Téléchargement depuis iCloud…',
      'openIn': 'Envoyer à l’émulateur',
      'switchRule': 'Le dossier switch est lu uniquement à sa racine. Ses sous-dossiers sont ignorés.',
      'sentMelonx': 'Le jeu a été transmis à iOS pour import dans MeloNX. MeloNX sera resynchronisé à votre retour.',
      'sentArmsx2': 'Le jeu a été transmis à iOS pour import dans ARMSX2. ARMSX2 sera resynchronisé à votre retour.',
      'sentRetroarch': 'Le jeu a été transmis à iOS pour import dans RetroArch. Resynchronisez RetroArch manuellement après l’import.',
      'importFailed': 'Le jeu n’a pas pu être préparé pour l’import.',
      'back': 'Retour',
    },
    'de': {
      'providerSubtitle': 'Remote ROM-Bibliothek', 'title': 'iCloud-Bibliothek', 'subtitle': 'ROMs in iCloud Drive durchsuchen und nur ausgewählte Spiele importieren.', 'chooseFolder': 'iCloud-Ordner wählen', 'changeFolder': 'iCloud-Ordner ändern', 'noFolder': 'Wähle den iCloud-Ordner mit deinen Konsolenordnern.', 'empty': 'Keine kompatiblen ROMs in diesem iCloud-Ordner gefunden.', 'refresh': 'Aktualisieren', 'importing': 'Wird aus iCloud geladen…', 'openIn': 'An Emulator senden', 'switchRule': 'Der Ordner switch wird nur auf oberster Ebene gelesen. Unterordner werden ignoriert.', 'sentMelonx': 'Das Spiel wurde iOS zum Import in MeloNX übergeben. MeloNX synchronisiert nach der Rückkehr erneut.', 'sentArmsx2': 'Das Spiel wurde iOS zum Import in ARMSX2 übergeben. ARMSX2 synchronisiert nach der Rückkehr erneut.', 'sentRetroarch': 'Das Spiel wurde iOS zum Import in RetroArch übergeben. RetroArch danach manuell neu synchronisieren.', 'importFailed': 'Das Spiel konnte nicht für den Import vorbereitet werden.', 'back': 'Zurück',
    },
    'es': {
      'providerSubtitle': 'Biblioteca ROM remota', 'title': 'Biblioteca de iCloud', 'subtitle': 'Explora ROMs en iCloud Drive e importa solo los juegos que elijas.', 'chooseFolder': 'Elegir carpeta de iCloud', 'changeFolder': 'Cambiar carpeta de iCloud', 'noFolder': 'Elige la carpeta de iCloud que contiene las carpetas de tus consolas.', 'empty': 'No se encontraron ROMs compatibles en esta carpeta de iCloud.', 'refresh': 'Actualizar', 'importing': 'Descargando desde iCloud…', 'openIn': 'Enviar al emulador', 'switchRule': 'La carpeta switch se lee solo en su nivel superior. Se ignoran las subcarpetas.', 'sentMelonx': 'El juego se entregó a iOS para importarlo en MeloNX. MeloNX se resincronizará al volver.', 'sentArmsx2': 'El juego se entregó a iOS para importarlo en ARMSX2. ARMSX2 se resincronizará al volver.', 'sentRetroarch': 'El juego se entregó a iOS para importarlo en RetroArch. Resincroniza RetroArch manualmente después.', 'importFailed': 'No se pudo preparar el juego para la importación.', 'back': 'Atrás',
    },
    'id': {
      'providerSubtitle': 'Pustaka ROM jarak jauh', 'title': 'Pustaka iCloud', 'subtitle': 'Jelajahi ROM di iCloud Drive dan impor hanya game yang dipilih.', 'chooseFolder': 'Pilih folder iCloud', 'changeFolder': 'Ganti folder iCloud', 'noFolder': 'Pilih folder iCloud yang berisi folder konsol Anda.', 'empty': 'Tidak ada ROM kompatibel ditemukan di folder iCloud ini.', 'refresh': 'Segarkan', 'importing': 'Mengunduh dari iCloud…', 'openIn': 'Kirim ke emulator', 'switchRule': 'Folder switch hanya dibaca pada tingkat teratas. Subfolder diabaikan.', 'sentMelonx': 'Game diserahkan ke iOS untuk diimpor ke MeloNX. MeloNX akan disinkronkan ulang saat kembali.', 'sentArmsx2': 'Game diserahkan ke iOS untuk diimpor ke ARMSX2. ARMSX2 akan disinkronkan ulang saat kembali.', 'sentRetroarch': 'Game diserahkan ke iOS untuk diimpor ke RetroArch. Sinkronkan ulang RetroArch secara manual setelah impor.', 'importFailed': 'Game tidak dapat disiapkan untuk impor.', 'back': 'Kembali',
    },
    'it': {
      'providerSubtitle': 'Libreria ROM remota', 'title': 'Libreria iCloud', 'subtitle': 'Sfoglia le ROM in iCloud Drive e importa solo i giochi scelti.', 'chooseFolder': 'Scegli cartella iCloud', 'changeFolder': 'Cambia cartella iCloud', 'noFolder': 'Scegli la cartella iCloud che contiene le cartelle delle console.', 'empty': 'Nessuna ROM compatibile trovata in questa cartella iCloud.', 'refresh': 'Aggiorna', 'importing': 'Download da iCloud…', 'openIn': 'Invia all’emulatore', 'switchRule': 'La cartella switch viene letta solo al livello principale. Le sottocartelle sono ignorate.', 'sentMelonx': 'Il gioco è stato passato a iOS per l’importazione in MeloNX. MeloNX verrà risincronizzato al ritorno.', 'sentArmsx2': 'Il gioco è stato passato a iOS per l’importazione in ARMSX2. ARMSX2 verrà risincronizzato al ritorno.', 'sentRetroarch': 'Il gioco è stato passato a iOS per l’importazione in RetroArch. Risincronizza RetroArch manualmente dopo l’importazione.', 'importFailed': 'Impossibile preparare il gioco per l’importazione.', 'back': 'Indietro',
    },
    'ja': {
      'providerSubtitle': 'リモートROMライブラリ', 'title': 'iCloudライブラリ', 'subtitle': 'iCloud DriveのROMを閲覧し、選んだゲームだけをインポートします。', 'chooseFolder': 'iCloudフォルダを選択', 'changeFolder': 'iCloudフォルダを変更', 'noFolder': '各コンソールのフォルダを含むiCloudフォルダを選択してください。', 'empty': 'このiCloudフォルダに対応ROMが見つかりません。', 'refresh': '更新', 'importing': 'iCloudからダウンロード中…', 'openIn': 'エミュレータへ送る', 'switchRule': 'switchフォルダは直下のみ読み込み、サブフォルダは無視します。', 'sentMelonx': 'ゲームをMeloNXへインポートするためiOSに渡しました。戻るとMeloNXを再同期します。', 'sentArmsx2': 'ゲームをARMSX2へインポートするためiOSに渡しました。戻るとARMSX2を再同期します。', 'sentRetroarch': 'ゲームをRetroArchへインポートするためiOSに渡しました。インポート後にRetroArchを手動で再同期してください。', 'importFailed': 'ゲームをインポート用に準備できませんでした。', 'back': '戻る',
    },
    'ko': {
      'providerSubtitle': '원격 ROM 라이브러리', 'title': 'iCloud 라이브러리', 'subtitle': 'iCloud Drive의 ROM을 탐색하고 선택한 게임만 가져옵니다.', 'chooseFolder': 'iCloud 폴더 선택', 'changeFolder': 'iCloud 폴더 변경', 'noFolder': '콘솔 폴더가 들어 있는 iCloud 폴더를 선택하세요.', 'empty': '이 iCloud 폴더에서 호환 ROM을 찾지 못했습니다.', 'refresh': '새로 고침', 'importing': 'iCloud에서 다운로드 중…', 'openIn': '에뮬레이터로 보내기', 'switchRule': 'switch 폴더는 최상위 파일만 읽으며 하위 폴더는 무시합니다.', 'sentMelonx': 'MeloNX 가져오기를 위해 게임을 iOS에 전달했습니다. 돌아오면 MeloNX를 다시 동기화합니다.', 'sentArmsx2': 'ARMSX2 가져오기를 위해 게임을 iOS에 전달했습니다. 돌아오면 ARMSX2를 다시 동기화합니다.', 'sentRetroarch': 'RetroArch 가져오기를 위해 게임을 iOS에 전달했습니다. 가져온 후 RetroArch를 수동으로 다시 동기화하세요.', 'importFailed': '게임을 가져오기 위해 준비하지 못했습니다.', 'back': '뒤로',
    },
    'pt': {
      'providerSubtitle': 'Biblioteca ROM remota', 'title': 'Biblioteca iCloud', 'subtitle': 'Explore ROMs no iCloud Drive e importe apenas os jogos escolhidos.', 'chooseFolder': 'Escolher pasta do iCloud', 'changeFolder': 'Alterar pasta do iCloud', 'noFolder': 'Escolha a pasta do iCloud que contém as pastas dos consoles.', 'empty': 'Nenhuma ROM compatível foi encontrada nesta pasta do iCloud.', 'refresh': 'Atualizar', 'importing': 'Baixando do iCloud…', 'openIn': 'Enviar ao emulador', 'switchRule': 'A pasta switch é lida somente no nível superior. Subpastas são ignoradas.', 'sentMelonx': 'O jogo foi entregue ao iOS para importação no MeloNX. O MeloNX será resincronizado ao retornar.', 'sentArmsx2': 'O jogo foi entregue ao iOS para importação no ARMSX2. O ARMSX2 será resincronizado ao retornar.', 'sentRetroarch': 'O jogo foi entregue ao iOS para importação no RetroArch. Resincronize o RetroArch manualmente após importar.', 'importFailed': 'O jogo não pôde ser preparado para importação.', 'back': 'Voltar',
    },
    'ru': {
      'providerSubtitle': 'Удалённая библиотека ROM', 'title': 'Библиотека iCloud', 'subtitle': 'Просматривайте ROM в iCloud Drive и импортируйте только выбранные игры.', 'chooseFolder': 'Выбрать папку iCloud', 'changeFolder': 'Изменить папку iCloud', 'noFolder': 'Выберите папку iCloud с папками ваших консолей.', 'empty': 'В этой папке iCloud не найдено совместимых ROM.', 'refresh': 'Обновить', 'importing': 'Загрузка из iCloud…', 'openIn': 'Отправить в эмулятор', 'switchRule': 'Папка switch читается только на верхнем уровне. Подпапки игнорируются.', 'sentMelonx': 'Игра передана iOS для импорта в MeloNX. После возврата MeloNX будет синхронизирован снова.', 'sentArmsx2': 'Игра передана iOS для импорта в ARMSX2. После возврата ARMSX2 будет синхронизирован снова.', 'sentRetroarch': 'Игра передана iOS для импорта в RetroArch. После импорта синхронизируйте RetroArch вручную.', 'importFailed': 'Не удалось подготовить игру к импорту.', 'back': 'Назад',
    },
    'zh': {
      'providerSubtitle': '远程 ROM 游戏库', 'title': 'iCloud 游戏库', 'subtitle': '浏览 iCloud Drive 中的 ROM，只导入你选择的游戏。', 'chooseFolder': '选择 iCloud 文件夹', 'changeFolder': '更改 iCloud 文件夹', 'noFolder': '请选择包含各主机文件夹的 iCloud 文件夹。', 'empty': '此 iCloud 文件夹中没有找到兼容的 ROM。', 'refresh': '刷新', 'importing': '正在从 iCloud 下载…', 'openIn': '发送到模拟器', 'switchRule': 'switch 文件夹只读取顶层文件，忽略所有子文件夹。', 'sentMelonx': '游戏已交给 iOS 导入 MeloNX。返回后将重新同步 MeloNX。', 'sentArmsx2': '游戏已交给 iOS 导入 ARMSX2。返回后将重新同步 ARMSX2。', 'sentRetroarch': '游戏已交给 iOS 导入 RetroArch。导入后请手动重新同步 RetroArch。', 'importFailed': '无法准备游戏进行导入。', 'back': '返回',
    },
    'zh_Hant': {
      'providerSubtitle': '遠端 ROM 遊戲庫', 'title': 'iCloud 遊戲庫', 'subtitle': '瀏覽 iCloud Drive 中的 ROM，只匯入你選擇的遊戲。', 'chooseFolder': '選擇 iCloud 資料夾', 'changeFolder': '變更 iCloud 資料夾', 'noFolder': '請選擇包含各主機資料夾的 iCloud 資料夾。', 'empty': '此 iCloud 資料夾中找不到相容的 ROM。', 'refresh': '重新整理', 'importing': '正在從 iCloud 下載…', 'openIn': '傳送到模擬器', 'switchRule': 'switch 資料夾只讀取最上層檔案，忽略所有子資料夾。', 'sentMelonx': '遊戲已交給 iOS 匯入 MeloNX。返回後將重新同步 MeloNX。', 'sentArmsx2': '遊戲已交給 iOS 匯入 ARMSX2。返回後將重新同步 ARMSX2。', 'sentRetroarch': '遊戲已交給 iOS 匯入 RetroArch。匯入後請手動重新同步 RetroArch。', 'importFailed': '無法準備遊戲進行匯入。', 'back': '返回',
    },
  };

  static String get(BuildContext context, String key) {
    final locale = Localizations.localeOf(context);
    var code = locale.languageCode;
    if (code == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' || country == 'TW' || country == 'HK' || country == 'MO') {
        code = 'zh_Hant';
      }
    }
    return (_values[code] ?? _values['en']!)[key] ?? _values['en']![key] ?? key;
  }
}
