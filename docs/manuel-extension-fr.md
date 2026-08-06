# LinguExx — manuel de l'extension LibreOffice

**LinguExx** est une extension pour LibreOffice Writer qui met en forme des
exemples linguistiques : langue objet alignée sur ses gloses, traduction
libre, jugements d'acceptabilité en débord, paradigmes `a. / b.`

Les numéros d'exemples sont des **champs vivants** : insérez un exemple au
milieu du document, appuyez sur **F9**, et tous les numéros suivants se
renumérotent.

Ce manuel ne concerne que l'extension. Le convertisseur LaTeX →
LibreOffice (`linguexx2odt`) est documenté séparément dans
[`guide-fr.md`](guide-fr.md).

---

## 1. Prérequis

- **LibreOffice 4.1 ou plus récent** — c'est le minimum que déclare
  l'extension. Développée et vérifiée sous LibreOffice 26.2 ; toute
  version moderne convient. Fonctionne sous Windows, macOS et Linux.
- Le fichier de l'extension : **`linguexx-0.1.0.oxt`**.

Il n'y a rien d'autre à installer : ni Python, ni pandoc, ni LaTeX.

---

## 2. Installation

### 2.1 La méthode simple — sur les trois systèmes

C'est la méthode à utiliser dans la quasi-totalité des cas.

1. **Fermez LibreOffice** (tous les documents, et sous Windows le
   démarrage rapide dans la zone de notification).
2. **Double-cliquez sur `linguexx-0.1.0.oxt`.**
   LibreOffice s'ouvre sur le **Gestionnaire des extensions** et propose
   l'installation.
3. Acceptez, puis fermez la fenêtre.

Si le double-clic n'ouvre pas LibreOffice (fichier non associé, ce qui
arrive surtout sous Linux) :

1. Ouvrez LibreOffice Writer.
2. **Outils ▸ Gestionnaire des extensions…**
3. Bouton **Ajouter**, choisissez le fichier `.oxt`, validez.
4. **Fermez et rouvrez LibreOffice** — le menu n'apparaît qu'au
   redémarrage.

Une fois installée, l'extension ajoute un menu :

> **LinguExx ▸ Composer l'exemple**

### 2.2 En ligne de commande

Utile pour installer sur plusieurs postes, ou quand l'interface graphique
pose problème. L'outil s'appelle `unopkg` ; seul son emplacement change
d'un système à l'autre.

**Dans tous les cas, fermez LibreOffice d'abord** : `unopkg` refuse
d'écrire dans un profil en cours d'utilisation.

#### Windows

`unopkg.exe` se trouve dans le dossier `program` de LibreOffice, en
général :

```
C:\Program Files\LibreOffice\program\unopkg.exe
```

Ouvrez l'invite de commandes (`cmd`) et tapez :

```
"C:\Program Files\LibreOffice\program\unopkg.exe" add linguexx-0.1.0.oxt
```

Les guillemets sont nécessaires à cause de l'espace dans « Program
Files ». Si LibreOffice est en 32 bits sur un Windows 64 bits, le chemin
est `C:\Program Files (x86)\LibreOffice\program\`.

#### macOS

`unopkg` est à l'intérieur du paquet d'application :

```
/Applications/LibreOffice.app/Contents/MacOS/unopkg add linguexx-0.1.0.oxt
```

Ouvrez le **Terminal** (Applications ▸ Utilitaires) et collez cette ligne
en remplaçant `linguexx-0.1.0.oxt` par le chemin réel du fichier — le plus
simple est de taper la commande jusqu'à `add `, puis de **glisser le
fichier depuis le Finder** dans la fenêtre du Terminal.

#### Linux

`unopkg` est normalement dans le `PATH` :

```
unopkg add linguexx-0.1.0.oxt
```

Sinon, il est à côté du binaire de LibreOffice, typiquement
`/usr/lib/libreoffice/program/unopkg`.

### 2.3 Vérifier que c'est installé

```
unopkg list                      # Linux
"C:\Program Files\LibreOffice\program\unopkg.exe" list          # Windows
/Applications/LibreOffice.app/Contents/MacOS/unopkg list        # macOS
```

Vous devez voir :

```
Identifier: net.schaden.linguexx
  Version: 0.1.0
  is registered: yes
