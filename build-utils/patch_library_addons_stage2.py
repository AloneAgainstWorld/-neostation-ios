#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise SystemExit(f'Marker not found in {path}: {old[:180]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# App-level controller delegation: B returns from the add-on panel, X removes
# the currently selected source.
replace_once(
    'lib/screens/app_screen.dart',
    '''  void _handleBackNavigation() {\n    if (_selectedTabIndex == AppTabs.scraper) {\n      NewScraperOptionsScreen.backCurrent();\n    }\n  }''',
    '''  void _handleBackNavigation() {\n    if (_selectedTabIndex == AppTabs.scraper) {\n      NewScraperOptionsScreen.backCurrent();\n    } else if (_selectedTabIndex == AppTabs.library) {\n      LibraryScreen.backCurrent();\n    }\n  }''',
)
replace_once(
    'lib/screens/app_screen.dart',
    '''  void _handleXButton() {\n    if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.deleteCurrent();\n    }\n  }''',
    '''  void _handleXButton() {\n    if (_selectedTabIndex == AppTabs.settings) {\n      NewSettingsScreen.deleteCurrent();\n    } else if (_selectedTabIndex == AppTabs.library) {\n      LibraryScreen.deleteCurrent();\n    }\n  }''',
)

# Fix the two int.clamp assignments introduced by the stage-2 Library UI.
replace_once(
    'lib/screens/library_screen/library_screen.dart',
    '''        _addonSelectedIndex = (_addonSelectionCount - 1).clamp(0, 9999);''',
    '''        _addonSelectedIndex = (_addonSelectionCount - 1).clamp(0, 9999).toInt();''',
)
replace_once(
    'lib/screens/library_screen/library_screen.dart',
    '''    _addonSelectedIndex = _addonSelectedIndex.clamp(\n      0,\n      (_addonSelectionCount - 1).clamp(0, 9999),\n    );''',
    '''    _addonSelectedIndex = _addonSelectedIndex\n        .clamp(0, (_addonSelectionCount - 1).clamp(0, 9999).toInt())\n        .toInt();''',
)

# Localization keys.
locale_keys = '''  static const String libraryAddonAddUrl = 'library_addon_add_url';\n  static const String libraryAddonAddUrlSubtitle =\n      'library_addon_add_url_subtitle';\n  static const String libraryAddonImportFile = 'library_addon_import_file';\n  static const String libraryAddonImportFileSubtitle =\n      'library_addon_import_file_subtitle';\n  static const String libraryAddonUrlTitle = 'library_addon_url_title';\n  static const String libraryAddonUrlHelp = 'library_addon_url_help';\n  static const String libraryAddonInstall = 'library_addon_install';\n  static const String libraryAddonInstalling = 'library_addon_installing';\n  static const String libraryAddonInstalled = 'library_addon_installed';\n  static const String libraryAddonUpdated = 'library_addon_updated';\n  static const String libraryAddonError = 'library_addon_error';\n  static const String libraryAddonInstalledSources =\n      'library_addon_installed_sources';\n  static const String libraryAddonRemoveTitle = 'library_addon_remove_title';\n  static const String libraryAddonRemoveBody = 'library_addon_remove_body';\n  static const String libraryAddonRemoved = 'library_addon_removed';\n  static const String libraryAddonCount = 'library_addon_count';\n'''
p = Path('lib/l10n/app_locale.dart')
text = p.read_text(encoding='utf-8')
if 'libraryAddonAddUrl' not in text:
    marker = "  static const String general = 'general';\n"
    if marker not in text:
        raise SystemExit('AppLocale general marker missing')
    text = text.replace(marker, locale_keys + marker, 1)
    p.write_text(text, encoding='utf-8')

