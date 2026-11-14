#!/bin/bash
# build_locales.sh — Extrait les chaînes, remplit le catalogue français
# et le compile.
#
# À relancer chaque fois que des textes de l'interface changent.
#
#   1. xgettext relit tous les .py et met à jour locale/diaporama2screen.pot
#   2. locale/traduire_fr.py écrit locale/fr/LC_MESSAGES/diaporama2screen.po
#      et signale les chaînes sans traduction
#   3. msgfmt compile le .po en .mo, seul fichier que gettext lit à l'exécution
#
# Les .mo ne sont pas versionnés : ils se refabriquent d'une commande.

set -u
cd "$(dirname "$0")" || exit 1

DOMAINE="diaporama2screen"
LANGUES="fr"

# Lue dans paths.py plutôt que recopiée ici : un numéro écrit à deux
# endroits finit toujours par différer.
VERSION=$(python3 -c 'import paths; print(paths.APP_VERSION)' 2>/dev/null)
VERSION=${VERSION:-0.0.0}

for outil in xgettext msgfmt python3; do
  if ! command -v "$outil" >/dev/null; then
    echo "Outil absent : $outil"
    echo "  sudo apt install gettext"
    exit 1
  fi
done

mkdir -p locale

echo "--- extraction des chaines ---"
xgettext --language=Python --keyword=_ --keyword=N_ --from-code=UTF-8 \
  --package-name="$DOMAINE" --package-version="$VERSION" \
  --msgid-bugs-address=jean \
  --output="locale/$DOMAINE.pot" ./*.py || exit 1
echo "chaines extraites : $(grep -c '^msgid ' "locale/$DOMAINE.pot")"

echo
echo "--- catalogue francais ---"
python3 locale/traduire_fr.py || exit 1

echo
echo "--- compilation ---"
for langue in $LANGUES; do
  po="locale/$langue/LC_MESSAGES/$DOMAINE.po"
  mo="locale/$langue/LC_MESSAGES/$DOMAINE.mo"
  if [ ! -f "$po" ]; then
    echo "absent : $po"
    continue
  fi
  msgfmt --check-format --output-file="$mo" "$po" || exit 1
  echo "$mo"
done

echo
echo "Termine."
