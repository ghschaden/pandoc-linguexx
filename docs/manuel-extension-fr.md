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

Une fois installée, l'extension ajoute un menu à quatre commandes, plus un
réglage :

> **LinguExx ▸ Composer l'exemple**
> **LinguExx ▸ Composer l'arbre numéroté**
> **LinguExx ▸ Composer l'arbre sans numéro**
> **LinguExx ▸ Décomposer l'exemple** (§ 5)
> **LinguExx ▸ Mise en page des exemples…** (§ 8)

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

Pour les arbres (§ 4.9), répétez l'opération avec **`TreeSelection`**
(arbre numéroté) et **`TreeSelectionBare`** (sans numéro) — par exemple
**Ctrl+Maj+T** et **Ctrl+Maj+U**.

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

### 4.8 Le formatage que vous avez appliqué

Ce que vous avez mis en forme à la main est conservé : **petites
capitales** d'une glose Leipzig, *italique* de la langue objet, **gras**,
exposants et indices, styles de caractère.

Chaque passage est mesuré dans la police dans laquelle il sera dessiné, et
non dans celle du reste de la ligne. C'est indispensable pour les petites
capitales : ce sont des capitales à 80 % du corps, donc 10 à 20 % **plus
larges** que les minuscules qu'elles remplacent. Mesurée sur les
minuscules, la colonne serait trop étroite et la glose y reviendrait à la
ligne — et, dans un exemple découpé en bandes, une bande de trop
déborderait du bloc de texte.

### 4.9 Arbres syntaxiques

**LinguExx ▸ Composer l'arbre numéroté** transforme une notation entre crochets en
un arbre dessiné. Sélectionnez

```
[DP [D le] [NP [N arbre]]]
```

et vous obtenez un exemple numéroté dont le contenu est l'arbre, dans le
même tableau que n'importe quel autre exemple : même champ de numéro,
mêmes styles d'espacement, même alignement.

La notation est celle que partagent qtree et forest : le premier mot après
un `[` est l'étiquette, ce qui suit sont les filles, et un mot nu est une
feuille. `[D le]` et `[D [le]]` sont équivalents.

- **`{groupes entre accolades}`** forment une seule étiquette, espaces
  comprises.
- **Une feuille suivie de `, roof`** est dessinée sous un triangle :
  `[S [NP {le grand arbre, roof}] [VP [V dormait]]]`.
- **Un jugement d'acceptabilité** précède l'arbre comme il précède un
  exemple : `*[S [NP lui] [VP [V partait]]]`.
- **Les étiquettes gardent leur mise en forme** : italique d'un terminal,
  petites capitales d'un trait.

L'arbre est un groupe de formes de dessin Writer ancré comme caractère :
un objet réel du document, qui s'imprime, s'exporte en PDF, dont les
étiquettes sont du texte sélectionnable, et que vous pouvez déplacer à la
souris — mais rien ne recalcule la disposition si vous le faites.

#### Mouvement

Nommez les deux nœuds et ajoutez une ligne `move` sous l'arbre :

```
[CP [DP,name=wh quoi] [C' [C a] [TP [DP Jean] [VP [V vu] [DP,name=t __]]]]]
move t -> wh
```

La flèche part de sous le nœud d'origine, suit sa propre voie dans une
gouttière sous l'arbre, et remonte jusqu'au nœud d'arrivée. Les deux
extrémités se placent **sous le sous-arbre entier**, et non à la ligne de
base du nœud : un nœud a presque toujours quelque chose en dessous de lui,
et une flèche visant la ligne de base le traverserait. Une flèche pointe
vers un constituant, elle ne le traverse jamais. Plusieurs
flèches reçoivent des voies distinctes ; deux flèches ne partagent une voie
que si leurs portées ne se chevauchent pas, et la plus courte passe
au-dessus — comme on le dessine à la main.

`name=` est une option de nœud comme `roof` : elle se met dans les
crochets, après une virgule. Une ligne `move` est reconnue au mot `move`
en tête ; tout le reste de la sélection est l'arbre.

**Ce n'est pas du TikZ, volontairement.** forest écrit la même chose
`\draw[->] (t) to[out=south west,in=south] (wh);`. Prendre en charge un
sous-ensemble de TikZ serait un piège : la limite du sous-ensemble
passerait pour un bug. Tout ce qui contient une barre oblique inverse reste
refusé, et le message renvoie ici.