```

Ou, dans l'interface : **Outils ▸ Gestionnaire des extensions…** doit
lister « LinguExx — exemples linguistiques glosés ».

### 2.4 Mettre à jour

Réinstaller par-dessus une version déjà présente demande l'option `-f`
(*force*) :

```
unopkg add -f linguexx-0.1.0.oxt
```

Par l'interface, le Gestionnaire des extensions propose de remplacer la
version existante.

### 2.5 Désinstaller

```
unopkg remove net.schaden.linguexx
```

ou, dans le Gestionnaire des extensions, sélectionnez LinguExx et cliquez
sur **Supprimer**.

---

## 3. Un raccourci clavier

Le menu fonctionne, mais un raccourci est bien plus rapide à l'usage.

1. **Outils ▸ Personnaliser… ▸ onglet Clavier**.
2. Choisissez une combinaison libre dans la liste du haut — par exemple
   **Ctrl+Maj+E** (sous macOS : **⌘+Maj+E**).
3. En bas à gauche, dans **Catégorie**, dépliez
   **Mes macros ▸ LinguExx ▸ Gloss**. (L'extension installe sa
   bibliothèque parmi les macros de l'utilisateur ; selon la version de
   LibreOffice, cette branche peut se trouver sous une rubrique
   « Macros ».)
4. Dans **Fonction**, sélectionnez **`GlossSelection`**.
5. Cliquez sur **Modifier**, puis **OK**.

> La fonction s'appelle encore `GlossSelection` pour des raisons de
> compatibilité, alors que l'entrée de menu s'appelle « Composer
> l'exemple ». C'est le même traitement.

Sous macOS, pensez à vérifier dans **LibreOffice ▸ Préférences** que la
combinaison choisie n'est pas déjà prise par le système.

---

## 4. Utilisation

Le principe est toujours le même : **tapez les lignes, sélectionnez-les,
lancez la commande**.

### 4.1 Un exemple simple, sans glose

C'est le cas le plus courant. Une seule ligne suffit :

```
Un exemple simple.
```

donne

```
(1)   Un exemple simple.
```

Le texte reste du texte courant : il n'est pas découpé en colonnes.

### 4.2 Un exemple glosé

Sélectionnez la langue objet, la ou les lignes de glose, et la traduction :

```
Esto es un ejemplo glosado
this is a example glossed
'This is a glossed example.'
```

donne

```
(2)   Esto    es   un   ejemplo   glosado
      this    is   a    example   glossed
      'This is a glossed example.'
```

Les règles de lecture de la sélection :

- **la première ligne** est la langue objet ;
- **la dernière ligne** est la traduction libre si elle commence par un
  guillemet ; sinon c'est une ligne de glose de plus ;
- **tout ce qui est entre les deux** est une ligne de glose. Il peut y en
  avoir autant que nécessaire.

### 4.3 La traduction libre

Une ligne est reconnue comme traduction si elle commence par l'un de ces
caractères :

| | |
|---|---|
| `'` `"` | apostrophe et guillemet droits |
| `` ` `` | **accent grave** — la convention LaTeX `` `comme ceci' `` |
| `‘` `’` `“` `„` | guillemets courbes |
| `«` `‹` | guillemets français |

L'accent grave compte parce que c'est ce que l'on tape en venant de
linguexx : l'autocorrection ne transforme que le guillemet fermant.

Une traduction se place toujours **en dernière ligne du tableau**, même
lorsque l'exemple est long et découpé en plusieurs bandes.

### 4.4 Plusieurs mots dans une seule colonne

Mettez-les entre accolades, comme dans linguexx :

```
Ich {habe geschlafen}
I    {have slept}
'I slept.'
```

### 4.5 Jugements d'acceptabilité

Un `*`, `**`, `?`, `??`, `#`, `%` ou `!` en tête de la ligne objet est
placé dans **sa propre colonne, en débord à gauche** :

```
*Das kleine Kind schlafen
 the little child sleep.INF
'The little child sleeps.'
```

La marque ne consomme aucune place horizontale : un exemple jugé et un
exemple non jugé commencent exactement au même endroit.

### 4.6 Sous-exemples

Sélectionnez tout le paradigme :

```
a. Esto es un ejemplo
   this is a example
   'This is an example.'
b. Otro ejemplo aqui
   another example here
   'Another example here.'
```

Les lettres vont dans leur propre colonne et le paradigme porte **un seul
numéro**.

- Sont reconnus comme lettres : une seule lettre ou un chiffre romain
  suivi de `.` ou `)` — `a.`, `(b)`, `iii.` La reconnaissance est étroite
  exprès, pour que `Dr.` ou `no.` ne soient pas pris pour des lettres.
- La lettre peut précéder la ligne objet, ou être seule sur sa ligne.
- **Une lettre de sous-exemple se place exactement là où commence le texte
  d'un exemple principal** — la géométrie de linguexx.
- Les items peuvent être glosés ou non **dans le même paradigme**, et
  chacun peut porter son propre jugement et sa propre traduction.

### 4.7 Exemples trop longs

Un exemple plus large que le bloc de texte est automatiquement découpé en
**bandes superposées**, chaque bande repartant de la marge gauche, les
gloses restant sous leurs mots. La traduction reste à la fin.

