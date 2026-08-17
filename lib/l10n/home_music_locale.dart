import 'package:flutter/widgets.dart';

/// Localized labels for the fork's main-menu ambience setting.
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
    'de': 'Atmosphärische Musik nur im Hauptmenü abspielen',
    'en': 'Play atmospheric music only in the main menu',
    'es': 'Reproducir música ambiental solo en el menú principal',
    'fr': 'Jouer une musique d’ambiance uniquement dans le menu principal',
    'id': 'Putar musik suasana hanya di menu utama',
    'it': 'Riproduci musica d’atmosfera solo nel menu principale',
    'ja': 'メインメニューでのみ雰囲気のある音楽を再生',
    'ko': '메인 메뉴에서만 분위기 음악 재생',
    'pt': 'Reproduzir música ambiente apenas no menu principal',
    'ru': 'Воспроизводить атмосферную музыку только в главном меню',
    'zh': '仅在主菜单播放氛围音乐',
    'zh_Hant': '僅在主選單播放氛圍音樂',
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
