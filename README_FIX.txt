NeoStation – MeloNX JIT preflight compile fix v3

Ce correctif s'applique PAR-DESSUS le patch "neostation-melonx-prejit-universal-v2".

Il remplace uniquement :
packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift

Cause de l'échec GitHub Actions :
SecTaskCreateFromSelf / SecTaskCopyValueForEntitlement ne sont pas disponibles dans
la cible iOS normale utilisée ici, même s'ils existent dans la famille Security sur
macOS/Mac Catalyst. Xcode arrêtait donc la compilation Swift.

Correction :
- suppression de l'usage de SecTask / Security ;
- détection du suffixe de resign SideStore directement depuis le bundle ID réellement
  installé de NeoStation ;
- le même suffixe est ensuite appliqué à com.stossy11.MeloNX pour construire la cible
  envoyée à StikDebug.

Après installation, tester Super Smash Bros Ultimate puis ouvrir :
Fichiers > Sur mon iPhone > NeoStation > melonx_jit_preflight_debug.txt

Le fichier doit afficher notamment :
NeoStation bundle: ...
Detected sideload suffix: ...
Target effective bundle: ...
StikDebug URL: ...