La largeur des colonnes est **mesurée sur la police réelle** du document,
et la largeur disponible est lue dans le style de page : le résultat est
juste pour la page que vous avez sous les yeux.

### 4.8 Annuler

Toute la construction est **une seule étape d'annulation**. Un **Ctrl+Z**
(⌘+Z) reprend l'exemple entier.

---

## 5. La renumérotation automatique

C'est l'intérêt principal du dispositif.

1. Placez le curseur avant un exemple existant et créez-en un nouveau.
2. **Outils ▸ Actualiser ▸ Champs**, ou simplement **F9**.

Tous les numéros suivants se décalent d'un cran.

---

## 6. Mise en forme : tout passe par des styles

L'extension n'utilise aucun formatage direct. Tout est un **style nommé**,
donc vous pouvez remettre en forme **tous les exemples du document d'un
coup** depuis le volet Styles (**F11**, rubrique *Styles personnalisés*).

| style | ce qu'il gouverne |
|---|---|
| `LxExampleCell` | toutes les cellules : langue objet, gloses, numéro |
| `LxTranslation` | la ligne de traduction libre |
| `LxJudgmentCell` | la colonne des jugements |
| `LxExampleSpace` | **la hauteur des deux espaces**, au-dessus et au-dessous |
| `LxExampleSpaceAbove` | hérite du précédent ; pour l'espace du haut seulement |
| `LxExampleSpaceBelow` | idem, pour l'espace du bas seulement |

### Changer l'espace autour des exemples

Modifiez le style **`LxExampleSpace`** : onglet **Retraits et espacement**,
puis **Interligne : Fixe**, et donnez la hauteur voulue. Tous les exemples
du document suivent immédiatement.

Pour ne changer qu'un seul côté, donnez une hauteur propre à
`LxExampleSpaceAbove` ou `LxExampleSpaceBelow`.

> **Pourquoi un interligne fixe ?** L'espace est en réalité la hauteur
> d'une ligne de tableau vide placée en haut et en bas de chaque exemple.
> Un interligne fixe la règle **exactement** : 0 cm donne vraiment 0.

Ces styles sont exactement ceux qu'écrit le convertisseur `linguexx2odt` :
un document converti depuis LaTeX et un exemple ajouté à la main avec
l'extension sont le même objet et obéissent aux mêmes styles.

---

## 7. Ce que l'extension refuse de faire

Elle ne devine pas quand la sélection est ambiguë :

| situation | ce qui se passe |
|---|---|
| rien n'est sélectionné | message demandant de sélectionner la ou les lignes |
| une lettre de sous-exemple apparaît **en cours** de sélection alors que la sélection ne commence pas par une lettre | message demandant de commencer à la première lettre |
| une lettre seule, sans rien après elle | message signalant qu'il n'y a pas de contenu |

---

## 8. Dépannage

### L'extension est installée mais le menu n'apparaît pas

Fermez et rouvrez complètement LibreOffice. Sous Windows, vérifiez que le
**démarrage rapide** n'est pas resté actif dans la zone de notification :
clic droit ▸ **Quitter**.

### « unopkg : impossible d'accéder au profil »

LibreOffice est encore ouvert. Fermez-le complètement, puis recommencez.

### Les numéros affichent le mauvais chiffre

Appuyez sur **F9**. Les numéros sont des champs calculés ; la valeur
enregistrée dans le fichier n'est qu'un cache.

### La langue objet n'est pas alignée avec ses gloses

Cela n'arrive pas avec un exemple construit par l'extension. Si vous avez
fabriqué un tableau à la main, appliquez le style `LxExampleCell` à
**toutes** les cellules : Writer met automatiquement la première ligne
d'un tableau en style *Titre de tableau*, qui est centré.

### Rien ne se passe quand je lance la commande

Vérifiez qu'une sélection est bien active. Si un message apparaît, il
indique précisément ce qui manque.

### Où est mon profil LibreOffice ?

Utile pour signaler un problème ou repartir de zéro :

| système | emplacement |
|---|---|
| Windows | `%APPDATA%\LibreOffice\4\user` |
| macOS | `~/Library/Application Support/LibreOffice/4/user` |
| Linux | `~/.config/libreoffice/4/user` |

---

## 9. Fabriquer le fichier `.oxt` soi-même

Seulement utile si vous travaillez sur le code source. Depuis la racine du
dépôt :

```
python3 tools/build_oxt.py
```

Le fichier est écrit dans `dist/`. Il contient la macro Basic, la
déclaration du menu, et rien d'autre.

---

## Licence

GPL-3.0-or-later. Copyright © 2026 Gerhard Schaden.
