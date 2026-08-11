NeoStation iOS — MeloNX metadata/artwork fix

Purpose
-------
Fix imported MeloNX Switch games appearing as TitleID.melonx and make ScreenScraper usable for those virtual entries. Also import MeloNX iconData as local fallback artwork.

Files to replace
----------------
lib/services/melonx_library_service.dart
lib/services/screenscraper_service.dart
lib/data/datasources/sqlite_service.dart

What changes
------------
1. NeoStation displays MeloNX titleName instead of the synthetic TitleID.melonx filename.
2. MeloNX developer metadata is exposed in NeoStation.
3. MeloNX iconData is decoded during Sync and written to:
   Documents/media/switch/box2d/
   Documents/media/switch/screenshots/
   The image bytes are NOT stored in SharedPreferences.
4. ScreenScraper searches MeloNX virtual games by title_name rather than by TitleID.melonx.
5. A successful ScreenScraper scrape is allowed to replace the fallback MeloNX artwork.
6. The direct melonx://game launch flow is unchanged.

Test
----
- Copy this patch over the current project.
- Commit/push with GitHub Desktop and build the IPA.
- Install the new IPA over the existing NeoStation installation.
- Settings > Directories > MeloNX > Re-sync.
- Switch games should now show their MeloNX names.
- melonx_sync_debug.txt should include:
    MeloNX artwork files imported: N
  N may be up to twice the game count because artwork is imported into box2d and screenshots.
- Try scraping one Switch game. The search should use its actual MeloNX title.

If names work but artwork does not appear, send melonx_sync_debug.txt.
