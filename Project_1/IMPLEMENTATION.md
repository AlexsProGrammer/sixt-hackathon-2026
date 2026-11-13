# IMPLEMENTATION — Ein durchgehender Plan für eine Person mit Coding-Agent

## 1. Auftrag und Arbeitsweise

- Arbeite diesen Plan von oben nach unten durch. Eine Person und ein Coding-Agent besitzen den gesamten Implementierungsablauf.
- Dieser Plan ersetzt die bisherigen Rollenpläne `IMPLEMENTATION_A.md`, `IMPLEMENTATION_B.md` und `IMPLEMENTATION_C.md`. Diese Dateien sind historische Referenzen. Verwende für neue Arbeit ausschließlich diesen Ablauf.
- Verwende einen Arbeitsbranch für alle Änderungen. Der aktuell geprüfte Checkout steht auf `feat/abstention`; dort ist das Grounding-/probly-Paket vorhanden. Setze auf diesem Branch fort, sofern der Benutzer keinen anderen Branch vorgibt. Ein Branch pro Modul ist unnötig.
- Prüfe vorhandenen Code vor jeder Implementierung und verwende funktionierende Teile weiter. Die bisher gemeldeten 29 bestandenen Modultests sind erneut auszuführen, bevor du den Zustand als verifiziert übernimmst.
- Führe nach jeder Phase die angegebene Verifikation aus. Bei Erfolg gehe selbstständig zur nächsten Phase über. Behebe lokale Fehler im eigenen Arbeitsstand und wiederhole die betroffene Prüfung.
- Gib nach jeder Phase kurz an, was geändert wurde, welche Tests bestanden haben, was noch offen ist und was du als Nächstes ausführst. Fordere keine Teamübergaben oder Bestätigung zwischen erfolgreich geprüften Phasen an.
- Führe Git-Commits, Pushes und den abschließenden Merge im Rahmen der tatsächlichen Benutzerautorisierung aus. Die Umstellung auf einen Einzelplan erteilt allein keine neue Git-Freigabe.
- Halte funktionierende Zwischenstände fest. Für die Integration der eigenen Module ist kein Push oder Merge nach main erforderlich. Erst am Ende wird der getestete Gesamtstand gemeinsam veröffentlicht.

## 2. Ziel, Ausgangslage und Umfang

- Erweitere `4_extract.py` zu einer Pipeline, die für jedes Schema-Feld `value` und eine explizite endliche `confidence` in [0,1] ausgibt. Verwende bei Abstention `value=null, confidence=0.0`.
- Optimiere die gemessene Ersparnis bei Review-Kosten 1 und Fehlerkosten 100. Ein falscher akzeptierter Wert kann die Ersparnis vieler richtiger Werte aufheben.
- Bewahre die gelieferten Originale `1_download.sh`, `2_prepare.py`, `3_baseline.py`, `4_extract_example.py`, `5_score.py` und `test_score.py` unverändert. Eigene Implementierung erfolgt in der Teamkopie `4_extract.py` und eigenen Unterordnern.
- Verwende den offiziellen Scorer mit seiner vorhandenen Threshold-Suche, Schema-Validierung und Kostenanalyse. Ergänze nur Datenvorbereitung, Ausgabevollständigkeit und einen kleinen Adapter.
- Die Module `uncertainty/grounding.py`, `uncertainty/policy.py`, `uncertainty/uq_probly.py` und `tests/test_b_policy.py` sind im aktuell geprüften Checkout vorhanden. Der bestehende Testdateiname darf erhalten bleiben.
- Prüfe den Stand von `4_extract.py` neu. Beim letzten Codevergleich waren Chunking, Batching, verbesserte Prompt-Regeln und Poolsteuerung noch offen. Pfadnormalisierung und Laden der .env waren bereits vorhanden.
- Berücksichtige das beobachtete gemeinsame API-Limit mit HTTP 429. Nutze lokale Mocks für Entwicklung. Plane reale Requests anhand der verfügbaren Quote.
- Verbindlicher Umfang umfasst die sechs Reparaturen, die vorhandene probly-Aggregation im echten Ausführungspfad, Evaluation und reproduzierbare Abgabe.
- Vision/OCR, trainierte Kalibrierung, Credal Sets und Conformal Risk Control sind spätere optionale Erweiterungen. Scans ohne Text erhalten im Basismodell einen dokumentierten Null-Fallback.
- Die früheren 150 Minuten sind ein Zielbudget. Prüfe die tatsächlich verbleibende Zeit und reserviere ausreichend Zeit für Evaluation und Abgabe. Melde unvollständige Prüfungen ehrlich.

