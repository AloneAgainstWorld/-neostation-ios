NeoStation - MeloNX explicit StikDebug preflight (v2)

But du test
===========
Ne plus lancer le jeu avant que StikDebug ait eu le temps d'attacher son
script JIT. NeoStation demande d'abord explicitement le JIT pour MeloNX via
StikDebug, attend 8 secondes, puis envoie UNE SEULE fois le deeplink du jeu.

Flux attendu
============
NeoStation -> StikDebug -> MeloNX/JIT + universal.js -> attente 8 s -> jeu

Aucune modification de MeloNX ou StikDebug n'est necessaire.

Le bundle ID MeloNX n'est pas lie a un Team ID personnel dans le code.
NeoStation lit son Team ID signe sur l'iPhone et, lorsqu'il detecte un bundle
resigne de type SideStore/AltStore, construit automatiquement :
  com.stossy11.MeloNX.<TEAM_ID>
Sinon il conserve :
  com.stossy11.MeloNX

Test recommande
===============
1. Copier ces fichiers a la racine du projet en remplacant les existants.
2. Commit + Push avec GitHub Desktop.
3. Build GitHub Actions.
4. Installer par-dessus NeoStation avec SideStore.
5. Lancer directement Super Smash Bros Ultimate depuis NeoStation.
6. Ne rien toucher pendant environ 10 secondes.

Diagnostic
==========
Fichiers > Sur mon iPhone > NeoStation > melonx_jit_preflight_debug.txt

Sequence attendue :
STATE: PREFLIGHT_REQUESTED
STATE: BACKGROUND_TASK_STARTED
STATE: PREFLIGHT_OPENED
STATE: GAME_LAUNCH_SCHEDULED
STATE: GAME_LAUNCH_ATTEMPT
STATE: GAME_LAUNCH_OPENED

Le fichier affiche aussi le Bundle ID NeoStation, le Team ID detecte et le
Bundle ID MeloNX effectivement envoye a StikDebug.
