# diaporama2screen — guide d'utilisation

Monter un diaporama de photographies dont la légende est incrustée dans
l'image, prêt à jouer sur un téléviseur.

Le résultat est un seul fichier MP4 : une clé USB suffit à le lire sur
n'importe quel téléviseur récent, sans ordinateur, sans réseau et sans
lecteur particulier.

Les commandes de ce guide s'exécutent dans un terminal, sur l'ordinateur
où l'application tourne. Elles sont écrites pour une distribution de la
famille Debian — Debian, Ubuntu, Linux Mint — et se transposent sans
difficulté ailleurs : seul le gestionnaire de paquets change.

---

## Ce que produit l'application

Deux choses, dans cet ordre.

**Les images mises en page.** Chaque photographie est redimensionnée à la
résolution du téléviseur et sa légende est écrite en blanc sur un bandeau
noir, sous l'image. La photographie garde ses proportions : ce qui manque
pour remplir le cadre est comblé en noir, de part et d'autre. Le bandeau
occupe au moins un dixième de la hauteur, et s'agrandit si la légende est
longue. Le texte est centré, à une taille de 4 % de la hauteur de l'image —
soit 43 points en HD, 86 en 4K — dans la police DejaVu Sans.

**La vidéo.** Les images défilent avec un fondu croisé entre chacune, une
ouverture depuis le noir au début et une fermeture vers le noir à la fin.
La musique, s'il y en a, est enchaînée bout à bout puis bouclée autant de
fois qu'il le faut pour couvrir la durée, avec un fondu d'entrée de deux
secondes et un fondu de sortie de quatre secondes.

L'encodage est du H.264 à 30 images par seconde en 4:2:0, et du son AAC à
192 kb/s — le format que lisent les téléviseurs, les consoles et les
lecteurs multimédias.

Les images mises en page sont conservées à côté de la vidéo. Elles servent
à vérifier une légende sans tout réencoder, et à tirer un exemplaire sur
papier si besoin.

---

## Installer ce qu'il faut

L'application est écrite en Python et appelle six programmes extérieurs.

```bash
sudo apt install python3-tk python3-pil python3-pil.imagetk \
  libimage-exiftool-perl imagemagick ffmpeg zenity
```

À quoi chacun sert :

- **python3-tk** — la fenêtre elle-même.
- **python3-pil** et **python3-pil.imagetk** — l'affichage des aperçus et
  des vignettes.
- **libimage-exiftool-perl** — lire les légendes dans les photographies, et
  les y écrire.
- **imagemagick** — mettre les images en page avec leur bandeau.
- **ffmpeg** — assembler la vidéo et la musique.
- **zenity** — les fenêtres de choix de fichiers du bureau.

Deux paquets facultatifs, mais utiles :

```bash
sudo apt install wmctrl gettext
```

`wmctrl` permet à l'application de centrer les fenêtres de sélection sur sa
propre fenêtre ; sans lui, le gestionnaire de fenêtres les place où il veut.
`gettext` ne sert qu'à refabriquer les traductions.

L'application vérifie ces programmes à son démarrage et nomme ceux qui
manquent, avec la commande qui les installe. Le menu **Outils ▸ Programmes
requis** refait ce contrôle à tout moment.

---

## Obtenir et lancer l'application

L'application n'a pas d'installateur : c'est un dossier de fichiers Python
qui se lance là où il se trouve.

```bash
git clone https://github.com/lafontaj/diaporama2screen.git
cd diaporama2screen
python3 diaporama2screen.py
```

Pour ne plus avoir à retenir ce chemin, le menu **Outils ▸ Installer un
lanceur…** dépose une icône dans le menu des applications, sous
**Graphisme**, et au choix sur le bureau. Le lanceur retient l'endroit où le
dossier se trouve ; déplacer le dossier demande de le réinstaller. Cinnamon exige qu'un lanceur posé
sur le bureau soit marqué comme fiable ; l'application s'en occupe
elle-même. **Outils ▸ Retirer le lanceur** défait l'opération.

ℹ Le menu des applications met parfois quelques secondes à remarquer un
nouveau lanceur.