| Reihenfolge | Zielbudget | Ergebnis |
|---|---|---|
| 1. Bestand prüfen | 10 Minuten | Wiederverwendbarer getesteter Ausgangsstand |
| 2. Dokumente und Prompts | 25 Minuten | Vollständige Texte, Chunks und Batches |
| 3. API und Zusammenführung | 25 Minuten | Robuster Transport und vollständige Samples |
| 4. probly integrieren | 15 Minuten | Gesamte Extraktion mit Grounding/UQ |
| 5. Evaluation vorbereiten | 20 Minuten | Passende Gold-Mengen und Ausgabeprüfung |
| 6. Messen und entscheiden | 20 Minuten | Deklarierter Threshold und Kennzahlen |
| 7. Abgabe | 35 Minuten | Startbefehl, Bericht, Slides und veröffentlichbarer Stand |

## 3. Dateien und Abhängigkeiten

```text
Project_1/
├── IMPLEMENTATION.md
├── 4_extract.py
├── pipeline/
│   ├── __init__.py
│   ├── requests.py
│   ├── merge.py
│   └── transport.py
├── uncertainty/
│   ├── __init__.py
│   ├── grounding.py
│   ├── policy.py
│   └── uq_probly.py
├── evaluation/
│   ├── __init__.py
│   ├── prepare.py
│   ├── validate.py
│   └── select_threshold.py
├── tests/
│   ├── test_b_policy.py
│   ├── test_extraction.py
│   ├── test_evaluation.py
│   └── test_integration.py
├── submission/
│   ├── decision.json
│   └── slides.pdf
├── run_hidden.sh
├── requirements.txt
├── SUBMISSION.md
├── EDA.md
├── results/                 # lokale Runs und Vorhersagen
└── cache/                   # lokale erfolgreiche Modellantworten
```

- Verwende Python 3.12, Standardbibliothek, die vorhandenen requirements und `probly==0.9.1`. Nutze pypdf für PDF-Text, urllib für HTTP, concurrent.futures für den Workerpool, unittest für Tests.
- Alle Befehle laufen aus `Project_1`. Aktiviere unter PowerShell mit `.\.venv\Scripts\Activate.ps1` die vorhandene Umgebung. Alternativ ersetze `python` in Befehlen durch `.venv\Scripts\python.exe`. Unter Linux verwende `.venv/bin/python`.
- Installiere fehlende Abhängigkeiten mit `python -m pip install -r requirements.txt`. Ergänze probly nach erfolgreicher lokaler API-Prüfung in requirements.txt.
- Lade `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` aus der lokalen Umgebung/.env. Bereits gesetzte Prozessvariablen haben Vorrang. Verlange für den externen Veranstalter-Endpunkt eine gültige HTTPS-URL; lokale Mock-Tests dürfen HTTP verwenden.
- Gib Secrets weder in Logs noch in Artefakten aus. Verwende ausschließlich erlaubte öffentliche/Mock-Daten. Halte Rohdaten, Cache, Vorhersage-JSONL und Logs lokal und gitignoriert.
- Dokumentiere den externen API-Datenfluss. Verwende für Slides lokale Schriftarten und ausschließlich geeignete Beispielinhalte.

## 4. Modulverträge innerhalb der gemeinsamen Implementierung

- Verwende JSON-kompatible Dictionaries/Listen. Reine Grounding-/UQ-Funktionen verändern ihre Eingaben nicht und greifen weder auf Dateien noch APIs zu.
- `FieldPrediction` enthält `value` als JSON-Wert oder null und `confidence` als endliche Zahl in [0,1]. Bool ist kein gültiger Confidence-Wert. `Fields` ist eine Map von Feldname auf FieldPrediction.
- `Sample` enthält `sample_idx: int`, `complete: bool`, `fields: Fields`. Mehrere Chunks/Batches gehören zu einem Sample; sie zählen nicht als unabhängige Samples.

