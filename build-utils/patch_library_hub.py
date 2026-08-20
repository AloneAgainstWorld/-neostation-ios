#!/usr/bin/env python3
from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:180]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def insert_after_regex(path: str, pattern: str, addition: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if addition.strip() in text:
        return
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise SystemExit(f'Regex marker not found in {path}: {pattern!r}')
    end = match.end()
    p.write_text(text[:end] + '\n' + addition + text[end:], encoding='utf-8')


# -----------------------------------------------------------------------------
# Top-level tab identity + full-color Library icon.
# -----------------------------------------------------------------------------
nav = 'lib/utils/nav_tabs.dart'
replace_once(
    nav,
    'enum NavTab { systems, search, sync, achievements, scraper, settings }',
    'enum NavTab { systems, search, sync, achievements, scraper, settings, library }',
)
replace_once(
    nav,
    '    this.iconData,\n    this.hidden,',
    '    this.iconData,\n    this.tintIcon = true,\n    this.hidden,',
)
replace_once(
    nav,
    '  /// [AppLocale] key for the tab\'s display name.\n  final String labelKey;',
    '  /// Whether the asset should inherit the active foreground color.\n'
    '  /// Full-color artwork such as the Library manga icon opts out.\n'
    '  final bool tintIcon;\n\n'
    '  /// [AppLocale] key for the tab\'s display name.\n  final String labelKey;',
)
replace_once(
    nav,
    "  NavTab.settings: NavTabSpec(\n    icon: 'assets/images/icons/setting.webp',\n    labelKey: AppLocale.settings,\n  ),\n};",
    "  NavTab.settings: NavTabSpec(\n    icon: 'assets/images/icons/setting.webp',\n    labelKey: AppLocale.settings,\n  ),\n"
    "  NavTab.library: NavTabSpec(\n"
    "    icon: 'assets/images/icons/library-manga.webp',\n"
    "    labelKey: AppLocale.library,\n"
    "    tintIcon: false,\n"
    "  ),\n"
    "};",
)

header = 'lib/widgets/header.dart'
replace_once(
    header,
    '                                        iconData: navTabSpec(tab).iconData,\n                                      ),',
    '                                        iconData: navTabSpec(tab).iconData,\n'
    '                                        tintAsset: navTabSpec(tab).tintIcon,\n'
    '                                      ),',
)
replace_once(
    header,
    '    IconData? iconData,\n  }) {',
    '    IconData? iconData,\n    bool tintAsset = true,\n  }) {',
)
replace_once(
    header,
    ": Image.asset(icon!, color: tint),",
    ": Image.asset(\n                  icon!,\n                  color: tintAsset ? tint : null,\n                  fit: BoxFit.contain,\n                ),",
)

# -----------------------------------------------------------------------------
# AppScreen dispatch and controller delegation. Library is appended so existing
# tab ordinals remain stable.
# -----------------------------------------------------------------------------
app = 'lib/screens/app_screen.dart'
replace_once(
    app,
    "import 'neo_sync_screen/neo_sync_tab.dart';\n",
    "import 'neo_sync_screen/neo_sync_tab.dart';\nimport 'library_screen/library_screen.dart';\n",
)
replace_once(
    app,
    '  static const int settings = 5;\n\n  /// Total number of tabs, used for wrap-around when cycling with the bumpers.\n  static const int count = 6;',
    '  static const int settings = 5;\n  static const int library = 6;\n\n  /// Total number of tabs, used for wrap-around when cycling with the bumpers.\n  static const int count = 7;',
)
replace_once(
    app,
    '    if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.navigateRight();\n      return;\n    }\n  }',
    '    if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.navigateRight();\n      return;\n    }\n'
    '    if (_selectedTabIndex == AppTabs.library) {\n      LibraryScreen.navigateRight();\n      return;\n    }\n'
    '  }',
)
replace_once(
    app,
    '    if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.navigateLeft();\n      return;\n    }\n  }',
    '    if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.navigateLeft();\n      return;\n    }\n'
    '    if (_selectedTabIndex == AppTabs.library) {\n      LibraryScreen.navigateLeft();\n      return;\n    }\n'
    '  }',
)
replace_once(
    app,
    '    if (_selectedTabIndex == AppTabs.settings) {\n      return NewSettingsScreen.navigateDown();\n    }\n    return true;',
    '    if (_selectedTabIndex == AppTabs.settings) {\n      return NewSettingsScreen.navigateDown();\n    }\n'
    '    if (_selectedTabIndex == AppTabs.library) {\n      return LibraryScreen.navigateDown();\n    }\n'
    '    return true;',
)
replace_once(
    app,
    '    if (_selectedTabIndex == AppTabs.settings) {\n      return NewSettingsScreen.navigateUp();\n    }\n    return true;',
    '    if (_selectedTabIndex == AppTabs.settings) {\n      return NewSettingsScreen.navigateUp();\n    }\n'
    '    if (_selectedTabIndex == AppTabs.library) {\n      return LibraryScreen.navigateUp();\n    }\n'
    '    return true;',
)
replace_once(
    app,
    '    } else if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.selectCurrent();\n    }\n  }',
    '    } else if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.selectCurrent();\n'
    '    } else if (_selectedTabIndex == AppTabs.library) {\n      LibraryScreen.selectCurrent();\n'
    '    }\n  }',
)
replace_once(
    app,
    "        case AppTabs.settings:\n          tabName = 'Settings';\n          break;\n      }",
    "        case AppTabs.settings:\n          tabName = 'Settings';\n          break;\n"
    "        case AppTabs.library:\n          tabName = 'Library';\n          break;\n"
    "      }",
)
replace_once(
    app,
    '      case AppTabs.settings:\n        return NewSettingsScreen();\n      default:',
    '      case AppTabs.settings:\n        return NewSettingsScreen();\n'
    '      case AppTabs.library:\n        return const LibraryScreen();\n'
    '      default:',
)

# -----------------------------------------------------------------------------
# Localization keys.
# -----------------------------------------------------------------------------
locale_core = 'lib/l10n/app_locale.dart'
keys_block = """  static const String library = 'library';
  static const String libraryIntro = 'library_intro';
  static const String libraryAddons = 'library_addons';
  static const String libraryAddonsSubtitle = 'library_addons_subtitle';
  static const String libraryLocal = 'library_local';
  static const String libraryLocalSubtitle = 'library_local_subtitle';
  static const String libraryEmptyTitle = 'library_empty_title';
  static const String libraryEmptySubtitle = 'library_empty_subtitle';
  static const String libraryNextStep = 'library_next_step';"""
insert_after_regex(
    locale_core,
    r"^  static const String settings = 'settings';$",
    keys_block,
)

translations = {
    'en': {
        'library': 'Library',
        'libraryIntro': 'Add sources and keep all your reading content in one place.',
        'libraryAddons': 'Add-ons',
        'libraryAddonsSubtitle': 'Add external sources to expand your library.',
        'libraryLocal': 'Local library',
        'libraryLocalSubtitle': 'Your PDF, CBZ and other local content.',
        'libraryEmptyTitle': 'No source installed yet',
        'libraryEmptySubtitle': 'Add an add-on or a local source to get started.',
        'libraryNextStep': 'This section will be enabled in the next step.',
    },
    'fr': {
        'library': 'Bibliothèque',
        'libraryIntro': 'Ajoutez des sources et rassemblez tous vos contenus de lecture au même endroit.',
        'libraryAddons': 'Add-ons',
        'libraryAddonsSubtitle': 'Ajoutez des sources externes pour enrichir votre bibliothèque.',
        'libraryLocal': 'Bibliothèque locale',
        'libraryLocalSubtitle': 'Vos PDF, CBZ et autres contenus locaux.',
        'libraryEmptyTitle': 'Aucune source installée pour le moment',
        'libraryEmptySubtitle': 'Ajoutez un add-on ou une source locale pour commencer.',
        'libraryNextStep': 'Cette section sera activée à la prochaine étape.',
    },
    'es': {
        'library': 'Biblioteca',
        'libraryIntro': 'Añade fuentes y reúne todo tu contenido de lectura en un solo lugar.',
        'libraryAddons': 'Complementos',
        'libraryAddonsSubtitle': 'Añade fuentes externas para ampliar tu biblioteca.',
        'libraryLocal': 'Biblioteca local',
        'libraryLocalSubtitle': 'Tus PDF, CBZ y otros contenidos locales.',
        'libraryEmptyTitle': 'Aún no hay fuentes instaladas',
        'libraryEmptySubtitle': 'Añade un complemento o una fuente local para empezar.',
        'libraryNextStep': 'Esta sección se habilitará en el siguiente paso.',
    },
    'ru': {
        'library': 'Библиотека',
        'libraryIntro': 'Добавляйте источники и храните весь контент для чтения в одном месте.',
        'libraryAddons': 'Дополнения',
        'libraryAddonsSubtitle': 'Добавляйте внешние источники, чтобы расширить библиотеку.',
        'libraryLocal': 'Локальная библиотека',
        'libraryLocalSubtitle': 'Ваши PDF, CBZ и другой локальный контент.',
        'libraryEmptyTitle': 'Источники пока не установлены',
        'libraryEmptySubtitle': 'Добавьте дополнение или локальный источник, чтобы начать.',
        'libraryNextStep': 'Этот раздел будет включён на следующем этапе.',
    },
    'zh': {
        'library': '资料库',
        'libraryIntro': '添加来源，将所有阅读内容集中在一个地方。',
        'libraryAddons': '扩展源',
        'libraryAddonsSubtitle': '添加外部来源以扩充资料库。',
        'libraryLocal': '本地资料库',
        'libraryLocalSubtitle': '你的 PDF、CBZ 和其他本地内容。',
        'libraryEmptyTitle': '尚未安装来源',
        'libraryEmptySubtitle': '添加扩展源或本地来源即可开始。',
        'libraryNextStep': '此功能将在下一阶段启用。',
    },
    'zh_hant': {
        'library': '資料庫',
        'libraryIntro': '加入來源，將所有閱讀內容集中在同一處。',
        'libraryAddons': '擴充來源',
        'libraryAddonsSubtitle': '加入外部來源以擴充資料庫。',
        'libraryLocal': '本機資料庫',
        'libraryLocalSubtitle': '你的 PDF、CBZ 與其他本機內容。',
        'libraryEmptyTitle': '尚未安裝來源',
        'libraryEmptySubtitle': '加入擴充來源或本機來源即可開始。',
        'libraryNextStep': '此功能將在下一階段啟用。',
    },
    'pt': {
        'library': 'Biblioteca',
        'libraryIntro': 'Adicione fontes e reúna todo o seu conteúdo de leitura em um só lugar.',
        'libraryAddons': 'Complementos',
        'libraryAddonsSubtitle': 'Adicione fontes externas para ampliar sua biblioteca.',
        'libraryLocal': 'Biblioteca local',
        'libraryLocalSubtitle': 'Seus PDFs, CBZs e outros conteúdos locais.',
        'libraryEmptyTitle': 'Nenhuma fonte instalada ainda',
        'libraryEmptySubtitle': 'Adicione um complemento ou uma fonte local para começar.',
        'libraryNextStep': 'Esta seção será ativada na próxima etapa.',
    },
    'de': {
        'library': 'Bibliothek',
        'libraryIntro': 'Füge Quellen hinzu und sammle alle Leseinhalte an einem Ort.',
        'libraryAddons': 'Add-ons',
        'libraryAddonsSubtitle': 'Füge externe Quellen hinzu, um deine Bibliothek zu erweitern.',
        'libraryLocal': 'Lokale Bibliothek',
        'libraryLocalSubtitle': 'Deine PDF-, CBZ- und anderen lokalen Inhalte.',
        'libraryEmptyTitle': 'Noch keine Quelle installiert',
        'libraryEmptySubtitle': 'Füge ein Add-on oder eine lokale Quelle hinzu, um zu beginnen.',
        'libraryNextStep': 'Dieser Bereich wird im nächsten Schritt aktiviert.',
    },
    'it': {
        'library': 'Biblioteca',
        'libraryIntro': 'Aggiungi fonti e raccogli tutti i contenuti di lettura in un solo posto.',
        'libraryAddons': 'Componenti aggiuntivi',
        'libraryAddonsSubtitle': 'Aggiungi fonti esterne per ampliare la tua biblioteca.',
        'libraryLocal': 'Biblioteca locale',
        'libraryLocalSubtitle': 'I tuoi PDF, CBZ e altri contenuti locali.',
        'libraryEmptyTitle': 'Nessuna fonte installata',
        'libraryEmptySubtitle': 'Aggiungi un componente o una fonte locale per iniziare.',
        'libraryNextStep': 'Questa sezione sarà attivata nel prossimo passaggio.',
    },
    'id': {
        'library': 'Perpustakaan',
        'libraryIntro': 'Tambahkan sumber dan kumpulkan semua konten bacaan di satu tempat.',
        'libraryAddons': 'Add-on',
        'libraryAddonsSubtitle': 'Tambahkan sumber eksternal untuk memperluas perpustakaan.',
        'libraryLocal': 'Perpustakaan lokal',
        'libraryLocalSubtitle': 'PDF, CBZ, dan konten lokal lainnya.',
        'libraryEmptyTitle': 'Belum ada sumber terpasang',
        'libraryEmptySubtitle': 'Tambahkan add-on atau sumber lokal untuk memulai.',
        'libraryNextStep': 'Bagian ini akan diaktifkan pada tahap berikutnya.',
    },
    'ja': {
        'library': 'ライブラリ',
        'libraryIntro': 'ソースを追加して、すべての読書コンテンツを1か所にまとめます。',
        'libraryAddons': 'アドオン',
        'libraryAddonsSubtitle': '外部ソースを追加してライブラリを拡張します。',
        'libraryLocal': 'ローカルライブラリ',
        'libraryLocalSubtitle': 'PDF、CBZなどのローカルコンテンツです。',
        'libraryEmptyTitle': 'まだソースがありません',
        'libraryEmptySubtitle': 'アドオンまたはローカルソースを追加して開始してください。',
        'libraryNextStep': 'このセクションは次のステップで有効になります。',
    },
    'ko': {
        'library': '라이브러리',
        'libraryIntro': '소스를 추가하고 모든 읽기 콘텐츠를 한곳에 모아 보세요.',
        'libraryAddons': '애드온',
        'libraryAddonsSubtitle': '외부 소스를 추가해 라이브러리를 확장합니다.',
        'libraryLocal': '로컬 라이브러리',
        'libraryLocalSubtitle': 'PDF, CBZ 및 기타 로컬 콘텐츠입니다.',
        'libraryEmptyTitle': '아직 설치된 소스가 없습니다',
        'libraryEmptySubtitle': '애드온 또는 로컬 소스를 추가해 시작하세요.',
        'libraryNextStep': '이 섹션은 다음 단계에서 활성화됩니다.',
    },
}

key_order = [
    'library',
    'libraryIntro',
    'libraryAddons',
    'libraryAddonsSubtitle',
    'libraryLocal',
    'libraryLocalSubtitle',
    'libraryEmptyTitle',
    'libraryEmptySubtitle',
    'libraryNextStep',
]


def dart_quote(value: str) -> str:
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


for locale, values in translations.items():
    locale_path = f'lib/l10n/app_locale_{locale}.dart'
    text = Path(locale_path).read_text(encoding='utf-8')
    if 'AppLocale.libraryIntro:' in text:
        continue
    match = re.search(r"^  AppLocale.settings: .*,$", text, flags=re.MULTILINE)
    if match is None:
        raise SystemExit(f'Settings translation marker not found in {locale_path}')
    block = '\n'.join(
        f'  AppLocale.{key}: {dart_quote(values[key])},' for key in key_order
    )
    end = match.end()
    Path(locale_path).write_text(text[:end] + '\n' + block + text[end:], encoding='utf-8')

print('Library hub patch applied')
