#!/usr/bin/env python3
"""
traduire_fr.py — Remplit le catalogue français à partir du modèle .pot.

Lit locale/diaporama2screen.pot, associe à chaque chaîne sa traduction, et
écrit locale/fr/LC_MESSAGES/diaporama2screen.po. Les chaînes sans traduction
sont signalées et restent vides : gettext retombe alors sur l'anglais, donc
rien ne casse.

Les msgid sur plusieurs lignes sont recollés avant la recherche, de sorte que
la table ci-dessous se lit comme du texte ordinaire.
"""
__version__ = "1.0.0"

import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
POT = os.path.join(ICI, "diaporama2screen.pot")
PO = os.path.join(ICI, "fr", "LC_MESSAGES", "diaporama2screen.po")

FR = {
    # deps.py
    "Some required programs are missing:":
        "Des programmes nécessaires sont absents :",
    "Install them with:": "Installez-les avec :",
    "reading the captions": "lire les légendes",
    "laying out the images": "mettre les images en page",
    "measuring the caption band": "mesurer le bandeau de légende",
    "encoding the video": "encoder la vidéo",
    "inspecting the music files": "examiner les fichiers de musique",

    # launcher.py
    "The desktop folder could not be found.":
        "Le dossier du bureau est introuvable.",

    # metadata.py
    "the file still holds its old caption":
        "le fichier porte encore son ancienne légende",

    # render.py
    "No DejaVu font found; captions will use the ImageMagick default.":
        "Aucune police DejaVu trouvée ; les légendes utiliseront la police "
        "par défaut d'ImageMagick.",
    "Laying out the images": "Mise en page des images",
    "Caption unusable for {name}": "Légende inutilisable pour {name}",
    "Could not read {name}": "Lecture impossible : {name}",
    "Joining {n} pieces of music": "Assemblage de {n} pièces musicales",
    "The music could not be joined; the video will be silent.":
        "La musique n'a pas pu être assemblée ; la vidéo sera muette.",
    "Encoding the video": "Encodage de la vidéo",
    "No image could be produced.": "Aucune image n'a pu être produite.",

    # ui_dialogs.py
    "Choose a folder": "Choisir un dossier",
    "Add photos": "Ajouter des photos",
    "Images": "Images",
    "All files": "Tous les fichiers",
    "Add music files": "Ajouter des fichiers de musique",
    "Audio files": "Fichiers audio",
    "Open": "Ouvrir",
    "Save as": "Enregistrer sous",
    "The file “{f}” already exists. Replace it?":
        "Le fichier « {f} » existe déjà. Le remplacer ?",
    "Replace": "Remplacer",
    "OK": "OK",
    "Yes": "Oui",
    "Cancel": "Annuler",
    "Save": "Enregistrer",
    "Discard": "Abandonner",

    # ui_main.py — menus
    "New project": "Nouveau projet",
    "Open…": "Ouvrir…",
    "Save as…": "Enregistrer sous…",
    "Quit": "Quitter",
    "File": "Fichier",
    "System language": "Langue du système",
    "Language": "Langue",
    "Install a launcher…": "Installer un lanceur…",
    "Remove the launcher": "Retirer le lanceur",
    "Required programs": "Programmes nécessaires",
    "Tools": "Outils",
    "About": "À propos",
    "Help": "Aide",

    # ui_main.py — barre d'outils et liste
    "Add photos…": "Ajouter des photos…",
    "Remove from the slideshow": "Retirer du diaporama",
    "Re-read the captions": "Relire les légendes",
    "Write captions into the files…":
        "Écrire les légendes dans les fichiers…",
    "Caption": "Légende",
    "Top": "Début",
    "Up": "Monter",
    "Down": "Descendre",
    "Bottom": "Fin",
    "Sort by name": "Trier par nom",
    "Sort by date": "Trier par date",
    "Select a photo to see it here.":
        "Sélectionnez une photo pour la voir ici.",
    "Restore the file's caption": "Rétablir la légende du fichier",
    "Write into the file": "Écrire dans le fichier",
    "file not found": "fichier introuvable",
    "Empty slideshow. Add a folder or some photos to begin.":
        "Diaporama vide. Ajoutez un dossier ou des photos pour commencer.",
    "{n} photos": "{n} photos",
    "{n} with a caption": "{n} avec légende",
    "{n} edited here only": "{n} modifiées ici seulement",
    "{n} missing files": "{n} fichiers manquants",
    "duration {d}": "durée {d}",
    "This file no longer exists.": "Ce fichier n'existe plus.",
    "This photo cannot be displayed:\n{reason}":
        "Cette photo ne peut pas être affichée :\n{reason}",
    "no date": "sans date",
    "Edited here only. In the file: {text}":
        "Modifiée ici seulement. Dans le fichier : {text}",
    "(none)": "(aucune)",
    "Read from the file.": "Lue dans le fichier.",
    "This photo has no caption in its metadata.":
        "Cette photo ne porte aucune légende dans ses métadonnées.",
    "This caption is already the one in the file. There is nothing to write.":
        "Cette légende est déjà celle du fichier. Il n'y a rien à écrire.",
    "No caption has been edited here, so there is nothing to write.":
        "Aucune légende n'a été modifiée ici, il n'y a rien à écrire.",
    "Write this caption into the photograph itself?\n\n{name}\n{caption}":
        "Écrire cette légende dans la photographie elle-même ?"
        "\n\n{name}\n{caption}",
    "(empty)": "(vide)",
    "Write {n} captions into the photographs themselves?":
        "Écrire {n} légendes dans les photographies elles-mêmes ?",
    "The files are modified. digiKam will show the new captions once it "
    "re-reads them.":
        "Les fichiers sont modifiés. digiKam affichera les nouvelles légendes "
        "dès qu'il les relira.",
    "Keep a copy of each original file (name_original)":
        "Conserver une copie de chaque fichier d'origine (nom_original)",
    "Write into the files": "Écrire dans les fichiers",
    "Write": "Écrire",
    "{ok} captions written, {bad} failed:\n{detail}":
        "{ok} légendes écrites, {bad} en échec :\n{detail}",
    "{n} captions written into the files.":
        "{n} légendes écrites dans les fichiers.",
    "Choose the photos to add": "Choisir les photos à ajouter",
    "Nothing added: those photos are already in the slideshow, or are not "
    "images.":
        "Rien d'ajouté : ces photos sont déjà dans le diaporama, ou ne sont "
        "pas des images.",
    "None of these photos can be read.":
        "Aucune de ces photos n'est lisible.",
    "{n} files are missing and will be left out. Continue?":
        "{n} fichiers sont manquants et seront laissés de côté. Continuer ?",
    "Continue": "Continuer",
    "“{f}” already exists. Replace it?":
        "« {f} » existe déjà. Le remplacer ?",
    "The laid-out images go to:\n{images}\n\nThe video goes to:\n{video}\n\n"
    "Numbered images already in that folder are replaced.":
        "Les images mises en page vont dans :\n{images}\n\nLa vidéo va "
        "dans :\n{video}\n\nLes images numérotées déjà présentes dans ce "
        "dossier sont remplacées.",
    "Produce": "Produire",
    "Produce the video": "Produire la vidéo",
    "untitled": "sans titre",
    "This project has unsaved changes. Save it now?":
        "Ce projet comporte des modifications non enregistrées. "
        "L'enregistrer maintenant ?",
    "Open a project": "Ouvrir un projet",
    "Slideshow projects": "Projets de diaporama",
    "This project could not be opened:\n{reason}":
        "Ce projet n'a pas pu être ouvert :\n{reason}",
    "Save the project": "Enregistrer le projet",
    "slideshow": "diaporama",
    "This project could not be saved:\n{reason}":
        "Ce projet n'a pas pu être enregistré :\n{reason}",
    "The language will change the next time the application starts.":
        "La langue changera au prochain démarrage de l'application.",
    "Every required program is installed.":
        "Tous les programmes nécessaires sont installés.",
    "{app}\n\nBuild a photo slideshow with captions burnt into the image, "
    "ready to play on a television.":
        "{app}\n\nMonter un diaporama photo avec la légende incrustée dans "
        "l'image, prêt à jouer sur un téléviseur.",
    "Put diaporama2screen in the Graphics group of the menu, and a launcher "
    "on the desktop?":
        "Placer diaporama2screen dans le groupe Graphisme du menu, et un "
        "lanceur sur le bureau ?",
    "An existing launcher will be replaced.":
        "Un lanceur existant sera remplacé.",
    "Also put a launcher on the desktop":
        "Poser aussi un lanceur sur le bureau",
    "Install a launcher": "Installer un lanceur",
    "Install": "Installer",
    "Launcher installed:": "Lanceur installé :",
    "The menu may take a moment to notice it.":
        "Le menu peut mettre un instant à s'en apercevoir.",
    "Launcher removed:": "Lanceur retiré :",
    "No launcher was installed.": "Aucun lanceur n'était installé.",

    # ui_picker.py
    "Folder:": "Dossier :",
    "Change…": "Changer…",
    "Parent folder": "Dossier parent",
    "Include subfolders": "Inclure les sous-dossiers",
    "Select all": "Tout cocher",
    "Select none": "Tout décocher",
    "Add": "Ajouter",
    "No image in this folder.": "Aucune image dans ce dossier.",
    "already in the slideshow": "déjà dans le diaporama",
    "unreadable": "illisible",
    "{here} of {shown} in this folder":
        "{here} sur {shown} dans ce dossier",
    "Add {n} photos": "Ajouter {n} photos",
    "{n} photos ticked in other folders are kept.":
        "{n} photos cochées dans d'autres dossiers sont conservées.",

    # ui_render.py
    "Producing the slideshow": "Production du diaporama",
    "Starting…": "Démarrage…",
    "Open the folder": "Ouvrir le dossier",
    "{done} of {total}": "{done} sur {total}",
    "Close": "Fermer",
    "Finished": "Terminé",
    "Written to: {path}": "Écrit dans : {path}",
    "Stopped": "Interrompu",
    "Nothing more was written.": "Rien de plus n'a été écrit.",
    "Failed": "Échec",
    "See the detail below.": "Voir le détail ci-dessous.",
    "Stop the production now?": "Interrompre la production maintenant ?",
    "Stop": "Interrompre",
    "Keep going": "Poursuivre",
    "Stopping…": "Interruption…",

    # ui_settings.py
    "Format:": "Format :",
    "Seconds per photo:": "Secondes par photo :",
    "Cross-fade:": "Fondu enchaîné :",
    "Fade from and to black:": "Fondus au noir :",
    "Music": "Musique",
    "Add files…": "Ajouter des fichiers…",
    "Add a folder…": "Ajouter un dossier…",
    "Remove": "Retirer",
    "Where the results are written": "Où les résultats sont écrits",
    "Images:": "Images :",
    "Automatic": "Automatique",
    "Video:": "Vidéo :",
    "Add a music folder": "Ajouter un dossier de musique",
    "(missing)": "(manquant)",
    "No music: the video will be silent.":
        "Aucune musique : la vidéo sera muette.",
    "{n} pieces, played in this order then looped.":
        "{n} pièces, jouées dans cet ordre puis bouclées.",
    "Folder for the laid-out images": "Dossier des images mises en page",
    "Where to write the video": "Où écrire la vidéo",
    "Video": "Vidéo",
    "  (automatic)": "  (automatique)",
    "No photo in the slideshow yet.":
        "Aucune photo dans le diaporama pour l'instant.",
    "{n} photos — {duration} of video":
        "{n} photos — {duration} de vidéo",
}