| Funktion | Input | Return und Verhalten |
|---|---|---|
| `build_jobs(text, schema, *, chunk_chars, overlap_chars, batch_size, samples)` in pipeline/requests.py | Vollständiger Text, Schema und positive Größen | Liste von Jobs mit sample_idx, chunk_id, batch_id, start, end, text, field_names und Teilschema. Jede Job-ID ist eindeutig. |
| `merge_sample(job_results, schema, sample_idx)` in pipeline/merge.py | Für jeden geplanten Job Metadaten, answer und ok | Ein Sample. Jeder fehlgeschlagene Job bleibt mit ok=false enthalten; complete ist dann false. Deterministisch unabhängig von Pool-Reihenfolge. |
| `is_grounded(value, text, field_schema)` in uncertainty/grounding.py | Kandidat, vollständiger Text oder None, Feldschema | Bool. Fehlende oder nicht prüfbare Evidenz ergibt false. |
| `apply_policy(answer, schema, text)` in uncertainty/policy.py | Modell-Feldmap, Schema, vollständiger Text | Vollständige Fields-Map. Ungültiges, Fehlendes und Unbelegtes wird null/0. |
| `aggregate_samples(samples, schema, text)` in uncertainty/uq_probly.py | Liste vollständiger Sample-Objekte | Dict mit fields und diagnostics. Leere/ungültige/unvollständige Samples führen im bestehenden Vertrag zu dokumentweiter Abstention. |
| `validate_predictions(records, predictions)` in evaluation/validate.py | Listen von Eingabe-Records und Prediction-Zeilen | Liste von Fehlerstrings. Leere Liste bedeutet gültige vollständige Ausgabe. |
| `choose_threshold(gold_records, predictions, error_cost=100.0)` in evaluation/select_threshold.py | Gold-Records und Prediction-Zeilen | Entscheidungsdaten aus dem offiziellen Scorer. Predictions vor score() in doc_id -> Fields umwandeln. |

- `diagnostics` enthält n_samples, complete, method und per_field. Pro Feld enthält es agreement, entropy, n_clusters, grounded und reason. Entropie wird in Nats dokumentiert.
- Prediction-JSONL enthält pro Dokument genau `doc_id` und `fields` mit allen Schema-Feldern. Iteriere während der Inferenz ausschließlich über schema.properties und verwende niemals gold.
- Für `--out results/run.jsonl` schreibe `results/run.diagnostics.jsonl` und `results/run.manifest.json`. Diagnostics enthalten eine Zeile pro geschriebener Prediction.
- Manifest enthält contract_version=1, run_id, pipeline, n_requested, n_written, n_failed, requests, cache_hits, elapsed_seconds. Pipeline enthält model, prompt_version, samples, temperature, workers, chunk_chars, overlap_chars, batch_size.
- `submission/decision.json` enthält contract_version=1, run_id, threshold, abstain_all, method, pipeline sowie gemessene n_docs, n_fields, accepted, wrong, hallucinated und net_saving_pct. Übernehme pipeline aus dem ausgewerteten Manifest.
- `net_saving_pct` übernimmt den Anteil des offiziellen Scorers; multipliziere für die Prozentanzeige mit 100.
- Erhalte `--data`, `--out`, `--limit`, `--mode`. Ergänze `--workers`, `--samples`, `--temperature`, `--chunk-chars`, `--overlap-chars`, `--batch-size`, `--on-error fail|abstain`, `--abstain-all`, `--decision`.
- `--decision` lädt die gespeicherte Pipelinekonfiguration. Prüfe Modell/Promptversion und erkenne widersprüchliche Overrides. All-Abstain setzt alle Werte auf null/0 und funktioniert vor Prüfung der API-Konfiguration.

## 5. Sequenzielle Umsetzung

### Phase 1 — Bestand sichern und vorhandenes probly-Paket verifizieren