translations = {
    'en': [
        'Add source by URL', 'Install a NeoStation manifest hosted on HTTPS.',
        'Import manifest', 'Install a NeoStation add-on from a local JSON file.',
        'Add Library source', 'HTTPS manifest URL (schema neostation.library.v1).',
        'Install', 'Installing source…', 'Installed {name}', 'Updated {name}',
        'Unable to install source: {error}', 'Installed sources',
        'Remove source?', 'Remove {name} from your Library sources?',
        'Removed {name}', '{count} source(s) installed',
    ],
    'fr': [
        'Ajouter par URL', 'Installez un manifeste NeoStation hébergé en HTTPS.',
        'Importer un manifeste', 'Installez un add-on NeoStation depuis un fichier JSON local.',
        'Ajouter une source Bibliothèque', 'URL HTTPS du manifeste (schéma neostation.library.v1).',
        'Installer', 'Installation de la source…', '{name} installé', '{name} mis à jour',
        'Impossible d’installer la source : {error}', 'Sources installées',
        'Supprimer la source ?', 'Supprimer {name} des sources de la Bibliothèque ?',
        '{name} supprimé', '{count} source(s) installée(s)',
    ],
    'es': [
        'Añadir por URL', 'Instala un manifiesto de NeoStation alojado por HTTPS.',
        'Importar manifiesto', 'Instala un add-on de NeoStation desde un archivo JSON local.',
        'Añadir fuente de Biblioteca', 'URL HTTPS del manifiesto (esquema neostation.library.v1).',
        'Instalar', 'Instalando fuente…', '{name} instalado', '{name} actualizado',
        'No se pudo instalar la fuente: {error}', 'Fuentes instaladas',
        '¿Eliminar fuente?', '¿Eliminar {name} de las fuentes de la Biblioteca?',
        '{name} eliminado', '{count} fuente(s) instalada(s)',
    ],
    'de': [
        'Quelle per URL hinzufügen', 'Installiert ein über HTTPS bereitgestelltes NeoStation-Manifest.',
        'Manifest importieren', 'Installiert ein NeoStation-Add-on aus einer lokalen JSON-Datei.',
        'Bibliotheksquelle hinzufügen', 'HTTPS-Manifest-URL (Schema neostation.library.v1).',
        'Installieren', 'Quelle wird installiert…', '{name} installiert', '{name} aktualisiert',
        'Quelle konnte nicht installiert werden: {error}', 'Installierte Quellen',
        'Quelle entfernen?', '{name} aus den Bibliotheksquellen entfernen?',
        '{name} entfernt', '{count} Quelle(n) installiert',
    ],
    'it': [
        'Aggiungi tramite URL', 'Installa un manifesto NeoStation ospitato tramite HTTPS.',
        'Importa manifesto', 'Installa un add-on NeoStation da un file JSON locale.',
        'Aggiungi fonte Libreria', 'URL HTTPS del manifesto (schema neostation.library.v1).',
        'Installa', 'Installazione fonte…', '{name} installato', '{name} aggiornato',
        'Impossibile installare la fonte: {error}', 'Fonti installate',
        'Rimuovere la fonte?', 'Rimuovere {name} dalle fonti della Libreria?',
        '{name} rimosso', '{count} fonte/i installata/e',
    ],
    'pt': [
        'Adicionar por URL', 'Instale um manifesto NeoStation hospedado por HTTPS.',
        'Importar manifesto', 'Instale um add-on NeoStation a partir de um arquivo JSON local.',
        'Adicionar fonte da Biblioteca', 'URL HTTPS do manifesto (esquema neostation.library.v1).',
        'Instalar', 'Instalando fonte…', '{name} instalado', '{name} atualizado',
        'Não foi possível instalar a fonte: {error}', 'Fontes instaladas',
        'Remover fonte?', 'Remover {name} das fontes da Biblioteca?',
        '{name} removido', '{count} fonte(s) instalada(s)',
    ],
    'id': [
        'Tambah lewat URL', 'Pasang manifes NeoStation yang dihosting melalui HTTPS.',
        'Impor manifes', 'Pasang add-on NeoStation dari berkas JSON lokal.',
        'Tambah sumber Perpustakaan', 'URL manifes HTTPS (skema neostation.library.v1).',
        'Pasang', 'Memasang sumber…', '{name} terpasang', '{name} diperbarui',
        'Tidak dapat memasang sumber: {error}', 'Sumber terpasang',
        'Hapus sumber?', 'Hapus {name} dari sumber Perpustakaan?',
        '{name} dihapus', '{count} sumber terpasang',
    ],
    'ru': [
        'Добавить по URL', 'Установить манифест NeoStation, размещённый по HTTPS.',
        'Импортировать манифест', 'Установить дополнение NeoStation из локального JSON-файла.',
        'Добавить источник библиотеки', 'HTTPS URL манифеста (схема neostation.library.v1).',
        'Установить', 'Установка источника…', '{name} установлен', '{name} обновлён',
        'Не удалось установить источник: {error}', 'Установленные источники',
        'Удалить источник?', 'Удалить {name} из источников библиотеки?',
        '{name} удалён', 'Установлено источников: {count}',
    ],
    'ja': [
        'URLから追加', 'HTTPSで公開されたNeoStationマニフェストをインストールします。',
        'マニフェストを読み込む', 'ローカルJSONファイルからNeoStationアドオンをインストールします。',
        'ライブラリソースを追加', 'HTTPSマニフェストURL（スキーマ neostation.library.v1）。',
        'インストール', 'ソースをインストール中…', '{name} をインストールしました', '{name} を更新しました',
        'ソースをインストールできません: {error}', 'インストール済みソース',
        'ソースを削除しますか？', '{name} をライブラリソースから削除しますか？',
        '{name} を削除しました', '{count} 件のソースをインストール済み',
    ],
    'ko': [
        'URL로 추가', 'HTTPS로 호스팅된 NeoStation 매니페스트를 설치합니다.',
        '매니페스트 가져오기', '로컬 JSON 파일에서 NeoStation 애드온을 설치합니다.',
        '라이브러리 소스 추가', 'HTTPS 매니페스트 URL (스키마 neostation.library.v1).',
        '설치', '소스 설치 중…', '{name} 설치됨', '{name} 업데이트됨',
        '소스를 설치할 수 없습니다: {error}', '설치된 소스',
        '소스를 삭제할까요?', '라이브러리 소스에서 {name}을(를) 삭제할까요?',
        '{name} 삭제됨', '{count}개 소스 설치됨',
    ],
    'zh': [
        '通过 URL 添加', '安装通过 HTTPS 托管的 NeoStation 清单。',
        '导入清单', '从本地 JSON 文件安装 NeoStation 插件。',
        '添加资料库来源', 'HTTPS 清单 URL（架构 neostation.library.v1）。',
        '安装', '正在安装来源…', '已安装 {name}', '已更新 {name}',
        '无法安装来源：{error}', '已安装来源',
        '删除来源？', '从资料库来源中删除 {name}？',
        '已删除 {name}', '已安装 {count} 个来源',
    ],
    'zh_hant': [
        '透過 URL 新增', '安裝透過 HTTPS 託管的 NeoStation 清單。',
        '匯入清單', '從本機 JSON 檔案安裝 NeoStation 外掛。',
        '新增資料庫來源', 'HTTPS 清單 URL（架構 neostation.library.v1）。',
        '安裝', '正在安裝來源…', '已安裝 {name}', '已更新 {name}',
        '無法安裝來源：{error}', '已安裝來源',
        '刪除來源？', '從資料庫來源中刪除 {name}？',
        '已刪除 {name}', '已安裝 {count} 個來源',
    ],
}

