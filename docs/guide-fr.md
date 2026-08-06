# pandoc-linguexx — guide d'utilisation

Ce guide explique comment installer et utiliser les deux outils du projet :

| outil | à quoi il sert |
|---|---|
| **`linguexx2odt`** | convertit un document LaTeX contenant des exemples [linguexx](../../linguexx) en fichier LibreOffice Writer |
| **`LinguExx.bas`** | macro Writer qui met en forme des exemples glosés directement dans Writer, sans passer par LaTeX |

Les deux sont complémentaires et produisent **le même objet** : un tableau
sans bordures, un numéro qui est un champ vivant, et les mêmes styles
nommés. On peut convertir un article depuis LaTeX puis continuer à
ajouter des exemples à la main dans Writer.

L'intérêt principal par rapport à un export PDF : **les numéros
d'exemples se renumérotent tout seuls**. Insérez un exemple au milieu du
document, appuyez sur F9, et tous les numéros suivants ainsi que tous les
renvois se mettent à jour.

---

# Partie A — le convertisseur `linguexx2odt`

## A.1 Prérequis

- **pandoc ≥ 3.0** (développé et testé avec la version 3.6.1)
- **Python ≥ 3.10**, bibliothèque standard uniquement — aucune dépendance
  à installer
- LibreOffice n'est **pas** nécessaire pour convertir, seulement pour lire
  le résultat

Vérifiez que pandoc est bien présent :

```
pandoc --version
```

## A.2 Installation

Sur Arch, Manjaro et la plupart des distributions récentes, le Python du
système est « géré de l'extérieur » (*externally managed*) et refuse
`pip install`. Utilisez un environnement virtuel :

```
python -m venv .venv
.venv/bin/pip install -e .
```

La commande est alors disponible ici :

```
.venv/bin/linguexx2odt article.tex
```

Pour l'avoir sous la main sans le chemin complet, ajoutez-la au `PATH` :

```
export PATH="$PWD/.venv/bin:$PATH"
```

ou faites un lien symbolique :

```
ln -s "$PWD/.venv/bin/linguexx2odt" ~/.local/bin/
```

**Avec `pipx`** (paquet `python-pipx`), tout tient en une ligne et la
commande est installée directement dans le `PATH` :

```
pipx install -e .
```

**Sans rien installer du tout** — il n'y a aucune dépendance externe :

```
PYTHONPATH=src python3 -m linguexx2odt.cli article.tex
```

## A.3 Première conversion

```
linguexx2odt article.tex
```

produit `article.odt` à côté du fichier source. Pour choisir le nom de
sortie :

```
linguexx2odt article.tex -o version-editeur.odt
```

L'option `-v` indique ce qui a été converti :

```
linguexx2odt article.tex -v
```

```
pandoc 3.6.1
12 examples (7 with gloss tiers), 12 placed, 3 cross-references, 1 warnings
-> /home/vous/article.odt
```

## A.4 Les options

```
linguexx2odt fichier.tex [-o sortie.odt]
```