- [ ] Prüfe Branch, Status und Dateibaum. Bewahre vorhandene Änderungen. Vergleiche vorhandenen Code mit diesem Plan; markiere bereits erfüllte Schritte anhand von Tests.
- [ ] Prüfe, dass `4_extract.py` die eigene Kopie ist. Falls sie fehlt, kopiere den vorhandenen Starter in diese Datei. Notiere Hashes der geschützten Originaldateien für den Abschlussvergleich.
- [ ] Prüfe die bestehenden uncertainty-Module und die installierte probly-Version. Verwende `create_categorical_distribution` und die vorhandene Entropie-API entsprechend ihrer lokal geprüften Signaturen.
- [ ] Verifiziere Grounding ohne Freipass für lange Werte, Erhalt von Zahlentrennzeichen, Confidence-Validierung und null/0-Abstention. Kontrolliere, dass K=1 exakt dem Policy-Ergebnis entspricht.
- [ ] Ergänze `probly==0.9.1` in requirements.txt, sofern es fehlt.
- [ ] **Verification:** Führe `python test_score.py`, `python -m unittest discover -s tests -p test_b_policy.py` und `python 4_extract.py --help` aus. Erwarte Exit 0. Melde den tatsächlich geprüften Ausgangsstand und gehe weiter.

### Phase 2 — Vollständige Dokumente, Chunks, Batches und Prompt

- [ ] Entferne in `4_extract.py` alle stillen 60k-Slices aus den Textladepfaden. Lade CUAD-Texte einmal und vor Poolstart. Lies vorhandene Seiten in Reihenfolge. Behalte plattformübergreifende Pfadauflösung und prüfe mit pathlib, dass aufgelöste Pfade unter DATA liegen.
- [ ] Erkenne leere/unlesbare PDFs. Gib für diese vollständige Null-Vorhersagen und den Diagnosegrund unreadable aus. Führe dafür keinen externen PDF-Upload aus.
- [ ] Implementiere in `pipeline/requests.py` build_jobs. Beginne mit konfigurierbaren 45.000 Zeichen und 3.000 Überlappung. Decke den vollständigen Text inklusive Ende lückenlos ab. Prüfe 0 <= overlap < chunk_chars.
- [ ] Prüfe das tatsächliche Modellkontextlimit und reserviere Platz für Schema, Prompt und Antwort. Zeichenwerte sind eine Startkonfiguration und keine Token-Garantie.
- [ ] Teile Schemafelder stabil in Batches mit maximal zehn Feldern. Jeder Chunk erhält jeden Batch für jedes Sample. Bewahre Feldbeschreibungen vollständig; verkleinere den Batch bei zu großem Prompt.
- [ ] Ergänze in `4_extract.py` Typ, Normalizer und vollständige Beschreibung im Prompt. Verlange wörtliche Strings und befolge explizite numerische/Datums-Vorgaben. Sichtbare Checkboxen werden als Strings true/false ausgegeben; fehlende Abschnitte als null. Verlange stets Confidence und behandle Dokumenttext als Daten.
- [ ] Erstelle `tests/test_extraction.py` mit synthetischem Text >60k und Evidenz am Ende, Batch-Vollständigkeit, Grenzgrößen, Windows-Pfaden und Scan-Fallback ohne Request.
- [ ] **Verification:** Führe `python -m unittest discover -s tests -p test_extraction.py` aus. Erwarte erfolgreiche Prüfungen einschließlich der Textstelle hinter Zeichen 60.000.

### Phase 3 — Transport, Cache, Parser und Sample-Zusammenführung

