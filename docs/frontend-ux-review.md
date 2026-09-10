# Review UX AIE — affidabilità, semplicità e identità visiva

## Verdetto

La direzione decision-first è coerente con AIE. Non possiamo definirla «il miglior
frontend» senza prove con utenti e controllo nel browser. La proposta originale è
una visione di prodotto, non un contratto implementabile integralmente nello stato
attuale del core. Il vertical slice è la scelta da mantenere, con le correzioni sotto.

| Aspetto | Valutazione | Scelta per la prima versione |
| --- | --- | --- |
| Affidabilità | Fonti cliccabili e distinzione dato/ipotesi sono essenziali; un badge verde non prova completezza. | Esporre tempi, impronte, dati mancanti e limiti della verifica. |
| Semplicità | Sei sezioni più otto tab societari sono troppi punti di ingresso per il primo rilascio. | Quattro sezioni attive e fonti contestuali; dettagli tecnici progressivi. |
| Attrattiva | L'identità deve venire dalla chiarezza del dossier e della decisione. | Sidebar blu scuro, superfici chiare, gerarchia tipografica e colori riservati a stati significativi. |
| Input | La domanda naturale è una buona destinazione, ma richiede interpretazione e conferma affidabili. | Dichiarare la ricerca nell'archivio e l'import strutturato; niente finta analisi dal ticker. |
| Continuità | Ogni vista deve mostrare lo stesso insieme di input nel tempo. | Collegamenti esatti per ID, impronta, data e modalità; aggiornamento esplicito. |

## Correzioni importanti alla proposta

1. **Togliere stelle e barre complessive di qualità/fit.** Sono punteggi impliciti anche
   senza il numero 87/100. Mostrare componenti, vincoli e trade-off canonici.
2. **Non chiedere capitale per valutare una società da sola.** L'importo appartiene
   all'allocazione; Underwriting resta indipendente dal portafoglio.
3. **Non promettere un confronto arbitrario di candidati.** Il core attuale confronta
   esattamente candidata, posizione esistente eleggibile, ETF core e liquidità
   investibile. Un confronto diverso richiede un contratto approvato.
4. **Non mostrare un totale in euro senza FX ammesso.** Valori, concentrazione e
   variazioni restano nei libri in valuta nativa. I driver sovrapposti non sono additivi.
5. **Non confondere associazione e causalità.** La presenza in un ETF o un tag economico
   non costituisce una catena causale dimostrata. Un futuro grafo deve distinguerli.
6. **Non trasformare confidenza qualitativa in probabilità.** Mantenere visibile lo
   stato di calibrazione; gli scenari non hanno probabilità assegnate automaticamente.
7. **Non inventare condizioni operative.** Nel core ammesso STAGED deriva dal limite
   esplicito per ordine, non da una previsione di volatilità. Piano e ordine eseguito
   sono oggetti diversi; un ritorno osservato non è un profitto realizzato.
8. **Non scambiare esito positivo e buona decisione.** Learning deve tenere separati
   risultato, tesi e qualità del ragionamento; un singolo caso non prova capacità predittiva.

## Architettura e manutenzione

React/TypeScript/Vite rimane una scelta compatibile con il core Python. TanStack Query
serve alla gestione delle richieste, Zod al contratto di trasporto. Tailwind, shadcn,
grafi, charting e Tauri non sono requisiti di affidabilità: li introdurrei quando un
bisogno concreto giustifica la dipendenza. Nella 0.1 HTML semantico, dialog nativi e
CSS condiviso coprono il percorso scelto senza un nuovo design-system runtime.

Riferimenti tecnici consultati:

- [React: building from scratch](https://react.dev/learn/build-a-react-app-from-scratch)
- [TanStack Query: important defaults](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults)
- [W3C: native modal dialog technique](https://www.w3.org/WAI/WCAG22/Techniques/html/H102)

Queste fonti spiegano le primitive, non certificano l'affidabilità del prodotto AIE.

## Cosa resta da validare

L'import JSON è il maggiore ostacolo alla semplicità attuale. Il passo successivo è
un inserimento guidato che costruisca bozze dei contratti esistenti, conservando
provenienza, ipotesi e conferma; non un LLM che salti la validazione del core.
Prima di dichiarare conclusa la review visiva servono prove nel browser e le cinque
attività di accettazione del documento Chapter 12. Non sono state sostituite con un
voto estetico inventato o con la sola copertura dei test.
