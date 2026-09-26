# Registro: paper, abstract, protocolli, tesi, note di progetto, risposte ai reviewer

La prosa scientifica che l'utente accetta mette ogni cosa al suo posto nella gerarchia: prima il risultato, poi il numero che lo sostiene, poi soltanto il dettaglio che cambia il modo di leggerlo. Vale in italiano e in inglese; le coppie in fondo vengono dalla tesi di specializzazione dell'utente (settembre 2026) e sono il modello da seguire.

- **Una frase, un'affermazione.** La frase è lunga quanto l'affermazione che porta; quando due affermazioni condividono una frase, diventano due frasi. Un numero ha una frase intorno a sé, e una fila di cifre dentro una frase è una tabella ancora da disegnare.
- **Il paragrafo apre con la sua affermazione o con il suo risultato**, e svolge un compito solo, in tre o quattro frasi. Un rimando a una tabella, un denominatore o una cornice di contesto non lo aprono.
- **La sezione va dall'esito al meccanismo.** I risultati partono da ciò che il lavoro ha prodotto, i metodi dal quadro delle parti e delle loro funzioni; i passaggi operativi e le definizioni da manuale vengono dopo, o escono dal testo.
- **Le frasi si legano, le proposizioni non si impilano.** Il ragionamento passa da una frase all'altra con una conseguenza (quindi, pertanto), un'aggiunta (inoltre, infine) o un soggetto che riprende la frase precedente ("Questa dipendenza"); un'enumerazione è annunciata da una frase e le sue parti sono marcate (in primo luogo, in secondo luogo, infine).
- **Ogni affermazione dice ciò che è stato misurato, e niente di più.** Una misura si descrive insieme a ciò che non descrive; un'implicazione è un tema da approfondire, non il luogo dove intervenire; i quantificatori e gli intensivi che i dati non portano ("ogni", "soprattutto") restano fuori.
- **Un componente si descrive per funzione, ingresso, uscita e regola, e ha un nome solo**, quello della disciplina (concordanza, gruppo di confronto, unità aggregata), mantenuto in tutto il testo. Il registro nominale e le forme impersonali della prosa scientifica italiana vanno bene.
- **Registro della proposta.** Una nota di progetto o un protocollo descrivono un lavoro proposto: le azioni vanno al futuro o all'intenzione ("Questo lavoro si propone di costruire…", "la mappatura attraverserà…"); la struttura dell'oggetto proposto sta al presente ("il framework è una matrice a due assi").
- **Formulazioni difendibili davanti a un reviewer metodologico**: "set di riferimento adjudicato" o "reference set", dove "blind gold standard" sarebbe contestabile.
- Nella discussione i risultati positivi vengono prima dei limiti.
- I paper citati servono per il loro contenuto, dentro il filo del discorso: la narrativa è funzionale.
- Nei testi destinati a durare i riferimenti temporali sono datati ("nel 2026", dove "attualmente" invecchia).
- **Con un limite di lunghezza** si sceglie che cosa togliere e lo si elenca in chat, obiettivi e risultati compresi, così decide l'utente; i numeri che restano ma non servono al filo passano in una tabella. Si riporta il conteggio contro il limite.
- **Risposte ai reviewer**: tono fermo e cortese; ogni risposta apre con ciò che è stato fatto (o con il perché no), con ringraziamenti brevi e senza concessioni di maniera.

## Coppie prima e dopo

(dalla tesi di specializzazione, settembre 2026; "prima" è la versione di Claude, "dopo" quella accettata. Da imitare è la costruzione, non le parole.)

### Il risultato prima, il numero dopo

Prima:

> Nel confronto appaiato sulle stesse 294 iniziative la sola ricodifica del modello era corretta in 199 casi, la sola codifica originale in 29, entrambe in 50 e nessuna delle due in 16 (5,4%; test esatto di McNemar, p = 2,3 × 10^−32^); letta con la regola per cui si classifica la singola voce e non il suo contenitore, la codifica originale coincide con il riferimento nel 26,9% dei casi (79 su 294), e poiché la baseline codificava l'offerta nel suo complesso il valore quantifica il cambio di unità e non descrive un suo errore.

Dopo:

> Il confronto appaiato sulle stesse 294 iniziative documenta soprattutto l'effetto del cambio di unità di registrazione. La sola ricodifica del modello era corretta in 199 casi, la sola codifica originale in 29, entrambe in 50 e nessuna delle due in 16 (5,4%; test esatto di McNemar, p = 2,3 × 10−32). Applicando la regola attuale, che classifica la singola voce e non il contenitore, la codifica originale coincide con il riferimento nel 26,9% dei casi (79 su 294). Poiché la baseline codificava l'offerta nel suo complesso, questo valore quantifica il cambio di unità e non descrive un errore della baseline.

Le stesse parole, riordinate: la lettura che chiudeva una frase di 93 parole apre il paragrafo, e i numeri seguono in frasi proprie.

### Dall'esito al meccanismo

Prima:

> Dei 467 enti del registro, 56 sono in monitoraggio attivo e 411 soltanto registrati. Dai siti degli enti in monitoraggio attivo sono stati raccolti 1.285 candidati in due letture: 412 da otto enti fra il 12 giugno e l'11 agosto 2026, e 873 il 22 settembre 2026 dagli altri 49 (uno dei quali è passato quel giorno fra gli enti soltanto registrati), 37 dei quali pubblicano l'elenco delle proprie pagine, per 488.731 indirizzi in tutto; ne sono stati selezionati 8.283, i più recenti dell'ultimo anno fino a un massimo di 300 per ente, e letti 7.866, 891 pagine hanno superato il filtro e 873, di 31 enti, erano nuove.