- [ ] Implementiere in `pipeline/transport.py` urllib-Aufrufe mit Timeout und klaren Fehlerklassen. Logge Status, Dokument-ID und Fehlerklasse ohne rohe vertrauliche Antwortinhalte.
- [ ] Begrenze Retries pro Request und das gesamte Wartebudget des Laufs. Starte mit höchstens einem Retry und 60 Sekunden Gesamtwartebudget. Beachte Retry-After als Sekunden oder HTTP-Datum. Wiederholtes 429 oder längere Warteangaben stoppen weitere Requests dieses Laufs.
- [ ] Verwende ThreadPoolExecutor mit `--workers`, Standard 1. Begrenze eingereichte Jobs, teile den 429-Stopzustand und schreibe Ergebnisse ausschließlich über einen Writer. Teste Workerzahl 1 und 2 mit deterministischen Mock-Antworten.
- [ ] Implementiere SHA-256-Cache über Endpoint, Modell, vollständigen Payload und sample_idx. Speichere erfolgreiche valide Modellobjekte atomar mit tempfile/os.replace. Cache-Hits sind neue Auswertungen derselben Antwort; sie zählen nicht als unabhängige Samples.
- [ ] Parse JSON-Objekte und klar abgegrenzte Codefences. Ungültiges JSON, leere Antworten und Listen erzeugen sichtbare Parsefehler. Vermeide stilles Umwandeln eines Fehlers in ein erfolgreiches leeres Ergebnis.
- [ ] Implementiere merge_sample in `pipeline/merge.py`. Erzeuge für jeden Job auch im Fehlerfall ein Resultat. Unterschiedliche skalare Kandidaten führen zu null/0; gleiche werden zusammengeführt. Ein Nullfund in einem Chunk verwirft einen belegten Fund in einem anderen Chunk nicht.
- [ ] Dedupliziere CUAD-Spans in Quellreihenfolge und verbinde separate Belege mit ` | `. Verwende bei verbundenen Belegen die kleinste gültige Confidence. Verifiziere Evidenz anschließend durch die bestehende Policy.
- [ ] Verwende beim Sampling Sample 0 mit Temperatur 0 und weitere Samples mit konfigurierter Temperatur, zunächst 0.7 sofern unterstützt. Prüfe Modellunterstützung; dokumentiere bei Bedarf eine abgestimmte Promptvariation.
- [ ] Prüfe vorhandene Outputdateien auf beschädigte Zeilen und doppelte IDs. Erlaube Resume nur für ausdrücklich fortgesetzte Runs mit identischer Pipelinekonfiguration. Nutze für geänderte Varianten frische Ergebnisdateien.
- [ ] Im Fehlermodus fail bleiben technische Fehler ungeschrieben und der Lauf endet mit Exit 1. Im Modus abstain erhalten betroffene Dokumente null/0 und eine Fehlerdiagnose. Zähle angefragte, geschriebene und fehlgeschlagene Dokumente separat.
- [ ] **Verification:** Erweitere `tests/test_extraction.py` um Cache-Hits, Payload-Änderung, kaputtes JSON, Timeout, 429-Stopp, Chunk-Konflikte und Resume. Führe `python -m unittest discover -s tests -p test_extraction.py` aus. Patche Wartezeiten; erwarte Exit 0 ohne reale API-Aufrufe.

### Phase 4 — Vorhandene Grounding-/probly-Module vollständig einbinden

- [ ] Verbinde in `4_extract.py` Textladen -> Jobs -> Transport -> Parsing -> merge_sample -> aggregate_samples -> Prediction und Diagnosen. Prüfe vor Aggregation, dass alle erwarteten Samples enthalten sind.
- [ ] Bewahre den vorhandenen Grounding-Vertrag. Prüfe zusammenhängende Belege, Token-Grenzen und bei CUAD jeden durch ` | ` verbundenen Teil. Bool-/Checkbox-/JSON-Felder bleiben konservativ zurückgestellt, soweit keine vollständig geprüfte Evidenzlogik existiert.
- [ ] Verifiziere den vorhandenen probly-Pfad. Policy wird je Sample vor Clustering ausgeführt. Null ist ein eigener Cluster. Nutze normalisierte exakte Gleichheit; Token-F1 ist keine transitive Äquivalenzrelation.
- [ ] Verifiziere Verteilungserstellung und Entropieberechnung mit probly. Gleichstand oder null-Gewinner ergibt Abstention. Sonst ist der Score das Minimum aus Gewinneranteil und kleinster Modell-Confidence der Gewinner. Bei K=1 bleibt die gültige Modell-Confidence erhalten.
- [ ] Dokumentiere unkalibrierte Scores sowie die Grenze, dass Textvorkommen keine korrekte Feldzuordnung garantiert. Bewahre die dokumentweite Abstention bei unvollständigen Samples zunächst als bekannten Coverage-Kostenpunkt.
- [ ] Implementiere Dateiverträge und CLI-Optionen aus Abschnitt 4. Erzeuge für --abstain-all gültige vollständige Ausgabe ohne Credentials oder HTTP-Aufruf.
- [ ] Erstelle `tests/test_integration.py` mit lokalem HTTP-Mock und echter CLI. Prüfe K=1, K=3, gold-freie Eingabe, belegte/unbelegte Werte, kaputtes JSON, Scan-Fallback und All-Abstain.
- [ ] **Verification:** Führe `python -m unittest discover -s tests -p "test_*.py"` und `python test_score.py` aus. Erwarte Exit 0 und tatsächliche probly-Aufrufe im Integrationstest. Gehe danach unmittelbar zur Evaluation über.