EN_TETE = '''# Catalogue français de diaporama2screen.
# Les chaînes sources sont en anglais ; ce fichier est produit par
# locale/traduire_fr.py puis compilé par build_locales.sh.
msgid ""
msgstr ""
"Project-Id-Version: diaporama2screen\\n"
"Language: fr\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=2; plural=(n > 1);\\n"

'''


def echapper(texte):
    """Le texte tel qu'il s'écrit entre guillemets dans un .po."""
    return (texte.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\t", "\\t"))


def desechapper(texte):
    return (texte.replace('\\n', "\n").replace('\\t', "\t")
            .replace('\\"', '"').replace("\\\\", "\\"))


def lire_msgids(chemin):
    """Les msgid du modèle, recollés quand ils tiennent sur plusieurs lignes,
    dans l'ordre du fichier."""
    with open(chemin, "r", encoding="utf-8") as f:
        lignes = f.read().splitlines()
    msgids = []
    courant = None
    for ligne in lignes:
        if ligne.startswith("msgid "):
            courant = [re.findall(r'"(.*)"', ligne)[0]]
        elif courant is not None and ligne.startswith('"'):
            courant.append(re.findall(r'"(.*)"', ligne)[0])
        elif courant is not None:
            msgids.append(desechapper("".join(courant)))
            courant = None
    if courant is not None:
        msgids.append(desechapper("".join(courant)))
    return [m for m in msgids if m]


def main():
    if not os.path.isfile(POT):
        print("Modèle absent :", POT)
        return 1
    msgids = lire_msgids(POT)
    os.makedirs(os.path.dirname(PO), exist_ok=True)

    manquantes = []
    with open(PO, "w", encoding="utf-8") as f:
        f.write(EN_TETE)
        for msgid in msgids:
            traduction = FR.get(msgid, "")
            if not traduction:
                manquantes.append(msgid)
            f.write('msgid "{}"\n'.format(echapper(msgid)))
            f.write('msgstr "{}"\n\n'.format(echapper(traduction)))

    print("chaînes du modèle :", len(msgids))
    print("traduites         :", len(msgids) - len(manquantes))
    print("écrit             :", PO)
    if manquantes:
        print("\nSANS TRADUCTION :")
        for m in manquantes:
            print("  " + repr(m))
    inutiles = [k for k in FR if k not in msgids]
    if inutiles:
        print("\nDANS LA TABLE MAIS PAS DANS LE MODÈLE :")
        for k in inutiles:
            print("  " + repr(k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
