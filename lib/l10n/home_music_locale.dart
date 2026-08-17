import 'package:flutter/widgets.dart';

/// Localized labels for the fork's main-menu music setting.
abstract final class HomeMusicLocale {
  static const Map<String, String> _titles = {
    'de': 'Musik im Hauptmenü',
    'en': 'Main menu music',
    'es': 'Música del menú principal',
    'fr': 'Musique du menu principal',
    'id': 'Musik menu utama',
    'it': 'Musica del menu principale',
    'ja': 'メインメニューの音楽',
    'ko': '메인 메뉴 음악',
    'pt': 'Música do menu principal',
    'ru': 'Музыка главного меню',
    'zh': '主菜单音乐',
    'zh_Hant': '主選單音樂',
  };

  static const Map<String, String> _subtitles = {
    'de': 'Aktivieren, um eine MP3-, WAV-, OGG- oder FLAC-Datei auszuwählen; sie wird nur im Hauptmenü abgespielt',
    'en': 'Enable to choose an MP3, WAV, OGG or FLAC file; it plays only in the main menu',
    'es': 'Actívalo para elegir un archivo MP3, WAV, OGG o FLAC; solo se reproduce en el menú principal',
    'fr': 'Activer pour choisir un fichier MP3, WAV, OGG ou FLAC ; il sera lu uniquement dans le menu principal',
    'id': 'Aktifkan untuk memilih berkas MP3, WAV, OGG, atau FLAC; hanya diputar di menu utama',
    'it': 'Attiva per scegliere un file MP3, WAV, OGG o FLAC; verrà riprodotto solo nel menu principale',
    'ja': '有効にして MP3、WAV、OGG、FLAC ファイルを選択します。メインメニューでのみ再生されます',
    'ko': '활성화하여 MP3, WAV, OGG 또는 FLAC 파일을 선택하세요. 메인 메뉴에서만 재생됩니다',
    'pt': 'Ative para escolher um arquivo MP3, WAV, OGG ou FLAC; ele será reproduzido apenas no menu principal',
    'ru': 'Включите, чтобы выбрать файл MP3, WAV, OGG или FLAC; он будет воспроизводиться только в главном меню',
    'zh': '启用后选择 MP3、WAV、OGG 或 FLAC 文件；音乐仅在主菜单播放',
    'zh_Hant': '啟用後選擇 MP3、WAV、OGG 或 FLAC 檔案；音樂僅在主選單播放',
  };

  static String title(BuildContext context) => _lookup(_titles, context);
  static String subtitle(BuildContext context) => _lookup(_subtitles, context);

  static String _lookup(Map<String, String> values, BuildContext context) {
    final locale = Localizations.localeOf(context);
    return values[_localeKey(locale)] ?? values['en']!;
  }

  static String _localeKey(Locale locale) {
    if (locale.languageCode == 'zh') {
      final scriptCode = locale.scriptCode?.toLowerCase();
      final countryCode = locale.countryCode?.toUpperCase();
      if (scriptCode == 'hant' ||
          countryCode == 'TW' ||
          countryCode == 'HK' ||
          countryCode == 'MO') {
        return 'zh_Hant';
      }
    }
    return locale.languageCode;
  }
}