### Phase 5 — Datenvorbereitung und vorhandenen Scorer nutzen

- [ ] Implementiere `evaluation/prepare.py` mit --data, --out-dir und --seed. Teile dev deterministisch nach Dokumentgruppen analog zu 2_prepare.py; zusammengehörige Seiten bleiben zusammen. Schreibe dev_train_gold/input und dev_cal_gold/input sowie ein Split-Manifest. Entferne gold aus Inferenzdateien.
- [ ] Implementiere `evaluation/validate.py` ausschließlich für eindeutige/exakt passende Dokument-IDs, vollständige Schemafelder und explizite endliche Confidence-Werte. Null erfordert Confidence 0. CLI --input/--pred gibt bei Erfolg VALID und Exit 0 aus.
- [ ] Implementiere `evaluation/select_threshold.py` als kleinen Adapter über importlib zur originalen score-Funktion. Verwende die Map doc_id -> Fields wie load_preds. Übernehme den auf Dev ermittelten business.threshold. Erzeuge bei threshold=None All-Abstain mit threshold=1.0.
- [ ] Berechne Counts am gewählten Threshold mit dem offiziellen Scorer. Beim All-Abstain-Fall bewerte tatsächlich null gesetzte Vorhersagen; Threshold 1.0 allein könnte einen Wert mit Confidence 1 noch akzeptieren.
- [ ] Ergänze den Adapter um --gold, --pred, --manifest und --out. Kopiere Pipeline/Run-ID aus dem passenden Manifest in decision.json. Prüfe IDs und Manifestkonsistenz vor Auswahl.
- [ ] Erstelle `tests/test_evaluation.py` mit erfundenen Records einschließlich tags und von Hand erwarteten Counts. Prüfe Split-Disjunktheit, ungültige Ausgabe und Threshold-/All-Abstain-Auswahl. Verwende die offiziellen Bewertungsfunktionen.
- [ ] **Verification:** Führe `python -m unittest discover -s tests -p test_evaluation.py` sowie `python -m evaluation.prepare --data data/unified/dev.jsonl --out-dir results/split --seed 42` aus. Erwarte erfolgreiche Tests und vier JSONL-Dateien mit disjunkten Gruppen.

### Phase 6 — Reale Messung, Threshold und Freeze

- [ ] Prüfe verfügbare Zeit und API-Quote. Lege die ausgewertete Dev-Auswahl vor dem Lauf fest. Speichere passende gold-freie Eingabe als results/final_dev_input.jsonl und Gold als results/final_dev_gold.jsonl.
- [ ] Starte mit `python 4_extract.py --data results/final_dev_input.jsonl --out results/final_dev_predictions.jsonl --mode llm --workers 1 --samples 1 --on-error abstain`. Verwende bei Wiederholungen frische Run-Dateien entsprechend der Variante.
- [ ] Vergleiche K=1 und K=3 auf denselben Dokumenten, soweit Quote/Zeit reichen. Berichte Requests, Cache-Hits, Fehler und Laufzeit. Kennzeichne K=3 bei ausschließlich lokalen Tests als Mock-geprüft.
- [ ] Entwickle auf dev_train; friere Prompt/Policy vor Threshold-Auswahl auf dev_cal ein. Bereits zur Fehlerbehebung betrachtete Smoke-Dokumente sind Entwicklungsdaten. Dokumentiere kleine Stichproben und technische Ausfälle.
- [ ] Führe den Decision-Adapter auf der festgelegten Cal-Auswahl aus. Bezeichne das Ergebnis als empirische Auswahl. Wähle All-Abstain, wenn die vorhandenen Ergebnisse keine verantwortbare positive Variante tragen; dokumentiere Umfang und Unsicherheit.
- [ ] Bewerte den deklarierten Threshold mit `5_score.py` und --error-cost 20, 100 und 500. Verwende denselben Threshold und dieselben finalen Predictions. Berichte declared/at_threshold; business ist ein optimierter Sweep und kein finales Testergebnis.
- [ ] Werte test_public erst nach Freeze einmal aus, soweit Zeit/Quote reichen. Berichte unvollständige Abdeckung ausdrücklich. Verwende Testergebnisse ausschließlich für den Abschlussbericht.
- [ ] **Verification:** Führe `python -m evaluation.validate --input results/final_dev_input.jsonl --pred results/final_dev_predictions.jsonl` aus und erwarte VALID. Prüfe `python -m json.tool submission/decision.json` sowie Counts und Pipelinewerte gegen den tatsächlichen Run.