#### Un arbre dans un paradigme

Un arbre peut être un item d'un paradigme `a. … b. …`, à côté d'items
glosés ou de simple texte. Sélectionnez l'ensemble et lancez **Composer
l'exemple** — pas *Composer l'arbre*, puisque c'est le paradigme qui est
l'exemple :

```
a. [DP [D le] [NP [N arbre]]]
b. [DP [D un] [NP [N chat]]]
c. [VP [V chantait] [AdvP [Adv fort]]]
```

Un seul numéro, les lettres dans leur colonne, chaque arbre dans la cellule
fusionnée qu'aurait prise un item non glosé.

**C'est la commande qui décide, jamais le texte.** *Composer l'exemple* ne
dessine jamais d'arbre : les crochets seuls ne signifient rien, car c'est
ainsi qu'on indique la structure constituante dans un exemple ordinaire —
`[TP [DP Jean] [VP est parti]]` reste tel quel.

Sous *Composer l'arbre numéroté*, chaque item est un arbre. Un item qui
n'en est pas un est refusé **avec sa lettre** (« Sub-example b. is not a
tree »), avant toute construction. Pour mettre un arbre à côté d'un exemple
glosé, faites-en deux exemples.

#### Un arbre venu de LaTeX

Le convertisseur ne sait pas dessiner d'arbre, mais il ne le détruit plus :
un environnement `\begin{forest}…\end{forest}` (ou `\Tree` de qtree)
arrive dans le document converti sous forme de **notation entre crochets**,
dans l'exemple auquel il appartient.

Sélectionnez ces crochets et lancez **Composer l'arbre sans numéro** — sans
numéro, car l'exemple qui les entoure en fournit déjà un.

#### Un arbre sans numéro

Tous les arbres ne doivent pas consommer un numéro d'exemple : celui d'une
note de bas de page, d'une figure ou d'une diapositive, non.
**LinguExx ▸ Composer l'arbre sans numéro** dessine le même arbre sans
tableau, sans numéro et sans styles d'exemple : les formes remplacent les
crochets là où ils se trouvent.

C'est une commande distincte, et non une commande qui devinerait si un
numéro est souhaité — deviner d'après le contexte serait faux en silence.

**Donnez-lui une ligne à lui.** Un groupe ancré comme caractère réserve la
place en hauteur mais pas en largeur : l'arbre est dessiné là où le texte
de la ligne s'arrête. Du texte *avant* lui ne pose pas de problème (c'est
ainsi que fonctionne le jugement d'acceptabilité : sans tableau, le `*` est
simplement écrit devant). Du texte *après* lui se retrouverait à côté de
l'arbre plutôt qu'après, et la macro vous le signale.

**Non pris en charge, et refusé explicitement** : toute commande LaTeX
(avec une barre oblique inverse), les étiquettes d'arête, les flèches
au-dessus de l'arbre, et les options de nœud autres que `roof` et `name=`.
Elles sont refusées par leur nom plutôt qu'ignorées en silence.

### 4.10 Annuler

Toute la construction est **une seule étape d'annulation**. Un **Ctrl+Z**
(⌘+Z) reprend l'exemple entier.

---

## 5. Modifier un exemple déjà composé

**LinguExx ▸ Décomposer l'exemple** fait le chemin inverse : placez le
curseur n'importe où dans un exemple composé, et il redevient les lignes
dont il a été fait —

```
(7)  Esto es un ejemplo glosado
     this is a example glossed
     'This is a glossed example.'
```

redevient trois paragraphes ordinaires, le **numéro** en tête du premier.
Ce numéro est toujours le champ vivant auquel renvoient tous les renvois du
document. Modifiez le texte, sélectionnez-le, recomposez-le : c'est le même
exemple, avec le même numéro et **les mêmes renvois**.

C'est ainsi qu'on modifie un exemple. Le corriger sur place oblige à
travailler cellule par cellule, et un mot ajouté demande une colonne que le
tableau n'a pas ; en composer un nouveau à la place lui donnait un numéro
neuf, et tous les `\ref` qui le visaient tombaient en panne
(*Erreur : source du renvoi introuvable*).

Le trajet aller-retour ne sert pas qu'à corriger une coquille :

- **N'importe quelle commande de composition reprend le texte** : un
  exemple glosé peut revenir en arbre numéroté, ou en paradigme
  `a. … b. …`, avec son numéro.
