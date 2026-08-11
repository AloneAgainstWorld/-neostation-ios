NeoStation — MeloNX ScreenScraper image-path fix
=================================================

Cause identified
----------------
MeloNX virtual games use synthetic filenames such as:
  010028600ebda000.melonx

NeoStation's ScreenScraper media downloader removes the extension before writing
artwork, so downloaded files are named for example:
  media/switch/box2d/010028600ebda000.png
  media/switch/screenshots/010028600ebda000.png
  media/switch/wheels/010028600ebda000.png

But FileProvider did NOT strip the synthetic `.melonx` suffix because it is
longer than the generic 4-character fallback. The UI therefore searched for:
  010028600ebda000.melonx.png

Metadata/descriptions were saved correctly because they live in SQLite and do
not depend on the artwork filename. This is why descriptions appeared while
scraped images did not.

Fix
---
`melonx` is now treated as a NeoStation virtual ROM extension by FileProvider,
so write-time and read-time media keys are identical.

`armsx2` is included for the same reason, preventing the same mismatch for
virtual ARMSX2 library entries.

Installation
------------
Copy the contents of this ZIP to the root of the current NeoStation repository,
accept the replacement of:
  lib/providers/file_provider.dart

Then commit/push with GitHub Desktop and build/install the new IPA over the
existing NeoStation app.

After installation
------------------
1. Open NeoStation.
2. Check a Switch game that has already been scraped. Artwork already downloaded
   under the extensionless Title ID should now become visible.
3. If some artwork type is genuinely still missing, run Scrape again for that
   game. No MeloNX re-sync is required for this path fix.

The older MeloNX-exported fallback icon files remain usable because GameModel
already has an original-filename fallback lookup.
