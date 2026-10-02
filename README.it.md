# Studio di efficienza nell’elaborazione dei dati

[English](README.md) | **Italiano**

Ho confrontato cicli Python, pandas e SQLite sugli stessi dati sintetici. Il mio obiettivo era capire come cambiano tempo e memoria quando lo stesso filtro, raggruppamento o JOIN viene implementato in modi diversi, con un esperimento riproducibile.

Per analisti junior e sviluppatori, questo studio mostra come impostare un confronto verificabile, controllare risultati equivalenti e interpretare il rapporto tra tempo e memoria. Il repository contiene programma, input generati, misure reali e analisi. L'esperimento è stato eseguito su un MacBook Air Apple M3 con 16 GB di RAM il 1 ottobre 2026. I record contengono interi sintetici, non dati di clienti reali.

## I miei risultati

Con un milione di righe, pandas ha ottenuto il tempo mediano più basso per tutte e tre le operazioni, sia includendo la preparazione sia nell'esecuzione warm. In modalità warm è stato **1,56 volte più veloce di Python nel filtro, 10,89 volte nel raggruppamento e 3,84 volte nel JOIN con aggregazione**.

Il dataset più piccolo cambia il quadro. Con 50.000 righe, il filtro warm ha richiesto **1,13 ms in Python e 1,35 ms in pandas**. Includendo caricamento e preparazione, l'ordine si inverte: **9,94 ms e 3,42 ms**, rispettivamente. Il confronto utile dipende da dove parte il cronometro.

![Tempo misurato: singole osservazioni, mediane e intervalli osservati](charts/elapsed_time.png)

Nel JOIN warm su un milione di righe, SQLite ha registrato una mediana del picco RSS inferiore a pandas: **128,91 MiB contro 229,83 MiB**. Il tempo è stato però maggiore: **317,70 ms contro 28,05 ms**. Valutare solo la velocità nasconderebbe questa differenza.