- **Tout est remesuré** sur la page et la police que vous avez maintenant,
  et le découpage en bandes est refait.
- Tout revient : les lettres de sous-exemples, les jugements, la
  traduction, les `{groupes entre accolades}` qui ne faisaient qu'une
  colonne, et la mise en forme de chaque passage.

Les lignes prennent le style de paragraphe du texte où elles atterrissent,
comme si vous y tapiez.

**Un arbre dessiné revient sous forme de crochets**, lignes `move`
comprises : le dessin conserve la notation dont il est issu, dans sa
**description** (Format ▸ Description — c'est aussi le texte alternatif que
demande un PDF balisé). Recomposez-le avec **Composer l'arbre numéroté** :
ici comme ailleurs, c'est la commande qui décide, jamais le texte.

> **La mise en forme des étiquettes ne revient pas.** Une description est
> du texte brut, et les marques qui transportent la mise en forme dans
> cette macro sont des caractères à usage privé qui s'y afficheraient comme
> des carrés. Une étiquette en italique le reste dans le dessin et revient
> en texte simple.

### Ce que la commande refuse

| situation | pourquoi |
|---|---|
| l'exemple contient un **dessin sans source** — une image, ou un arbre dessiné avant que les arbres ne conservent leurs crochets | il n'y a rien à rendre, et décomposer le perdrait |
| le tableau **n'est pas un exemple** | un exemple est encadré par les deux lignes d'espacement, et rien d'autre ne produit de telles lignes ; il s'agit donc d'un tableau que vous avez fait vous-même |
| l'exemple n'a **ni colonne de jugement ni traduction** | ce sont les deux choses qui disent où commence le texte de l'exemple ; seul un document converti qui ne juge jamais rien peut se présenter ainsi |

> **Documents antérieurs.** Un exemple trop long découpé en bandes et
> composé avant cette version ne porte pas la marque qui signale le début
> d'une bande : ses lignes de continuation reviennent comme des lignes de
> glose supplémentaires. Rassemblez-les à la main avant de recomposer —
> l'exemple recomposé, lui, portera la marque.

---

## 6. La renumérotation automatique

C'est l'intérêt principal du dispositif.

1. Placez le curseur avant un exemple existant et créez-en un nouveau.
2. **Outils ▸ Actualiser ▸ Champs**, ou simplement **F9**.

Tous les numéros suivants se décalent d'un cran.

---

## 7. Mise en forme : tout passe par des styles

L'extension n'utilise aucun formatage direct. Tout est un **style nommé**,
donc vous pouvez remettre en forme **tous les exemples du document d'un
coup** depuis le volet Styles (**F11**, rubrique *Styles personnalisés*).

| style | ce qu'il gouverne |
|---|---|
| `LxExampleCell` | toutes les cellules : langue objet, gloses, numéro |
| `LxTranslation` | la ligne de traduction libre |
| `LxJudgmentCell` | la colonne des jugements |
| `LxExampleBand` | la première ligne d'une bande de continuation ; il ne déclare rien et ne se voit pas — c'est une marque, qui permet de retrouver le découpage en bandes (§ 5) |
| `LxExampleSpace` | **la hauteur des deux espaces**, au-dessus et au-dessous |
| `LxExampleSpaceAbove` | hérite du précédent ; pour l'espace du haut seulement |
| `LxExampleSpaceBelow` | idem, pour l'espace du bas seulement |

### Changer l'espace autour des exemples

Le plus simple : **LinguExx ▸ Mise en page des exemples…** (§ 8), qui écrit
ces styles pour vous.

À la main : modifiez le style **`LxExampleSpace`** : onglet **Retraits et
espacement**, puis **Interligne : Fixe**, et donnez la hauteur voulue. Tous
les exemples du document suivent immédiatement.

Pour ne changer qu'un seul côté, donnez une hauteur propre à
`LxExampleSpaceAbove` ou `LxExampleSpaceBelow`.

> **Pourquoi un interligne fixe ?** L'espace est en réalité la hauteur
> d'une ligne de tableau vide placée en haut et en bas de chaque exemple.
> Un interligne fixe la règle **exactement** : 0 cm donne vraiment 0.

