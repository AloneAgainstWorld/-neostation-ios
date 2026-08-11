NeoStation – correctif callback MeloNX gameInfo

Diagnostic:
Le fichier melonx_sync_debug.txt montrait :
  STATE: REQUESTED
  Request URL: melonx://gameinfo?scheme=neostation

Le handler MeloNX testé attend exactement le host camelCase "gameInfo".
Dart Uri normalise le host en minuscules, donc le deeplink ouvrait MeloNX mais
n'entrait pas dans le handler d'export et aucun callback n'était envoyé.

Correctif:
- NeoStation transmet maintenant la chaîne brute
  melonx://gameInfo?scheme=neostation
  à un petit opener natif iOS (UIApplication.shared.open).
- Le chemin ne passe plus par Dart Uri sur iOS, ce qui évite gameInfo -> gameinfo.
- Le callback reste : neostation://melonx?games=<base64url>

Installation:
Copier le contenu de ce dossier à la racine du projet NeoStation et accepter
le remplacement des 3 fichiers, puis Commit/Push dans GitHub Desktop et rebâtir l'IPA.

Test:
Settings > Directories > MeloNX > Sync.
Puis vérifier Fichiers > Sur mon iPhone > NeoStation > melonx_sync_debug.txt.
Résultat attendu : CALLBACK_RECEIVED puis IMPORTED.
