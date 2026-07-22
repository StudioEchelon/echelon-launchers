# Réduire les faux positifs antivirus

Nos launchers **ne sont pas des virus** — mais un `.exe` PyInstaller non signé est flaggé
à tort par Windows SmartScreen et certains AV. Voici le plan pour que ça tombe.

## ✅ Déjà fait (dans le build)
- **Métadonnées de version** (`version*.txt`) : éditeur « Studio Echelon », nom de produit,
  copyright — un exe anonyme est le déclencheur n°1.
- **Icône** propre par jeu (`.ico`).
- **`--noupx`** : aucun packing (UPX = signal malware massif).
- **`--clean`** : build reproductible → la réputation s'accumule sur le même binaire.

## 🟡 Gratuit, à faire une fois en ligne
1. **Soumettre les faux positifs** aux éditeurs :
   - Microsoft Defender : https://www.microsoft.com/wdsi/filesubmission (choisir « faux positif »)
   - VirusTotal : uploader l'exe, puis contester chaque moteur qui flag.
2. **Réputation SmartScreen** : plus de gens téléchargent depuis la MÊME URL GitHub Releases,
   plus le warning « éditeur inconnu » disparaît tout seul (quelques centaines de dl).
3. **Prévenir les joueurs** : « éditeur inconnu → Informations complémentaires → Exécuter quand même ».

## 🟢 Le vrai fix (payant)
- **Certificat de signature de code** (OV ~70-200 €/an, ou **EV** pour réputation immédiate).
  Signer l'exe = plus de SmartScreen du tout. Étape : `signtool sign /fd sha256 /tr <timestamp> ...`
  à ajouter dans le workflow après le build.

## ❌ Ce qu'on ne fait PAS
Obfuscation, chiffrement de payload, anti-VM, anti-debug : ce sont des techniques de MALWARE.
Les moteurs les détectent comme tel → ça rendrait le launcher PLUS suspect, pas moins.
On reste transparent et identifiable, c'est ça qui marche.