---

## La fenêtre

Quatre zones, de haut en bas.

**La barre d'outils** — ajouter des photographies, en retirer, relire les
légendes dans les fichiers, écrire les légendes dans les fichiers.

**La liste** — une ligne par photographie, dans l'ordre où elles passeront.
Chaque ligne porte son rang, son nom de fichier, sa date et sa légende. Les
boutons sous la liste déplacent la photographie choisie, ou trient tout par
nom ou par date.

**L'aperçu** — la photographie choisie dans la liste, et sous elle sa
légende, modifiable.

**Les réglages** — format, durées, musique, dossiers de sortie, et le
bouton qui lance la production.

---

## 1. Ajouter des photographies

Le bouton **Ajouter des photos…** ouvre une planche de vignettes.

Elle se parcourt dossier par dossier : le champ du haut montre le dossier
courant, **Changer…** en choisit un autre, et **Dossier parent** remonte
d'un niveau. **Inclure les sous-dossiers** étend la planche à tout ce qui
se trouve en dessous.

Chaque vignette porte une case à cocher et le nom du fichier. **Tout
sélectionner** et **Tout désélectionner** agissent sur le dossier affiché.

Le point important : **les cases cochées survivent au changement de
dossier.** On peut donc traverser cinq albums, cocher au passage ce qui
convient, et ne valider qu'une fois à la fin. Une ligne sous la planche
rappelle en permanence combien de photographies sont cochées ailleurs. Une
photographie déjà présente dans le diaporama apparaît grisée et ne peut pas
être cochée deux fois.

Les formats reconnus sont `.jpg`, `.jpeg`, `.png`, `.tif` et `.tiff`.

Le chargement des vignettes se fait en arrière-plan, du haut vers le bas :
la planche reste utilisable pendant ce temps, et la molette fait défiler
même si tout n'est pas encore affiché.

---

## 2. Les légendes

C'est le cœur de l'application, et l'endroit où il faut comprendre ce qui
se passe avant d'agir.

### Où la légende est lue

La légende est lue **dans la photographie elle-même**, jamais dans la base
de données d'un catalogueur. Trois champs sont consultés, dans cet ordre,
et le premier qui n'est pas vide gagne :

1. `IPTC:Caption-Abstract`
2. `XMP:Description`
3. `EXIF:ImageDescription`

Ce sont les champs que remplit digiKam quand on saisit une légende. Une
photographie légendée dans digiKam arrive donc dans l'application avec sa
légende déjà en place, sans rien exporter.

La date suit la même logique : `EXIF:DateTimeOriginal`, puis
`EXIF:CreateDate`, puis la date de modification du fichier.

### Modifier une légende

Le champ sous l'aperçu se modifie librement. La modification ne touche
**que le diaporama** : le fichier d'origine n'est pas écrit. Une mention
sous le champ rappelle alors ce que contient encore le fichier, et le
bouton **Restaurer la légende du fichier** revient en arrière.

Cette séparation est volontaire. Une légende convient souvent pour un
diaporama projeté dans un salon et conviendrait mal comme description
permanente de l'original — et l'inverse arrive aussi.

Le bas de la liste compte en permanence combien de légendes sont modifiées
ici seulement.

### Écrire les légendes dans les fichiers

**Destructif.** Cette opération modifie les photographies d'origine.

Elle ne se produit jamais d'elle-même : il faut la demander, soit pour la
photographie choisie avec **Écrire dans le fichier**, soit pour toutes
d'un coup avec **Tout écrire**. Une confirmation s'affiche, qui propose de
conserver une copie de chaque original sous le nom `nom_original`.

Les trois champs sont écrits ensemble, en UTF-8, afin qu'un autre logiciel
retrouve la légende quel que soit celui qu'il consulte.

Le résultat n'est pas tenu pour acquis : après l'écriture, l'application
**relit les fichiers** et compare. Un fichier qui a gardé son ancienne
légende est signalé nommément, plutôt que déclaré réussi parce qu'exiftool
a terminé sans erreur.

