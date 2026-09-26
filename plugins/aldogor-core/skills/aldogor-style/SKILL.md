---
name: aldogor-style
description: >-
  Revisione di un testo in due passate, in italiano e in inglese: prima l'impianto (arco logico, sezioni che portano contenuto nuovo, termini orfani, tabelle e figure, coerenza interna), poi la prosa nel registro dell'utente per genere (paper, protocolli e tesi, email e note a un gruppo, messaggi, slide). Usala quando l'utente dice "aldogor-style", "umanizza", "humanize", "revisione di struttura", "togli il tono da AI", o chiede di scrivere o rivedere un'email, un messaggio, o le slide e le note di una lezione, di un talk o di un workshop ("slide", "deck", "lezione", "presentazione").
---

# Aldogor-style

Due passate sullo stesso testo: l'impianto, poi la prosa. Un'email o un messaggio fanno solo la seconda; un paper, una tesi, una nota, un protocollo, una risposta ai reviewer o un deck fanno entrambe.

## L'impianto

L'impianto si vede soltanto sull'intero documento. Si legge tutto, si ricostruisce la tesi e il passo che ogni sezione le fa fare, e si propongono tagli, fusioni e spostamenti, ciascuno con la sua ragione. Le ragioni tipiche: una sezione che ripete ciò che un'altra ha già dato; un concetto usato prima di essere introdotto, spesso il residuo di una sezione tolta; un dettaglio che arriva prima del contesto che serve a collocarlo; una tabella o una figura che dice ciò che il testo dice già; un tema che pesa quanto la letteratura disponibile invece di quanto conta per la tesi; numeri della sintesi che non coincidono con quelli del corpo. Una figura si guadagna il posto dove una tabella o un paragrafo non basterebbero: ogni elemento che il lettore non usa si toglie, e oltre una decina di elementi la figura si divide in una vista d'insieme e un dettaglio. Nei grafici l'incertezza ha un nome (DS, ES o IC, con la numerosità), le barre partono da zero, il colore non è mai l'unico modo di distinguere, e la figura si guarda alla dimensione in cui sarà stampata. Un paper o un protocollo si confronta, voce per voce, con la linea guida di reporting del suo disegno letta sul sito di EQUATOR, con l'estensione per l'intelligenza artificiale quando l'IA è oggetto dello studio (CONSORT-AI, SPIRIT-AI, STARD-AI, TRIPOD+AI, TRIPOD-LLM, DECIDE-AI; PRISMA-ScR per le scoping review); l'aderenza si dichiara solo dopo aver controllato tutte le voci. Le informazioni di supporto (licenze, verifiche, strumenti) stanno accanto all'elemento che sostengono. Se un intervento cambia la numerazione o i rimandi, si aggiornano; poi la seconda passata ricuce le frasi.

## La prosa

Il testo si scrive a partire dal profilo del suo genere, che dice che voce ha:

- paper, abstract, protocolli, tesi, note di progetto, risposte ai reviewer: [references/register-paper.md](references/register-paper.md);
- email formali e note propositive a un gruppo di lavoro: [references/register-email.md](references/register-email.md);
- messaggi brevi: [references/register-chat.md](references/register-chat.md);
- slide e speaker notes: [references/register-slides.md](references/register-slides.md).

I post LinkedIn hanno un registro proprio, nella skill di progetto aldogor-linkedin di aldogor-job-hunting. Gli altri generi seguono il paragrafo sull'italiano e i cinque punti qui sotto.

Un testo italiano si pensa in italiano fin dalla prima stesura. Ogni frase dice per prima la sua affermazione principale; i numeri e i dettagli che la sostengono vengono dopo, e ciò che non le serve passa in un'altra frase o esce dal testo. Il nesso tra una frase e la successiva è scritto (quindi, pertanto, inoltre, un soggetto che riprende la frase precedente), e la lunghezza di ogni frase la decide il suo contenuto. Il lessico è quello italiano proprio (*agenda di ricerca*, *risultati*, *principale*); restano in inglese i termini tecnici consolidati del dominio (framework, machine learning, scoping review, human in the loop). Un testo breve porta un'idea sola.

Ciò che l'utente vuole trovare in ogni testo, in italiano come in inglese:

1. **La cosa com'è.** Il testo descrive l'oggetto nel suo stato attuale e lo definisce in positivo. Chi legge non conosce le versioni precedenti né le scelte di perimetro, quindi il testo non le nomina e non le difende; e non nega interpretazioni che nessuno ha proposto ("sono proposte da scegliere insieme", dove "sono proposte, non un elenco chiuso" si difenderebbe da un'obiezione mai mossa).
2. **Il contenuto, subito.** Il testo attacca con ciò che ha da dire, senza annunciarsi, senza intestazioni di stato (bozza, documento di lavoro) e senza formule come "per rendere concreto…, ecco come…". I titoli sono asciutti: "L'HIA e la sua pipeline", non "Il contesto: l'HIA e la sua pipeline".
3. **La frase che dice la cosa.** Ogni affermazione è detta nella sua versione concreta, con le parole di chi descrive l'oggetto. La chiusa di un paragrafo è l'ultimo passo del ragionamento, con la stessa voce delle frasi prima.
4. **La punteggiatura italiana.** Punto, virgola, due punti, parentesi; i trattini come punteggiatura (—, –, --) non compaiono mai, in nessuna lingua.
5. **Parole scelte una per una.** La parola comune non torna due volte a breve distanza; il termine tecnico, che ha un nome solo, si ripete. Il grassetto marca un concetto chiave, raramente.

Prosa curata, lessico colto, un inciso, una frase breve d'enfasi non sono difetti: si corregge ciò che stona e si lascia ciò che è scritto bene.

## Prima bozza e bozze respinte

Quando il testo nasce qui e porterà la firma dell'utente, prima della bozza si chiedono due cose: l'idea che il lettore deve portarsi via, in una frase, e chi legge. Se l'utente le ha già date, non si chiede. Il testo segue l'idea: i contenuti da coprire sono materiale da cui scegliere, e un elenco di contenuti non diventa mai la traccia del testo, perché un testo costruito sull'elenco diventa un inventario.

Quando l'utente corregge la bozza a mano, il giro successivo riparte dal suo testo corretto, non da una stesura nuova, e ogni sua riscrittura resta scritta dove le sessioni successive la trovano (in Claude Code, l'inbox delle correzioni). Una bozza respinta nell'impianto invece non si ritocca: si riparte con due o tre versioni scritte ciascuna da un'idea diversa, dichiarata in una riga, e si consegnano senza raccomandazione. La versione scelta entra nel brief come riferimento.

## Consegna

Se si modifica un file, si applicano le modifiche e si dà un riepilogo compatto. I profili crescono con le correzioni a mano dell'utente, che le distilla con aldogor-style-learn.