keys = [
    'libraryAddonAddUrl', 'libraryAddonAddUrlSubtitle', 'libraryAddonImportFile',
    'libraryAddonImportFileSubtitle', 'libraryAddonUrlTitle', 'libraryAddonUrlHelp',
    'libraryAddonInstall', 'libraryAddonInstalling', 'libraryAddonInstalled',
    'libraryAddonUpdated', 'libraryAddonError', 'libraryAddonInstalledSources',
    'libraryAddonRemoveTitle', 'libraryAddonRemoveBody', 'libraryAddonRemoved',
    'libraryAddonCount',
]

for lang, values in translations.items():
    path = Path(f'lib/l10n/app_locale_{lang}.dart')
    text = path.read_text(encoding='utf-8')
    if 'AppLocale.libraryAddonAddUrl:' in text:
        continue
    marker = '  AppLocale.general:'
    pos = text.find(marker)
    if pos < 0:
        raise SystemExit(f'General marker missing in {path}')
    lines = []
    for key, value in zip(keys, values):
        escaped = value.replace('\\', '\\\\').replace("'", "\\'")
        lines.append(f"  AppLocale.{key}: '{escaped}',")
    block = '\n'.join(lines) + '\n'
    text = text[:pos] + block + text[pos:]
    path.write_text(text, encoding='utf-8')

print('Library add-ons stage 2 patch applied')