⚠ **digiKam ne voit pas le changement tout seul.** Sa base de données garde
l'ancienne légende jusqu'à ce qu'on lui fasse relire les fichiers — par
exemple en lançant une lecture des métadonnées sur l'album concerné. Sans
cela, digiKam affiche l'ancien texte et peut même le réécrire par-dessus le
nouveau.

### Relire les légendes

**Relire les légendes** reprend les légendes dans les fichiers. C'est le
geste à faire après avoir légendé des photographies dans digiKam pendant
qu'un projet était déjà ouvert. Les légendes modifiées dans l'application
sont conservées ; seules celles qui venaient des fichiers sont rafraîchies.

---

## 3. Mettre les photographies en ordre

L'ordre de la liste est l'ordre du diaporama.

Les boutons sous la liste déplacent la photographie choisie : **Haut** et
**Bas** d'un rang, **Début** et **Fin** à l'extrémité. **Trier par nom** et
**Trier par date** réordonnent tout.

Le tri par date s'appuie sur la date lue dans la photographie. Pour des
numérisations d'albums de famille, cette date est souvent celle de la
numérisation et non celle de la prise de vue : le tri par nom de fichier est
alors plus fiable, à condition d'avoir nommé les fichiers en conséquence.

---

## 4. Régler le diaporama

### Format

**HD** donne 1920 × 1080, **4K** donne 3840 × 2160. Le choix fixe la
résolution des images mises en page et celle de la vidéo.

Le 4K ne sert que si les photographies ont la matière pour le remplir. Une
numérisation à 1200 ppp d'un tirage de 10 × 15 cm dépasse largement le 4K
et le justifie ; une photographie de 1500 pixels de large sera simplement
agrandie, sans gain.

### Durées

Trois réglages, en secondes :

- **Secondes par photo** — 10 par défaut. Le temps qu'une photographie
  occupe l'écran, fondu compris.
- **Fondu croisé** — 2 par défaut. La durée du recouvrement entre deux
  photographies.
- **Fondu depuis et vers le noir** — 2 par défaut. L'ouverture au début et
  la fermeture à la fin.

Dix secondes paraissent longues sur un écran d'ordinateur et justes sur un
téléviseur qu'on regarde de loin, surtout quand il y a une légende à lire.

La durée totale s'affiche sous la liste et se recalcule à chaque
changement.

### Musique

**Ajouter des fichiers…** et **Ajouter un dossier…** remplissent la liste ;
**Retirer**, **Haut** et **Bas** la mettent au point. Les morceaux sont
enchaînés dans l'ordre affiché, puis bouclés jusqu'à la fin de la vidéo.

Les formats reconnus sont `.flac`, `.mp3`, `.m4a`, `.ogg`, `.opus` et
`.wav`. Un fichier disparu depuis son ajout est marqué `(manquant)` au lieu
de faire échouer la production.

Sans musique, la vidéo est muette.

### Où les résultats sont écrits

C'est la question qu'on se pose toujours trop tard, donc les deux chemins
sont affichés en clair.

Par défaut, les images vont dans `~/Diaporama/<nom du projet>-1920x1080`
— avec la résolution réelle dans le nom, pour qu'un essai en HD et un
montage final en 4K ne se mélangent pas — et la vidéo dans
`~/Diaporama/<nom du projet>.mp4`.

**Changer…** choisit un autre emplacement, **Automatique** revient au
calcul par défaut.

---

## 5. Produire

**Produire la vidéo** ouvre une fenêtre d'avancement en deux étapes : la
mise en page des images, puis l'encodage de la vidéo. Chacune a sa barre de
progression, et le journal en dessous reçoit ce qui mérite d'être signalé —
une photographie illisible, une légende qu'ImageMagick a refusée.

**Arrêter** interrompt la production après confirmation. Ce qui était déjà
écrit reste sur le disque.

À la fin, **Ouvrir le dossier** affiche le résultat dans le gestionnaire de
fichiers.

Les images produites s'appellent `001_nom.jpg`, `002_nom.jpg`, et ainsi de
suite. Le numéro porte l'ordre du diaporama, ce qui permet de les lire dans
le bon ordre avec n'importe quelle visionneuse.

