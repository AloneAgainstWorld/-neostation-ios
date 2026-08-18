from pathlib import Path

path = Path('lib/screens/settings_screen/new_settings_options/directories_settings_content.dart')
text = path.read_text(encoding='utf-8')

method_anchor = '''  Future<void> _linkRpcs3DataFolder() async {\n'''
method = '''  Future<void> _configureRpcs3Launch() async {\n    final opened =\n        await IosShortcutJitLaunchService.openRpcs3ShortcutInstaller();\n    if (!mounted || opened) return;\n\n    AppNotification.showNotification(\n      context,\n      AppLocale.shortcutSetupOpenError.getString(context),\n      type: NotificationType.error,\n    );\n  }\n\n'''
if '_configureRpcs3Launch()' not in text:
    if method_anchor not in text:
        raise SystemExit('RPCS3 configure method anchor not found')
    text = text.replace(method_anchor, method + method_anchor, 1)

old = '''      trailingAction: SizedBox(\n        height: 48.r,\n        child: FilledButton.icon(\n          onPressed: !isLinked ? null : _syncWithRpcs3,\n          icon: Icon(Symbols.sync_rounded, size: 20.r),\n          label: Text(\n            hasSynced\n                ? AppLocale.iosEmuResync.getString(context)\n                : AppLocale.iosEmuSync.getString(context),\n            style: TextStyle(fontSize: 14.r),\n          ),\n        ),\n      ),\n'''
new = '''      trailingAction: Row(\n        children: [\n          Expanded(\n            child: SizedBox(\n              height: 48.r,\n              child: FilledButton.icon(\n                onPressed: !isLinked ? null : _syncWithRpcs3,\n                icon: Icon(Symbols.sync_rounded, size: 20.r),\n                label: Text(\n                  hasSynced\n                      ? AppLocale.iosEmuResync.getString(context)\n                      : AppLocale.iosEmuSync.getString(context),\n                  style: TextStyle(fontSize: 14.r),\n                ),\n              ),\n            ),\n          ),\n          SizedBox(width: 10.r),\n          Expanded(\n            child: SizedBox(\n              height: 48.r,\n              child: OutlinedButton.icon(\n                onPressed: _configureRpcs3Launch,\n                icon: Icon(Symbols.rocket_launch_rounded, size: 20.r),\n                label: Text(\n                  AppLocale.configureLaunch.getString(context),\n                  maxLines: 1,\n                  overflow: TextOverflow.ellipsis,\n                  style: TextStyle(fontSize: 13.r),\n                ),\n              ),\n            ),\n          ),\n        ],\n      ),\n'''
if 'onPressed: _configureRpcs3Launch' not in text:
    if old not in text:
        raise SystemExit('RPCS3 trailing action anchor not found')
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