Ces styles sont exactement ceux qu'écrit le convertisseur `linguexx2odt` :
un document converti depuis LaTeX et un exemple ajouté à la main avec
l'extension sont le même objet et obéissent aux mêmes styles.

---

## 8. Régler la mise en page des exemples

**LinguExx ▸ Mise en page des exemples…** ouvre une boîte de dialogue qui
règle les cinq longueurs relevant de la maison d'édition plutôt que de la
mesure. Tout le reste — la largeur des colonnes, celle du bloc de texte, le
découpage des exemples trop longs — est mesuré ou lu sur la page, et n'est
pas réglable.

| | par défaut | ce que c'est |
|---|---|---|
| retrait jusqu'au numéro d'exemple | 0 cm | de la marge de gauche au `(1)` |
| retrait jusqu'à la lettre de sous-exemple | 1,1 cm | du numéro au `a.` |
| retrait jusqu'au texte du sous-exemple | 0,7 cm | du `a.` au texte qui le suit |
| espace au-dessus d'un exemple | 0,18 cm | le style `LxExampleSpaceAbove` |
| espace au-dessous d'un exemple | 0,18 cm | le style `LxExampleSpaceBelow` |

Chaque retrait se compte à partir du précédent :

```
|<- retrait ->|(1)|<- numéro ->|a.|<- lettre ->|Esto es un ejemplo
```

Le deuxième fixe donc aussi l'endroit où commence le texte d'un exemple
**principal** : la lettre d'un sous-exemple et le texte d'un exemple
principal sont au même x — c'est la géométrie de linguexx, et la raison
pour laquelle la colonne des jugements est prélevée sur la colonne de
gauche au lieu d'être insérée après elle.

Les deux retraits de sous-exemple sont des **minimums** : un numéro trop
large pour la colonne qu'on lui donne — `(100)`, ou `(12)` dans un grand
corps — obtient quand même la place qu'il lui faut, au lieu d'entrer en
collision avec l'exemple.

**Les deux sortes de réglage n'agissent pas de la même façon, et c'est
voulu :**

- **Les retraits ne s'appliquent qu'aux exemples composés ensuite.** Un
  exemple déjà dans le document est un tableau dont les colonnes sont
  déjà fixées ; rien ne revient le recomposer, exactement comme rien ne
  réaligne un exemple quand vous en modifiez un mot. Recomposez-le depuis
  son texte source si vous voulez qu'il bouge.
- **Les espaces, eux, remettent en forme tout le document d'un coup**,
  parce qu'ils *sont* les styles `LxExampleSpace*` (§ 7) : la boîte de
  dialogue n'est qu'une autre façon de les modifier. Deux valeurs égales
  sont écrites sur le style parent, dont les deux enfants héritent — une
  modification ultérieure du parent depuis le volet Styles déplace donc
  toujours les deux côtés ; deux valeurs différentes détachent chaque
  enfant.

**Les réglages appartiennent au document**, comme les styles, et le
suivent. Il n'y a pas de préférence globale : un article a une géométrie,
et pour l'avoir dans tous vos articles, réglez-la dans le **modèle** dont
vous partez. Les trois retraits sont rangés dans les propriétés
personnalisées du document (**Fichier ▸ Propriétés ▸ Propriétés
personnalisées** : `LinguExxIndentCm`, `LinguExxNumberCm`,
`LinguExxMarkerCm`) ; les espaces ne sont rangés nulle part ailleurs que
dans les styles, pour que le document n'ait pas deux réponses à la même
question.

Une longueur hors de l'intervalle 0–10 cm est refusée, et dans ce cas rien
n'est modifié.

> Un exemple avec retrait est le seul cas où le tableau ne s'étend pas sur
> tout le bloc de texte. La conséquence : sa largeur ne suit plus les
> changements de géométrie de la page, alors qu'un exemple sans retrait,
> lui, les suit.

---

## 9. Ce que l'extension refuse de faire

Elle ne devine pas quand la sélection est ambiguë :

| situation | ce qui se passe |
|---|---|
| rien n'est sélectionné | message demandant de sélectionner la ou les lignes |
| une lettre de sous-exemple apparaît **en cours** de sélection alors que la sélection ne commence pas par une lettre | message demandant de commencer à la première lettre |
| une lettre seule, sans rien après elle | message signalant qu'il n'y a pas de contenu |

---

## 10. Dépannage

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

## 11. Fabriquer le fichier `.oxt` soi-même

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