ℹ Les images numérotées d'une production précédente sont effacées avant
d'en écrire de nouvelles. Sans cela, une photographie retirée du projet
resterait dans le dossier et reviendrait dans la vidéo.

---

## Le fichier de projet

**Fichier ▸ Enregistrer** écrit un fichier `.d2s.json`, par défaut dans
`~/Diaporama/projets`.

Il contient la liste des photographies — leurs chemins, pas leur contenu —,
les légendes modifiées dans l'application, l'ordre, et tous les réglages.
Il ne contient aucune image : c'est une feuille de montage, pas une
archive. Déplacer les photographies d'origine après avoir enregistré un
projet le rend inopérant, et l'application signale alors les fichiers
introuvables au lieu de refuser de s'ouvrir.

Un projet modifié et non enregistré provoque une question à la fermeture,
avec le choix d'enregistrer, de ne pas enregistrer ou de rester.

---

## Où vivent les fichiers

| Quoi | Où |
|---|---|
| Réglages de l'application | `~/.config/diaporama2screen/settings.json` |
| Cache des vignettes | `~/.cache/diaporama2screen` |
| Projets | `~/Diaporama/projets` |
| Images mises en page | `~/Diaporama/<projet>-<largeur>x<hauteur>` |
| Vidéos | `~/Diaporama/<projet>.mp4` |

Rien n'est écrit ailleurs, et aucune de ces destinations n'est obligatoire :
les deux dernières se choisissent projet par projet.

---

## Lire le diaporama sur un téléviseur

Copier le fichier MP4 à la racine d'une clé USB formatée en FAT32 ou en
exFAT, brancher la clé sur le téléviseur, et choisir la source USB.

Le MP4 porte l'attribut `+faststart`, qui place l'index de lecture au début
du fichier. Les lecteurs des téléviseurs commencent ainsi la lecture tout de
suite au lieu de parcourir le fichier entier.

Pour une projection en salle, deux précautions valent le détour : faire
l'essai sur un écran de taille comparable, car une légende lisible sur un
moniteur peut être trop petite sur un grand écran vu de loin ; et emporter
une seconde clé.

---

## Dépannage

**« Des programmes requis sont absents »** — la liste nomme les programmes
et la commande qui les installe. Le menu **Outils ▸ Programmes requis**
refait le contrôle.

**Une photographie n'apparaît pas dans l'aperçu** — le format est
peut-être reconnu par l'extension mais pas lisible, par exemple un TIFF
compressé d'une manière inhabituelle. Le journal de production le signale
et la production continue sans elle.

**« Légende inutilisable »** dans le journal — ImageMagick a refusé de
composer le texte. La photographie est quand même mise en page, sans son
bandeau. Une légende contenant des caractères très inhabituels est la cause
la plus courante.

**La vidéo est muette alors qu'une musique est choisie** — vérifier que les
fichiers ne sont pas marqués `(manquant)` dans la liste.

**La production échoue sans message clair** — relancer l'application depuis
un terminal avec la commande de la section « Obtenir et lancer l'application » : les
messages de ffmpeg et d'ImageMagick s'y affichent en entier.

**digiKam montre encore l'ancienne légende** — lui faire relire les
métadonnées de l'album, comme expliqué plus haut.

**Signaler un défaut** — donner le numéro de version, sans quoi le rapport
est difficile à situer. Il s'affiche dans **Aide ▸ À propos**, et en ligne
de commande :

```bash
python3 diaporama2screen.py --version
```

---

## Changer de langue

Le menu **Langue** offre le français, l'anglais et **Langue du système**,
qui suit la locale de la session. Le choix est retenu d'un lancement à
l'autre, et s'applique aussi aux fenêtres de sélection de fichiers.

Après une modification des textes de l'interface, les catalogues se
refabriquent d'une commande.

```bash
cd diaporama2screen
./build_locales.sh
```

Le script extrait les chaînes des fichiers `.py`, remplit le catalogue
français, signale celles qui n'ont pas de traduction, et compile le
résultat. Les fichiers compilés ne sont pas versionnés : ils se refont de
cette même commande.