![Picco RSS dell'intero processo: singole osservazioni, mediane e intervalli osservati](charts/peak_memory.png)

I rapporti confrontano mediane in condizioni equivalenti e non dimostrano accelerazioni universali.

Tempo mediano con 1.000.000 di righe nella tabella dei fatti, in millisecondi:

| Operazione | Modalità | Python | pandas | SQLite |
|---|---|---:|---:|---:|
| Filtro | Process-cold | 223,09 | 27,94 | 509,94 |
| Raggruppamento e aggregazione | Process-cold | 173,93 | 17,51 | 815,28 |
| JOIN e aggregazione | Process-cold | 204,47 | 45,89 | 767,63 |
| Filtro | Warm | 27,55 | 17,68 | 64,07 |
| Raggruppamento e aggregazione | Warm | 72,13 | 6,62 | 380,16 |
| JOIN e aggregazione | Warm | 107,68 | 28,05 | 317,70 |

Consulta le [misure grezze](results/main/raw.csv), il [riepilogo completo](results/analysis/summary.csv) o il rapporto in russo in [PDF](reports/synthetic-processing-study-ru.pdf) e [DOCX modificabile](reports/synthetic-processing-study-ru.docx).

## Come leggere i grafici

I simboli piccoli mostrano le singole prove, quelli grandi le mediane; le barre indicano minimo e massimo osservati su cinque ripetizioni, non intervalli di confidenza. Le dimensioni dei dataset sono categorie equidistanti sull'asse x, non distanze numeriche proporzionali. Il tempo usa un asse y logaritmico comune alle operazioni della stessa modalità, con limiti diversi per cold e warm. Tra modalità, confrontare i valori degli assi, non l'altezza dei simboli. La memoria usa lo stesso asse y lineare con origine zero in tutti e sei i pannelli.

**Process-cold** comprende caricamento del file NPZ condiviso, preparazione, esecuzione, ordinamento e materializzazione completa del risultato; import e avvio del processo sono esclusi. Le cache dei file del sistema operativo non sono state svuotate: non è una misura a disco freddo. **Warm** comprende solo esecuzione e risultato completo dopo una prova preliminare non cronometrata. Ogni ripetizione usa un processo nuovo.

**Il picco RSS** è il massimo di memoria dell'intero processo fino al completamento della query, prima della verifica. Include import, array di input, preparazione e prova warm, non solo la memoria incrementale della query o la memoria fisica esclusiva. Le osservazioni riguardano una macchina e uno schema sintetico. L'energia non è stata misurata; non sono supportate conclusioni su energia o CO2. Vedere la [metodologia](docs/METHODOLOGY.md) e i [chiarimenti sulle misure](docs/IMPLEMENTATION_ADDENDUM.md).

## Avvio rapido: analizzare i dati raccolti

Eseguire dalla cartella del repository con Python 3.12. Questi comandi rigenerano statistiche e grafici senza eseguire il benchmark:

```sh
git clone https://github.com/Gr1gorii/processing-efficiency-study.git
cd processing-efficiency-study
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python src/analyze.py --machine-label "Apple M3 MacBook Air, 16 GB RAM"
python -m unittest discover -s tests -v
python src/audit_results.py
```

L'etichetta hardware descrive le misure incluse, non il computer usato per l'analisi. I grafici vengono salvati in PDF vettoriale e PNG. L'esportazione PNG richiede `pdftoppm` di Poppler oppure `sips` su macOS; i PDF restano disponibili se entrambi mancano. Il programma di raccolta è pensato per macOS e sistemi di tipo Unix; la raccolta su Windows non è stata validata.

## Cosa è stato confrontato

La matrice principale comprende 50.000, 250.000 e 1.000.000 di righe, tre implementazioni, tre operazioni, due modalità e cinque ripetizioni: **270 misure principali**. Un **pilot separato di 36 prove** ha verificato prima fattibilità e correttezza. La tabella clienti contiene 5.000 chiavi univoche. Gli input sono int64, senza valori nulli, stringhe o chiavi esterne prive di corrispondenza.

- **Filtro:** seleziona per stato e importo, restituendo coppie ID/importo ordinate.
- **Raggruppamento:** conta i record e somma gli importi per categoria.
- **JOIN:** esegue un inner join con i clienti, poi conta i record e somma gli importi per segmento.

Python usa liste di righe e un dizionario, pandas usa DataFrame interi e SQLite un database in memoria con chiave primaria sui clienti e nessun indice sulla tabella dei fatti. Il confronto riguarda queste implementazioni concrete e le loro diverse rappresentazioni.

Seed dei dati: `20261001`. Seed dell'ordine principale: `73129`. Blocchi e ordine sono stati randomizzati, eseguendo un processo alla volta. Versioni registrate: Python 3.12.14, NumPy 2.3.5, pandas 2.2.3, SQLite 3.53.1 e macOS 26.7.1. I limiti dei thread delle librerie numeriche erano impostati a 1; `PRAGMA threads=1` di SQLite limita i thread ausiliari della query, non i thread totali del processo.

## Correttezza e limiti

Tutti i **306 risultati misurati coincidono con i digest esatti di riferimento**. Sei test coprono casi calcolati a mano, soglie, valori negativi, input vuoti, chiavi JOIN senza corrispondenza, generazione deterministica e copertura delle combinazioni. L'audit verifica misure salvate, statistiche e provenienza senza raccogliere nuovi tempi.

Pilot e raccolta principale hanno usato 90,20 secondi di tempo dei processi misurato dal processo padre, rispetto al limite cumulativo di 900 secondi. Il massimo RSS osservato è stato 282,08 MiB. Non si sono verificati arresti di protezione o aumenti del contatore swapout registrato.

Ci sono solo cinque ripetizioni per condizione e una sola macchina. Applicazioni in background, affinità CPU e stato termico non erano controllati; il carico medio di sistema a un minuto è variato da 4,17 a 5,24. Le piccole differenze di tempo richiedono particolare cautela. Stringhe, valori nulli, chiavi sbilanciate, database su disco e indici diversi possono cambiare i risultati. L'energia non è stata misurata e questi tempi non permettono conclusioni su energia o CO2.

La [metodologia](docs/METHODOLOGY.md), i [chiarimenti prima del pilot](docs/IMPLEMENTATION_ADDENDUM.md) e la [decisione dopo il pilot](docs/PILOT_DECISION.md) documentano il disegno e le regole di arresto.

## Riprodurre o adattare l'esperimento

La guida [Run your own experiment](docs/RUN_YOUR_OWN.md), in inglese, spiega come raccogliere pilot e misure principali in una cartella separata, preservando i risultati pubblicati. Mostra come cambiare dimensioni, allineare generazione e configurazione, valutare il pilot e analizzare le nuove misure. Il programma ha un budget cumulativo di 15 minuti per i processi e un limite di 20 minuti per la campagna; rifiuta di sovrascrivere una raccolta esistente.

Per adattare un'operazione, modificare le tre implementazioni in `src/backends.py`, il riferimento indipendente in `src/dataset.py` e i test calcolati a mano in `tests/test_correctness.py`. Rigenerare input e manifest, poi verificare la correttezza prima delle misure. L'audit delle tabelle narrative riguarda la matrice originale; va adattato se lo studio cambia.

## Struttura del repository

- `src/`: generazione, metodi, processo per singola prova, raccolta, analisi e audit.
- `tests/`: test di correttezza e copertura delle combinazioni.
- `data/`: input NPZ canonici e manifest di riferimento.
- `results/`: CSV/JSON/JSONL grezzi, ordine, ambiente registrato e tabelle. Le [note sui dati pubblici](docs/PUBLIC_DATA.md) documentano la rimozione di percorsi locali e identificatori temporanei dei processi; le misure sono conservate.
- `charts/`: grafici di tempo e memoria in PNG e PDF.
- `docs/`: metodologia, decisioni e documentazione.
- `reports/`: rapporti in russo, incluso il documento esteso in PDF e DOCX.
