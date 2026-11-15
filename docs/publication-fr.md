# Préparer une version

[English](releasing.md) · [Guide d'utilisation](guide-fr.md)

Appliquer cette liste à une version candidate précise. Consigner le commit,
les noms des fichiers distribués, les versions des outils, la date et les
résultats. Une exécution antérieure ne valide pas les modifications suivantes.
Cette liste décrit une procédure ; elle ne signifie pas que tous les points
ont déjà été vérifiés.

## Vérifications automatisées

1. Installer le candidat dans un environnement de développement (`pip install
   -e '.[dev]'`) et installer Ruff. Prévoir pandoc, LibreOffice et Poppler ;
   placer le corpus linguexx cible (1.5) à côté du dépôt.
2. Exécuter `make check` et `make js-test` (Node ≥ 22). Ne pas activer
   `LINGUEXX2ODT_ALLOW_MISSING` pour valider une publication.
3. Exécuter la suite Writer avec `python3 tools/run_macro_test.py`, dans un
   Python disposant du pont UNO de LibreOffice. Lancer `make onlyoffice-test`
   avec Document Builder configuré comme dans le workflow CI.
4. Construire les fichiers distribués : `make oxt`, `make onlyoffice` et
   `python -m pip wheel . --no-deps --wheel-dir dist`.
5. Installer le wheel dans un environnement neuf. Vérifier les trois
   commandes, `linguexx2odt --print-macro` et un aller-retour de conversion.
6. Vérifier les versions minimales déclarées de Python/Pandoc et une
   combinaison plus récente. La CI impose maintenant la suite Python complète
   et le contrôle du wheel neuf pour les couples Python/Pandoc 3.10/3.6.1,
   3.12/3.6.1 et 3.14/3.11. Vérifier les trois résultats pour le candidat.

## Vérifications dans les éditeurs

- Writer : installer le `.oxt` candidat ; composer, décomposer, modifier,
  recomposer et annuler des exemples ordinaires, des gloses communes et
  des arbres. Vérifier numéros, renvois, styles et page étroite.
- OnlyOffice : installer le module candidat dans l'application de bureau ;
  répéter le cycle et vérifier la renumérotation d'un document converti.
  Document Builder ne valide pas à lui seul l'interface de bureau.
- Word : suivre la [procédure Word](../WORD-TESTS-TODO.md) en consignant
  l'application et sa version. Distinguer la sortie du convertisseur du
  comportement du complément.

**Validation Word en attente :** les gloses communes ajoutées le 14 novembre
2026 n'ont pas été testées dans Word réel, ni sur le web ni sur le bureau.
Rendu, insertion, cycles composer/décomposer, refus des sélections invalides
et annulation sur le bureau restent à vérifier. Les simulations Office.js
et les contrôles OOXML ne valident pas ce point. Maintenir cette limite dans
les notes de version jusqu'à sa vérification.

## Documentation et préparation de la publication

- Mettre à jour ensemble le README anglais et le guide français : prérequis,
  commandes, constructions prises en charge, limites et état des vérifications.
- Mettre à jour les deux manuels Writer pour les changements de composition
  ou de modification.
- Mettre à jour le manuel PDF anglais, lancer `make manual` et relire le PDF.
- Harmoniser les noms des fichiers distribués et les versions du paquet.
  Consigner changements, limites et résultats réels dans les notes de version ;
  distinguer fonctions implémentées, tests automatisés et vérification manuelle.
- Conserver la réserve concernant Word tant que ces contrôles restent en
  attente. Relire le candidat complet avant de publier ses fichiers.

## Maintenir les cas de comportement communs

Ajouter les sélections de gloses communes invalides dans
[`tests/fixtures/shared-authoring.json`](../tests/fixtures/shared-authoring.json),
avec un nom explicite, les lignes d'entrée `lines` et `errorLine`, le numéro
de ligne à partir de 1, lignes vides comprises. Les résultats attendus sont
relus manuellement ; ils ne sont pas générés. Le parseur commun, les tests du
volet Word, ceux des opérations OnlyOffice et la suite réelle Writer lisent
ce même fichier. Ils vérifient le refus avant remplacement, ainsi que la
réussite d'une opération valide ultérieure.

Exécuter `make js-test` et `python -m pytest tests/test_addin_core.py
 tests/test_macro_sync.py`, puis la suite de macros Writer pour toute
modification de ce contrat. Garder les vérifications propres à chaque
éditeur dans sa suite : aucun appel d'insertion pour Word, aucune opération
produite ni entrée modifiée pour OnlyOffice, texte, tableaux et numérotation
inchangés dans Writer. Ces contrôles complètent les cas de mise en page et
d'aller-retour générés par le convertisseur ; ils ne valident pas Word réel.

Pour reproduire le contrôle du paquet installé, construire un wheel,
l'installer avec ses dépendances dans un environnement virtuel neuf, puis
lancer le Python de cet environnement avec `-I tools/check_installed.py`.
Ne pas utiliser d'installation modifiable ni les paquets du système. Le script
vérifie les chemins d'import, les trois commandes, la macro embarquée, les
champs de renvoi et les allers-retours ODT/DOCX depuis un répertoire temporaire.
Il nécessite pandoc et LibreOffice.

La version minimale de Pandoc est désormais 3.6.1. Une exécution séparée
avec Python 3.10/Pandoc 3.0 a reproduit un défaut de rendu des listes DOCX
imbriquées ; le succès du seul contrôle du wheel ne suffisait pas. L'extra
de développement inclut `lxml` pour valider les schémas ECMA-376 lorsqu'ils
sont disponibles.