| option | effet |
|---|---|
| `-o`, `--output FICHIER` | nom du `.odt` produit (par défaut : le `.tex` avec l'extension changée) |
| `--text-width CM` | largeur du bloc de texte servant au calcul des colonnes (défaut : 17, soit A4 avec marges de 2 cm) |
| `--font-pt PT` | corps du texte supposé pour estimer la largeur des colonnes (défaut : 12) |
| `--example-spacing CM` | espace au-dessus **et** au-dessous de chaque exemple (défaut : 0,18) |
| `--space-above CM` | espace au-dessus uniquement, prioritaire sur l'option précédente |
| `--space-below CM` | espace au-dessous uniquement |
| `--no-split` | ne pas découper un exemple trop large en bandes superposées ; le comprimer à la place |
| `--page a4\|a4-wide\|letter\|keep` | géométrie de page écrite dans le `.odt` (défaut : `a4`) |
| `--reference-doc REF.odt` | document de référence pandoc fournissant les styles de base |
| `--keep-intermediates DOSSIER` | conserve les fichiers intermédiaires, utile pour diagnostiquer |
| `-q`, `--quiet` | supprime les avertissements |
| `-v`, `--verbose` | résume ce qui a été converti |
| `--print-macro` | affiche le code de la macro Writer et s'arrête |

> **Important à propos de `--text-width`.** La largeur des colonnes et
> l'endroit où un exemple trop long est coupé en bandes sont calculés **au
> moment de la conversion**, puis figés. Si vous changez la géométrie de
> la page plus tard, reconvertissez depuis le `.tex` avec la bonne valeur
> plutôt que de vous battre avec le fichier existant.

## A.5 Ce que le convertisseur prend en charge

La syntaxe **lazy** de linguexx :

`\ex.` · sous-exemples `\a. \b. \c.` (deux niveaux : lettres puis chiffres
romains) · `\z.` · gloses `\gll` / `\glll` / `\gl … \endgl` · traductions
`\glt` · abréviations `\exg.` / `\ag.` / `\bg.` · `{groupes entre
accolades}` comptant pour une seule colonne · lignes de longueurs
inégales · jugements d'acceptabilité · `\label` / `\sublabel` / `\ref` /
`\pref` · `\lpzg{…}`.

Le corps d'un exemple se termine là où linguexx le termine : ligne vide,
`\z.`, fin d'environnement, ou accolade fermante.

Tout le reste du document — sections, prose, emphase, notes de bas de
page, citations — est converti par pandoc comme d'habitude.

## A.6 Ce qu'il ne fait pas, et le dit

Le convertisseur n'échoue **jamais en silence**. Tout ce qu'il ne peut pas
rendre fidèlement produit un avertissement nommant la construction et la
ligne, et dégrade vers quelque chose de lisible plutôt que vers rien :

| construction | ce qui se passe |
|---|---|
| `\ex.` dans `itemize`, `enumerate`, `footnote`, `exe`/`xlist` | laissé tel quel, en LaTeX |
| étiquettes personnalisées `\ex.[(4′)]` | imprimées littéralement ; le compteur n'avance pas |
| `\exsource{…}` | rendu en ligne à la fin, pas aligné à droite |
| `\refrange`, `\Last`, `\Next`, renvois relatifs | laissés en LaTeX |
| `\altn`, `\altg` | laissés en LaTeX |
| syntaxe gb4e `exe`/`xlist`, mode `[legacy]` | hors périmètre |
| mathématiques dans un exemple | confiées à pandoc ; peuvent ne pas survivre |

Lisez les avertissements : ils désignent précisément les endroits à
reprendre à la main.

---

# Partie B — la macro Writer `LinguExx.bas`

> Pour l'extension seule — installation sous Windows, macOS et Linux,
> utilisation, styles, dépannage — voir le manuel dédié :
> [`manuel-extension-fr.md`](manuel-extension-fr.md).

La macro sert à écrire des exemples **directement dans Writer**. Elle sait
faire deux choses que le convertisseur ne peut structurellement pas
faire :

- elle **mesure la police réelle**, au lieu d'estimer la largeur des
  colonnes (l'estimation du convertisseur se trompe de −7 % à +28 %) ;
- elle lit la **vraie largeur du bloc de texte** dans le style de page du
  document, au lieu de faire confiance à `--text-width`.

## B.1 Installation

### Méthode recommandée : l'extension

```
python3 tools/build_oxt.py
unopkg add dist/linguexx-0.1.0.oxt
```

Une entrée **LinguExx ▸ Composer l'exemple** apparaît dans Writer. Une extension installée ne
déclenche **aucun avertissement de sécurité**, contrairement aux macros
incorporées dans un document — c'est la seule méthode raisonnable pour
distribuer la macro à des collègues.

Pour la désinstaller : `unopkg remove net.schaden.linguexx`.

Fermez LibreOffice au préalable — `unopkg` refuse d'écrire dans un profil en
cours d'utilisation. Pour remplacer une version déjà installée, ajoutez
`-f` : `unopkg add -f dist/linguexx-0.1.0.oxt`.

### Méthode manuelle

Le code de la macro est livré avec le paquet Python :

```
linguexx2odt --print-macro > LinguExx.bas
```

Puis :

1. **Outils ▸ Macros ▸ Modifier les macros…** (l'EDI Basic s'ouvre).
2. Dans l'arborescence de gauche, dépliez **Mes macros ▸ Standard**.
3. Clic droit sur **Standard** → **Insérer ▸ Module BASIC**. Renommez-le
   `LinguExx` si vous voulez.
4. Collez tout le contenu du fichier dans la fenêtre de code, puis
   enregistrez (Ctrl+S).

La macro est maintenant disponible dans tous vos documents.

### Lui attribuer un raccourci clavier

1. **Outils ▸ Personnaliser ▸ onglet Clavier**.
2. Choisissez un raccourci libre dans la liste du haut, par exemple
   **Ctrl+Maj+E**.
3. En bas, dans **Catégorie**, dépliez **Macros LibreOffice ▸ Mes macros ▸
   Standard ▸ LinguExx**.
4. Dans **Fonction**, sélectionnez `GlossSelection` (le nom interne de
   la macro ; seule l'entrée de menu s'appelle « Composer l'exemple »).
5. Cliquez sur **Modifier**, puis sur **OK**.

## B.2 Utilisation — un exemple glosé

Tapez les lignes dans le document, **sélectionnez-les**, puis lancez la
macro :

```
Esto es un ejemplo glosado
this is a example glossed
'This is a glossed example.'
```

Résultat :

```
(1)   Esto    es   un   ejemplo   glosado
      this    is   a    example   glossed
      'This is a glossed example.'
```

Les règles de lecture de la sélection :

- **la première ligne** est la langue objet ;
- **la dernière ligne** est la traduction libre si elle commence par un
  guillemet (`'`, `"`, `‘`, `“`, `«`, `„`) ou par l'accent grave `` ` `` de
  la convention LaTeX `` `comme ceci' `` ; sinon c'est une ligne de glose
  de plus ;
- **tout ce qui est entre les deux** est une ligne de glose. Il peut y en
  avoir autant que nécessaire (morphèmes, gloses Leipzig, etc.).

Le numéro `(1)` est un champ **Séquence** nommé `NumEx` : il se
renumérote tout seul.

### Exemples non glosés

Une seule ligne suffit — c'est le cas le plus courant :

```
Un exemple simple.
```

donne `(1)  Un exemple simple.`, numéroté comme n'importe quel autre.
Le texte reste courant dans une cellule unique, il n'est pas découpé en
colonnes. Ajoutez une ligne entre guillemets en dessous et elle devient
la traduction.

### Groupes entre accolades

Pour qu'une suite de mots occupe une seule colonne, mettez-la entre
accolades — exactement comme dans linguexx :

```
Ich {habe geschlafen}
I    {have slept}
'I slept.'
```

### Jugements d'acceptabilité

Un `*`, `**`, `?`, `??`, `#`, `%` ou `!` en tête de la ligne objet est
reconnu et placé dans **sa propre colonne**, en débord à gauche :

```
*Das kleine Kind schlafen
 the little child sleep.INF
'The little child sleeps.'
```

La marque ne consomme aucune place horizontale : un exemple jugé et un
exemple non jugé commencent exactement au même endroit. C'est la
géométrie de linguexx.

## B.3 Les sous-exemples

Les paradigmes `a. … b. …` fonctionnent, glosés ou non. Sélectionnez
l'ensemble :

```
a. Esto es un ejemplo
   this is a example
   'This is an example.'
b. Otro ejemplo aqui
   another example here
   'Another example here.'
```

Résultat : les lettres dans leur propre colonne, **un seul numéro** pour
tout le paradigme, et une grille de colonnes commune.

Points à connaître :

- **Ce qui compte comme lettre** : une seule lettre ou un chiffre romain,
  suivi de `.` ou `)` — `a.`, `(b)`, `iii.`. La reconnaissance est
  volontairement étroite, pour que `Dr.` ou `no.` ne soient pas pris pour
  des lettres de sous-exemple.
- La lettre peut **précéder la ligne objet** (comme ci-dessus) ou être
  **seule sur sa ligne**.
- **Une lettre de sous-exemple se place exactement là où commence le
  texte d'un exemple principal.** C'est la géométrie de linguexx, et c'est
  la raison pour laquelle la colonne de jugement est prélevée sur la
  colonne précédente au lieu d'être insérée après elle.
- Les items peuvent être **glosés ou non, dans le même paradigme**. Un
  item non glosé est du texte courant dans une cellule fusionnée, et non
  un mot par colonne — le découper alignerait des mots qui n'ont rien à
  voir entre eux.
- **Chaque item peut porter son propre jugement.**
- Chaque item peut avoir sa propre traduction.

## B.4 Ce que la macro refuse

Elle ne devine pas quand la sélection est ambiguë :

| situation | message |
|---|---|
| rien n'est sélectionné | demande de sélectionner la ou les lignes de l'exemple |
| une lettre de sous-exemple apparaît **en cours** de sélection alors que la sélection ne commence pas par une lettre | demande de commencer à la première lettre |

## B.5 Annuler

Toute la construction est **une seule étape d'annulation** : un Ctrl+Z
reprend l'exemple entier, il n'est pas nécessaire de défaire ligne par
ligne.

---

# Partie C — mise en forme : tout passe par des styles

Rien n'utilise de formatage direct. Tout est un **style nommé**, ce qui
veut dire que vous pouvez remettre en forme **tous les exemples du
document d'un coup** depuis le volet Styles (**F11**, rubrique *Styles
personnalisés*).

## C.1 Les styles disponibles

### Styles de paragraphe

| style | ce qu'il gouverne |
|---|---|
| `LxExampleCell` | toutes les cellules : langue objet, gloses, numéro |
| `LxTranslation` | la ligne de traduction libre |
| `LxJudgmentCell` | la colonne des jugements (alignée à droite) |
| `LxExampleSpace` | **la hauteur des deux espaces**, au-dessus et au-dessous |
| `LxExampleSpaceAbove` | hérite du précédent ; donnez-lui une hauteur propre pour ne changer que l'espace du haut |
| `LxExampleSpaceBelow` | idem, pour l'espace du bas seulement |

### Styles de caractère

| style | ce qu'il gouverne |
|---|---|
| `LxLeipzig` | les gloses Leipzig (`\lpzg{…}`) — petites capitales |
| `LxItalic`, `LxBold`, `LxSmallCaps` | italique, gras, petites capitales |
| `LxJudgment` | la marque de jugement elle-même |

Pour changer la police de tous les exemples d'un document : modifiez
`LxExampleCell`. Pour mettre toutes les gloses Leipzig en gris :
modifiez `LxLeipzig`. Etc.

## C.2 L'espace au-dessus et au-dessous des exemples

C'est le réglage que l'on veut changer le plus souvent, et il se fait de
deux manières.

### À la conversion

```
linguexx2odt article.tex --example-spacing 0.35
linguexx2odt article.tex --space-above 0.4 --space-below 0.2
```

### Après coup, dans Writer

Ouvrez le volet **Styles** (F11) et modifiez le style de paragraphe :

| pour changer… | modifiez… |
|---|---|
| **les deux espaces à la fois** | `LxExampleSpace` |
| l'espace du **haut** seulement | `LxExampleSpaceAbove` |
| l'espace du **bas** seulement | `LxExampleSpaceBelow` |

Dans la boîte de dialogue du style, allez à l'onglet **Retraits et
espacement**, puis **Interligne : Fixe**, et donnez la hauteur voulue.

Tous les exemples du document suivent immédiatement.

> **Pourquoi *Interligne fixe* et pas « espace au-dessus du
> paragraphe » ?** L'espace est en réalité la hauteur d'une ligne de
> tableau vide placée en haut et en bas de chaque exemple. Un interligne
> fixe fixe cette hauteur **exactement** : 0 cm donne vraiment 0.
>
> On aurait préféré une marge de tableau, plus naturelle. C'est
> impossible : LibreOffice ignore l'héritage (`style:parent-style-name`)
> sur les styles de tableau, si bien qu'un espacement de tableau ne peut
> jamais être autre chose qu'un formatage direct, appliqué tableau par
> tableau. La ligne d'espacement est le seul mécanisme qui donne un vrai
> style modifiable.

Les deux styles `…Above` et `…Below` ne déclarent **rien** par
eux-mêmes : ils suivent le style parent. C'est ce qui fait qu'une seule
modification de `LxExampleSpace` déplace les deux côtés. Dès que vous
donnez une hauteur propre à l'un des deux, ce côté-là devient
indépendant.

---

# Partie D — vérifier la renumérotation

C'est l'intérêt principal du format produit. Pour le vérifier :

1. Ouvrez le `.odt` dans Writer.
2. Placez le curseur avant un exemple existant.
3. Insérez un nouveau champ de numéro : **Insertion ▸ Champ ▸ Autres
   champs… ▸ onglet Variables ▸ Séquence**, choisissez `NumEx`, puis
   **Insérer**.
4. **Outils ▸ Actualiser ▸ Champs** (ou **F9**).

Tous les numéros suivants et tous les renvois se décalent d'un cran.

En pratique, vous n'insérerez pas les champs à la main : vous utiliserez
la macro, qui pose le champ pour vous.

---

# Partie E — problèmes fréquents

### Les colonnes sont trop larges ou trop étroites (documents convertis)

Le convertisseur n'a pas accès aux métriques de la police : il estime la
largeur des colonnes à partir de largeurs de caractères moyennes, en
majorant légèrement. Trois solutions, de la plus simple à la meilleure :

1. tirez les bords de colonne à la souris dans Writer ;
2. reconvertissez avec `--font-pt` si votre corps de texte n'est pas 12 ;
3. utilisez la macro, qui mesure vraiment.

### Un exemple déborde de la page

Un exemple trop large est normalement découpé en **bandes superposées**,
chaque bande repartant de la marge gauche. Si vous avez utilisé
`--no-split`, il est comprimé à la place et les mots peuvent se couper
dans leur cellule. Reconvertissez sans `--no-split`, ou avec la bonne
valeur de `--text-width`.

### La langue objet n'est pas alignée avec ses gloses

Si vous avez construit un tableau à la main : Writer applique
automatiquement le style **Titre de tableau** (centré) à la première ligne
d'un nouveau tableau. Appliquez `LxExampleCell` à **toutes** les cellules.

### Les numéros affichent le mauvais chiffre

Appuyez sur **F9** (**Outils ▸ Actualiser ▸ Champs**). Les numéros sont
des champs calculés ; la valeur mémorisée dans le fichier n'est qu'un
cache.

### La macro ne fait rien / un message apparaît

Le message dit précisément ce qui manque. Les deux causes les plus
fréquentes sont une sélection d'une seule ligne, et un paradigme de
sous-exemples sélectionné à partir du milieu.

### Les accents ou caractères spéciaux passent mal

Le fichier LaTeX doit être en **UTF-8**. C'est la seule chose que le
convertisseur suppose du codage.

---

# Annexe — résumé des commandes

```
# convertir un article
linguexx2odt article.tex -o article.odt -v

# espacement plus aéré autour des exemples
linguexx2odt article.tex --example-spacing 0.35

# page A4 avec des marges plus étroites
linguexx2odt article.tex --page a4-wide --text-width 18
```

Dans Writer : sélectionner les lignes, puis **Ctrl+Maj+E** (ou le
raccourci que vous avez choisi).
