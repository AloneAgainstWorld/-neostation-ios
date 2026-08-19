from pathlib import Path

path = Path(
    "lib/screens/settings_screen/new_settings_options/directories_settings_content.dart"
)
text = path.read_text(encoding="utf-8")

section_start = text.find("  Widget _buildIOSRpcs3Section(ThemeData theme) {")
section_end = text.find("\n  /// ARMSX2 is sync-only", section_start)
if section_start < 0 or section_end < 0:
    raise SystemExit("RPCS3 settings section not found")

section = text[section_start:section_end]
old_start = section.find("      trailingAction: Row(\n")
if old_start < 0:
    # Already patched is a valid state for repeatable build pipelines.
    if "onPressed: _configureRpcs3Launch" not in section:
        print("RPCS3 Shortcut configuration button is already absent.")
        raise SystemExit(0)
    raise SystemExit("RPCS3 trailing action layout not found")

old_end_marker = "      ),\n    );\n  }\n"
old_end = section.rfind(old_end_marker)
if old_end < 0 or old_end <= old_start:
    raise SystemExit("RPCS3 trailing action end marker not found")

# Consume only the closing line of the old trailingAction Row. Keep the
# enclosing _buildIOSEmulatorCard close and method close untouched.
old_end += len("      ),\n")

replacement = """      trailingAction: SizedBox(
        height: 48.r,
        child: FilledButton.icon(
          onPressed: !isLinked ? null : _syncWithRpcs3,
          icon: Icon(Symbols.sync_rounded, size: 20.r),
          label: Text(
            hasSynced
                ? AppLocale.iosEmuResync.getString(context)
                : AppLocale.iosEmuSync.getString(context),
            style: TextStyle(fontSize: 14.r),
          ),
        ),
      ),
"""

new_section = section[:old_start] + replacement + section[old_end:]
if "onPressed: _configureRpcs3Launch" in new_section:
    raise SystemExit("RPCS3 Shortcut button survived the patch")
if "onPressed: !isLinked ? null : _syncWithRpcs3" not in new_section:
    raise SystemExit("RPCS3 sync button was not preserved")

text = text[:section_start] + new_section + text[section_end:]
path.write_text(text, encoding="utf-8")
print("Removed RPCS3 Configure Launch/Shortcut button; folder + sync remain.")