Dopo:

> Il primo ciclo di sorveglianza ha prodotto 2.533 candidati attraverso i due canali automatici: 1.285 dai siti degli enti in monitoraggio attivo e 1.248 dalla ricerca sul web. Tutti i candidati hanno ricevuto un esito di revisione (Tabella 4): 66 sono stati ammessi, 9 sono in attesa della risposta dell'ente, uno è sospeso per approfondimento e 2.457 sono stati esclusi. Fra le 66 voci ammesse, 51 hanno richiesto correzioni ai campi proposti dal modello.

Il paragrafo parte da ciò che il ciclo ha prodotto, dà il totale, poi la sua ripartizione, poi le decisioni; l'imbuto del crawler esce dal testo.

### Un'enumerazione annunciata e marcata

Prima:

> Come le altre, ha tre limiti: diventa presto obsoleta, perché l'offerta si concentra negli anni più recenti (oltre metà delle iniziative censite cadeva negli ultimi due anni del periodo) e le pagine che la documentano vengono modificate o rimosse; registra ogni offerta nel suo complesso, per cui un corso di laurea con un solo modulo pertinente pesa quanto un corso interamente dedicato; non è ripetibile a costi sostenibili, perché ogni aggiornamento richiederebbe di rifare a mano la ricerca in cinque lingue.

Dopo:

> Questa rilevazione aveva tre limiti principali. In primo luogo, diventava rapidamente obsoleta: oltre metà delle iniziative censite ricadeva negli ultimi due anni del periodo e le pagine che documentavano l'offerta venivano modificate o rimosse. In secondo luogo, ogni offerta era registrata nel suo complesso, così che un corso di laurea con un solo modulo pertinente pesava quanto un corso interamente dedicato alla DPH. Infine, l'aggiornamento manuale non era sostenibile, perché avrebbe richiesto di ripetere periodicamente la ricerca in cinque lingue.

### L'affermazione misurata sull'evidenza

Prima:

> In Italia i due domini dei dati compaiono con una frequenza circa dimezzata rispetto al resto d'Europa, e la differenza persiste, sia pure attenuata, contando le offerte anziché i moduli. Il confronto è descrittivo e riguarda l'offerta documentata sul web; indica tuttavia dove intervenire.

Dopo:

> In Italia RAD e GGD sono meno frequenti rispetto al gruppo di confronto a livello di iniziativa; la differenza si riduce quando l'analisi è ripetuta a livello di unità aggregata, ma mantiene la stessa direzione. Il confronto riguarda l'offerta documentata e risente sia della copertura sia della granularità delle fonti. Indica quindi un tema da approfondire, ma non consente di stabilire se esista un fabbisogno formativo né quale sede o intervento sarebbe appropriato per affrontarlo.

### Esempi, condizioni, ciò che si trasferisce e il suo limite

Prima:

> L'impianto è stato progettato per essere adattato ad altri bisogni informativi della sanità pubblica, quali il monitoraggio della formazione continua accreditata, di altre offerte formative o di registri di risorse e servizi, nei quali l'informazione è distribuita fra numerosi soggetti e documentata prevalentemente da fonti pubbliche soggette a frequenti aggiornamenti, in assenza di un registro centrale. In tali contesti possono essere ripresi i principi metodologici del sistema, cioè criteri espliciti e versionati, acquisizione multicanale, archiviazione e tracciabilità delle fonti, preclassificazione automatizzata con decisione finale umana e misurazione periodica delle prestazioni per attributi di sorveglianza. I contenuti della mappa e le prestazioni osservate restano invece specifici di questo primo contesto; per ciascun nuovo ambito devono essere ridefiniti i criteri di eleggibilità, la tassonomia, il registro degli enti, il vocabolario di ricerca e le soglie operative, e la valutazione delle prestazioni dell'automazione deve essere ripetuta.

Dopo, scritto dall'utente:

> L'impianto è stato progettato per essere adattato ad altri bisogni informativi della sanità pubblica, come il monitoraggio della formazione continua accreditata, di altre offerte formative o di registri di risorse e servizi. Il disegno è particolarmente adatto a contesti nei quali l'informazione è distribuita fra numerosi soggetti, manca un registro centrale e la documentazione, prevalentemente pubblica, è soggetta a frequenti aggiornamenti. In questi ambiti possono essere trasferiti i principi metodologici del sistema: criteri espliciti e versionati, acquisizione multicanale, archiviazione e tracciabilità delle fonti, preclassificazione automatizzata con decisione finale umana e valutazione periodica delle prestazioni. La generalizzabilità riguarda quindi l'architettura metodologica, non i contenuti della mappa né le prestazioni osservate: per ogni nuova applicazione devono essere ridefiniti i criteri di eleggibilità, la tassonomia, il registro delle fonti, il vocabolario di ricerca e le soglie operative, e le prestazioni dell'automazione devono essere nuovamente misurate.

## Pattern appresi dalle correzioni dell'utente

(aldogor-style-learn aggiunge qui.)
