NeoStation iOS — ARMSX2 library import v2
=========================================

Base attendue
-------------
Ce patch est prévu APRES le premier patch "neostation-armsx2-sync-patch".
Il remplace 4 fichiers existants.

Installation
------------
1. Décompresser le ZIP.
2. Copier le dossier lib/ à la racine du dépôt NeoStation.
3. Accepter le remplacement des 4 fichiers.
4. Vérifier les modifications dans GitHub Desktop.
5. Commit + Push.
6. Construire l'IPA via GitHub Actions et installer/tester.

Ce que corrige v2
-----------------
- RetroArch et ARMSX2 utilisent un seul dossier ROM partagé.
- Le bouton ARMSX2 Sync n'effectue plus un scan de dossier pour créer la PS2.
- La bibliothèque exportée par ARMSX2 est importée directement dans la base
  NeoStation comme système PS2.
- Si NeoStation connaît déjà le fichier PS2 physiquement, sa ligne existante
  est conservée.
- Sinon, NeoStation crée une ligne virtuelle dont rom_path est le deeplink
  armsx2://launch?... exporté par ARMSX2.
- Ces lignes virtuelles ne sont pas supprimées par un Rescan All classique.
- Un jeu PS2 virtuel se lance directement dans ARMSX2 sans test File.exists().

Diagnostic de synchro
---------------------
Après avoir appuyé sur ARMSX2 > Sync, regarder dans :
  Fichiers > Sur mon iPhone > NeoStation > armsx2_sync_debug.txt

Valeurs importantes :
- STATE: REQUESTED
  => NeoStation a bien ouvert ARMSX2, mais aucun callback n'est revenu.
- STATE: CALLBACK_RECEIVED
  => ARMSX2 a rappelé NeoStation mais l'import n'est pas encore validé.
- STATE: IMPORTED
  => le payload a été reçu et la bibliothèque PS2 a été écrite dans NeoStation.

Quand STATE: IMPORTED est présent, le fichier indique aussi :
- ARMSX2 games
- NeoStation virtual PS2 rows
- Existing physical PS2 rows reused
- PS2 rows now in NeoStation

Important
---------
Si le fichier reste sur STATE: REQUESTED après le retour manuel dans NeoStation,
le problème n'est plus le scan NeoStation : la version ARMSX2 installée n'a pas
renvoyé neostation://armsx2?...&payload=...