### Phase 7 — Reproduzierbare Abgabe und Slides

- [ ] Passe `run_hidden.sh` an den echten Aufruf `4_extract.py --data "$1" --out "$2" --mode llm --on-error abstain --decision submission/decision.json` an. Arbeite aus Project_1 und gib Python-Exitcodes korrekt weiter. Stelle sicher, dass alte Outputs niemals unbemerkt übernommen werden.
- [ ] Vervollständige SUBMISSION.md mit Ansatz, Modellwahl, gemessenen Ergebnissen, Baselines, Threshold, Laufzeit/Kosten soweit messbar, Konfiguration, How-to-run und Grenzen. Prüfe EDA.md und erhalte notwendige Credits.
- [ ] Erstelle maximal fünf Folien als submission/slides.pdf. Zeige Problem/Kosten, Pipeline, gemessenen Vergleich, ein akzeptiertes und ein abstiniertes Beispiel sowie Wiederverwendbarkeit/Grenzen. Öffne die PDF und prüfe Lesbarkeit und Seitenzahl.
- [ ] Bereite einen 3-Minuten-Pitch vor. Erkläre den gesamten Ablauf einschließlich der tatsächlich implementierten probly-Nutzung und der ungetesteten Bedingungen.
- [ ] Prüfe in einer frischen Umgebung gold-freien Input. Verwende Linux, sofern verfügbar. Dokumentiere sonst den Windows-/Mock-Nachweis und Linux als ausstehend.
- [ ] Vergleiche die Hashes der geschützten Originaldateien mit Phase 1. Prüfe Git-Diff und Secret-/Daten-Ausschlüsse. Veröffentliche den getesteten Gesamtstand nach vorhandener Autorisierung auf dem Team-Repo; plane einen Puffer für Remote-Kontrolle ein.
- [ ] **Verification:** Führe unter Linux `bash run_hidden.sh results/release_input.jsonl results/release_predictions.jsonl` und anschließend `python -m evaluation.validate --input results/release_input.jsonl --pred results/release_predictions.jsonl` aus. Erwarte Exit 0/VALID. Prüfe final GitHub-Dateien, PDF und Übereinstimmung von lokalem und Remote-Commit. Bei fehlender Linux-Umgebung führe die entsprechende Python-CLI auf Windows aus und dokumentiere die Einschränkung.

## 6. Vollständigkeitscheck der sechs Reparaturen

| Problem | Umsetzung | Abnahmenachweis |
|---|---|---|
| Stilles 60k-Limit | Phase 2 vollständiger Text und Chunking | Beleg nach Zeichen 60.000 erreicht Modelljob und Ausgabe |
| Alle Felder gleichzeitig | Phase 2 Batches | Alle Felder genau einem Batch pro Chunk/Sample zugeordnet |
| Zu lockeres Grounding | Phase 1 prüfen, Phase 4 integrieren | Lange Werte, Zahlenformate, unbelegte Werte und K=1 getestet |
| Scans/kaputte PDFs | Phase 2 Null-Fallback | Vollständige Ausgabe ohne unbestätigten PDF-Upload |
| Sequenzielle Requests | Phase 3 konfigurierbarer Pool | Worker 1/2 identisch mit Mocks; begrenzte 429-Retries |
| Prompt-Regeln | Phase 2 Typen/Beschreibungen/Checkboxen | Gerenderte Prompts und Pflichtfelder geprüft |

- Prüfe zusätzlich Pfad-/Env-Regressionen, Parsefehler, fehlende Confidence, Gruppen-Split und gold-freie Inferenz.
- Dokumentiere vorhandene Grenzen: strikte Spans kosten Recall; Feldzuordnung kann trotz Grounding falsch sein; unvollständige Samples lösen dokumentweite Abstention aus; Confidence ist unkalibriert.
- Schließe mit einer einzigen Fertigmeldung ab, die tatsächlich implementierte Funktionen, Tests, Ergebnisse, Abgabe-Commit und verbleibende Einschränkungen nennt.
