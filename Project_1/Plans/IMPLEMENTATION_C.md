# IMPLEMENTATION C — Evaluation, Integration und Abgabe

## Dein Auftrag

- Du bist der Coding-Agent für Person C. Bearbeite `evaluation/`, `tests/test_c_evaluation.py`, `tests/test_c_integration.py`, `tests/fixtures/contracts/`, `run_hidden.sh`, `submission/`, `SUBMISSION.md` sowie gezielte notwendige Anpassungen an requirements.txt, .gitignore und EDA.md.
- Beginne sofort mit synthetischen Daten und vorab bekannten Ergebnissen. Split, Ausgabeprüfung und Scorer-Adapter funktionieren ohne A/B-Imports.
- Verwende die originalen Funktionen aus 5_score.py. Ergänze nur passende Datenmengen, ID-/Feldvollständigkeit und Confidence-Prüfung. Prüfe erwartete Counts in den Fixtures von Hand.
- Koordiniere getestete Merges nach main, Threshold, Bericht, Slides und Präsentationsprobe. Nutze die bestehende Nutzerautorisierung für Git-Aktionen.
- Erst die gemeinsame CLI-Prüfung und echte Kennzahlen benötigen A/B. Fülle bis dahin Bericht- und Foliengerüst und prüfe die Auswertung lokal.
- Minute 0–10 Fixtures; 10–30 Split/Validator; 30–55 Scorer-Adapter und Berichtsgerüst; 55–75 Integration; 75–110 Kennzahlen/Freeze; 110–140 Abgabe/Probe; 140–150 Remote-Kontrolle.
- Dein Branch ist `feat/eval-submission`. Alle Pfade gelten relativ zu Project_1.
- Dieser Rollenplan enthält den gemeinsamen Kontext und alle rollenübergreifenden Schnittstellen. Die beschriebenen Schritte sind Implementierungsaufträge; prüfe ihren tatsächlichen Status im Checkout.

## Start und Arbeitsweise

- [ ] Prüfe `git status --short --branch`, Dateibaum und vorhandene Änderungen. Arbeite in einem eigenen Klon oder Worktree.
- [ ] Beginne auf deinem Branch vom gemeinsam bestätigten Start-Commit.
- [ ] Prüfe Python 3.12, die lokale Umgebung und Abhängigkeiten. Windows nutzt `.venv\Scripts\python.exe`, Linux `.venv/bin/python`.
- [ ] Führe `.venv\Scripts\python.exe test_score.py` aus. Erwarte erfolgreiche Originaltests.
- [ ] Bestätige die öffentlichen Schnittstellen mit dem Team. Beginne danach die unabhängigen eigenen Schritte.
- Bearbeite in den gemeinsamen Abschlussphasen die deiner Rolle zugewiesenen Aufgaben. Benenne fremde Aufgaben als Übergaben und setze eigene unabhängige Arbeit fort.
- Melde nach jedem Arbeitspaket Dateien, Tests, benötigte Abstimmung, nächsten Git-Schritt und nächste unabhängige Aufgabe. Kennzeichne tatsächlich ausgeführte Aktionen und empfohlene Aktionen eindeutig.
## Deine konkreten Implementierungsschritte

- [ ] **Step 2.C0 — C, vor 2.C1 ausführen:** Erstellt die synthetischen Dateien in `tests/fixtures/contracts/` gemäß dem Schnittstellenvertrag. Erstellt `tests/test_c_evaluation.py` mit `unittest` für Split, Validator und Threshold-Auswahl. Importiert ausschließlich C-Module und den offiziellen Scorer. Prüft vorab berechnete Counts und die All-Abstain-Option. C besitzt diese Testdatei und die Fixtures zusätzlich zu den bisher genannten Dateien.
- [ ] **Step 2.C1 — C:** Implementiert in `evaluation/prepare.py` mit `json`, `re` und `hashlib` eine deterministische Gruppenteilung analog zur Gruppierungsregel in `2_prepare.py`. Bietet `--data`, `--out-dir` und `--seed` an. Schreibt `dev_train_gold.jsonl`, `dev_cal_gold.jsonl` und jeweils eine `_input.jsonl` ohne `gold`. Prüft disjunkte Gruppen und eindeutige IDs; speichert den Seed und die Mengen im lokalen Manifest.
- [ ] **Step 2.C2 — C:** Implementiert in `evaluation/validate.py` mit `argparse`, `json` und `math` die Optionen `--input` und `--pred`. Prüft exakte Dokument-ID-Mengen, eindeutige Zeilen, exakte Schema-Feldmengen und explizite endliche numerische Confidence in [0,1]. Verlangt bei null Confidence 0. Meldet fehlende Dokumente als Fehler und gebt bei Erfolg `VALID` sowie Exit 0 aus.
- [ ] **Step 2.C3 — C:** Implementiert in `evaluation/select_threshold.py` mit `importlib` die Wiederverwendung von `5_score.py`. Bietet `--gold`, `--pred`, `--out` an. Prüft zuerst vollständige passende IDs. Implementiert ausschließlich einen dünnen Aufruf der vorhandenen `score(read_jsonl(gold_path), load_preds(pred_path))`-Funktion aus `5_score.py`. Übernehmt für die Dev-Auswahl `business.threshold`, das bereits den besten Net Saving einschließlich All-Abstain berechnet. Implementiert keine eigene Bewertungsformel oder Threshold-Suche. Bei `threshold=None` wählt ausdrücklich All-Abstain; speichert dafür einen numerischen deklarierten Threshold von 1.0 und `abstain_all=true`. Schreibt Threshold, Counts, Methode und Unsicherheit bei kleinem Umfang nach `submission/decision.json`. All-Abstain muss durch null-Ausgaben umgesetzt werden; definiert dafür mit A `--abstain-all`.
- [ ] **Step 2.C4 — C:** Erstellt in `SUBMISSION.md` das Gerüst für Problem, Ansatz, Baselines, Resultate, Modellwahl, Laufzeit, Fehlerkosten, How-to-run und Einschränkungen. Prüft in `.gitignore`, dass Cache, Rohdaten, `.env`, Prediction-JSONL und `results/*.log` ausgeschlossen sind; erlaubt gezielt kleine Score-Zusammenfassungen.
- [ ] **Step 2.C5 — C:** Ergänzt `requirements.txt` um die von B lokal geprüfte probly-Version. Erweitert die Auswertung in `evaluation/` und `SUBMISSION.md` um K=1 versus K=3 auf identischen Dokumenten, Requestanzahl und Laufzeit. Wenn K=3 nur mit Fixtures getestet wurde, kennzeichnet genau diesen Status. C bestimmt den Threshold; B besitzt Aggregation und Grounding. Ein zusätzliches Kalibrierungsmodell bleibt optional und würde von C ausschließlich auf `dev_train` gefittet.

### Verifikation deines Pakets

- [ ] **Verification — C:** Führt `.venv\Scripts\python.exe -m evaluation.prepare --data data/unified/dev.jsonl --out-dir results/split --seed 42` aus; erwartet disjunkte Dokumentgruppen, vier JSONL-Dateien und ein Manifest. Die Phase endet gemeinsam erst nach diesen drei erfolgreichen Prüfungen.
- [ ] **Verification — C, unabhängig von A/B:** Führt `.venv\Scripts\python.exe -m unittest discover -s tests -p test_c_evaluation.py` und `.venv\Scripts\python.exe -m evaluation.validate --input tests/fixtures/contracts/input.jsonl --pred tests/fixtures/contracts/predictions.jsonl` aus. Erwartet Exit 0 und `VALID`. Führt anschließend `.venv\Scripts\python.exe -m evaluation.select_threshold --gold tests/fixtures/contracts/gold.jsonl --pred tests/fixtures/contracts/predictions.jsonl --out results/fixture_decision.json` aus und prüft das erwartete Ergebnis gegen den Test. Damit ist Cs Paket bereits vor der A/B-Integration prüfbar.

## Gemeinsames Projektwissen und Funktionsverträge

## 1. Project Context & Architecture

- **Goal:** Erweitert den vorhandenen Dokument-Extractor um zuverlässige Ausgabevalidierung, Grounding und konservative Abstention. Liefert innerhalb von 150 Minuten eine reproduzierbare Pipeline mit gemessenen Ergebnissen, deklariertem Threshold und vollständiger Abgabe.
- **Verbindlicher Einstiegspunkt nach Upload-Prüfung:** Bearbeitet die vorhandene Teamkopie `Project_1/4_extract.py`. Im hochgeladenen Ordner ruft `run_hidden.sh` bereits diese Datei auf. Bewahrt die Originale `1_download.sh`, `2_prepare.py`, `3_baseline.py`, `4_extract_example.py`, `5_score.py` und `test_score.py` unverändert. Dies folgt eurer Arbeitsvorgabe; die gelesene README enthält kein allgemeines Änderungsverbot für nummerierte Dateien.
- **Projektwurzel:** `Project_1/`. Alle nachfolgenden Dateipfade und Python-Befehle sind relativ zu dieser Wurzel; Git-Befehle funktionieren dort ebenfalls.
- **Ausgangslage:** C1/C2 sind bereits implementiert. Die URL-Schema-Prüfung ist lokal geändert. Laut letztem Lauf liegen zwei CUAD-Ergebnisse vor; HTTP 429 blockiert weitere Dokumente. Behandelt diese Angaben als Ausgangspunkt und prüft den Stand vor Beginn.
- **Dokumentgrundlage:** `docs/00_start_here_review_and_fixes.md`, `docs/hackathon_master_plan_team_kickoff.md`, `docs/engineering_roadmap_refactoring_llm_cache.md`, `docs/data_reference_baselines_scoring_guide.md`, `docs/probly_integration_uncertainty_quantification_guide.md`.
- **Priorisierung nach Planprüfung:** Implementiert die sechs Reparaturen einschließlich Chunking, Batching und konfigurierbarer Parallelität sowie die probly-Aggregation in Phase 2. Prüft diese lokal mit Mocks. Startet reale Multi-Sample-Läufe nur im verfügbaren Requestbudget. Standard sind ein Worker und ein Sample; der verbindliche Scanfallback ist Abstention. 150 Minuten bleiben ein Zielbudget; meldet nicht bestandene Abnahmen ausdrücklich als offen.
- **Tech Stack & Dependencies:**
  - **Prüfgrundlage:** Verglichen wurden README, `run_hidden.sh`, `4_extract.py`, `5_score.py` und Teamhinweise aus `C:/Users/abdul/Downloads/Project_1/`. Dort fehlen `data/` und `.venv`; führt Laufprüfungen im eingerichteten Team-Checkout durch oder richtet diese Voraussetzungen zuerst ein. Die sechs Reparaturen sind in der hochgeladenen Kopie weiterhin offen; C1/C2 sind vorhanden. Implementierungsstatus und Messergebnisse sind jeweils neu zu prüfen.
  - **Vorhandene Bewertung verwenden:** `5_score.py` enthält bereits `collect`, `at_threshold`, `risk_coverage`, `best_saving`, `schema_validity` und die CLI für Threshold, Fehlerkosten und JSON-Berichte. `test_score.py` prüft diesen Scorer. C führt diese Dateien aus und verwendet ihre Funktionen unverändert.
  - **Zusätzliche Validierung begrenzen:** `evaluation/validate.py` prüft ausschließlich vollständige/eindeutige Dokument-IDs, Schema-Feldmengen und gültige Confidence-Werte. Diese Ausgabeprüfung ergänzt die vorhandene Schema-Validierung, welche weder Vollständigkeit noch Confidence absichert. C implementiert keinen zweiten Schema-Validator und keinen zweiten Scorer.
  - **Notwendiger eigener Code:** A implementiert Extraktion, Requests, Cache und die sechs Reparaturen in der Teamkopie und `pipeline/`. B implementiert Grounding, Policy und echte probly-Aggregation in `uncertainty/`. C implementiert nur Split/Gold-Subset, Ausgabeprüfung und einen kleinen Adapter zur vorhandenen Score-Ausgabe. C nutzt den gewonnenen Zeitraum für End-to-End-Prüfung und Abgabe.
  - **Umfang begrenzen:** Vision/OCR, trainierte Kalibrierung, Credal Sets und Conformal Risk Control sind optionale Erweiterungen. Zur probly-Integration gehören verbindlich Sample-Verteilungen und Entropie; mit K=1 sind diese Diagnosen wenig aussagekräftig. Eine getestete K=3-Verarbeitung mit lokalen Fixtures und ein soweit möglich realer Vergleich gehören zur Abnahme.
  - Verwendet Python 3.12 und die bestehende virtuelle Umgebung.
  - Erstellt eine fehlende Windows-Umgebung mit `py -3.12 -m venv .venv`.
  - Installiert vorhandene Abhängigkeiten mit `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
  - Verwendet `pypdf==7.0.0` für PDF-Text und das bestehende `jsonschema==4.26.0` beim Scoring.
  - Nutzt `argparse`, `json`, `pathlib`, `urllib`, `hashlib`, `tempfile`, `math`, `unittest` und `importlib` aus der Standardbibliothek.
  - B integriert `probly==0.9.1` verbindlich in Phase 2; C ergänzt die Abhängigkeit in `requirements.txt`. Installiert bei Bedarf mit `.venv\Scripts\python.exe -m pip install probly==0.9.1`. Prüft Factory- und Entropie-Signaturen anhand der installierten Version.
  - Ersetzt in Linux-Befehlen `.venv\Scripts\python.exe` durch `.venv/bin/python`; installiert dort mit `python3 -m venv .venv` und `.venv/bin/python -m pip install -r requirements.txt`.
- **File Structure:**

```text
Project_1/
├── IMPLEMENTATION.md                    # dieser Plan; gemeinsam vor Beginn lesen
├── 4_extract.py                 # A: bestehender Einstiegspunkt + Integration
├── 5_score.py                           # offizieller Scorer, als Referenz verwenden
├── test_score.py                        # vorhandene Scorer-Tests
├── requirements.txt                     # bestehende Abhängigkeiten
├── run_hidden.sh                        # C: finaler Aufruf
├── SUBMISSION.md                        # C: Ansatz, Messungen, Ausführung
├── EDA.md                               # C: vorhandene Analyse prüfen
├── pipeline/
│   ├── __init__.py                      # A: leeres Paket
│   ├── requests.py                     # A: Chunks, Feld-Batches, Sample-Jobs
│   ├── merge.py                        # A: Chunks zu vollständigem Sample zusammenführen
│   └── transport.py                     # A: HTTP, Retry, Cache
├── uncertainty/
│   ├── __init__.py                      # B: leeres Paket
│   ├── grounding.py                    # B: Evidenzprüfung
│   ├── uq_probly.py                    # B: Sample-Aggregation, Entropie, Agreement
│   └── policy.py                       # B: Feldvalidierung + Abstention
├── evaluation/
│   ├── __init__.py                      # C: leeres Paket
│   ├── prepare.py                      # C: gruppierter Split, gold-freie Eingaben
│   ├── validate.py                     # C: Ausgabeprüfung
│   └── select_threshold.py             # C: dünner Adapter für vorhandenen Scorer
├── tests/
│   ├── test_a_extraction.py            # A: Transport/Parser/Resume
│   ├── test_b_policy.py                # B: Grounding/Abstention
│   └── test_c_integration.py           # C: integrierter CLI-Test mit Mock-Endpoint
├── submission/
│   ├── decision.json                  # C: gewählter Threshold + Verfahren
│   └── slides.pdf                     # C: maximal fünf Folien
├── results/                           # lokal: Eingaben, Vorhersagen, Laufprotokolle
└── cache/                             # lokal: erfolgreiche API-Antworten
```

- **Attention Points — Eigentum und Zusammenarbeit:**
  - Person A besitzt ausschließlich `4_extract.py`, `pipeline/` und `tests/test_a_extraction.py`; Branch `feat/extraction`.
  - Person B besitzt ausschließlich `uncertainty/` und `tests/test_b_policy.py`; Branch `feat/abstention`.
  - Person C besitzt `evaluation/`, `tests/test_c_integration.py`, `run_hidden.sh`, `submission/`, `SUBMISSION.md`, `EDA.md`, `requirements.txt` und nötige gezielte Ignore-Regeln; Branch `feat/eval-submission`. Prüft Konfliktmarker nur im tatsächlich verwendeten Checkout; der frühere Befund bezog sich auf den S:-Checkout.
  - Übergebt Änderungswünsche an Dateien anderer Personen an deren Eigentümer. A bindet Bs Funktionen ein. C integriert die Branches in `main` des Team-Repos.
  - Arbeitet auf getrennten lokalen Klonen. Bei mehreren Agenten auf einem Rechner verwendet getrennte Worktrees; wechselt niemals gleichzeitig Branches in demselben Arbeitsverzeichnis.
  - Verwendet ausschließlich das eigene Team-Repo. Lasst jede Person gezielt ihre Dateien stagen; prüft vor jedem Commit `git diff --cached --stat` und den Inhalt des Diffs.
  - C integriert erst B, dann A, dann C. Jeder Branch muss vor seiner Übergabe den aktuellen `main`-Stand übernehmen und seine Prüfungen bestehen.
  - A führt sämtliche echten API-Läufe zentral aus. B und C verwenden lokale Fixtures oder den Mock-Endpoint. Diese Regel bündelt die aktuell knappe Teamquote.
- **Attention Points — Daten und Konfiguration:**
  - Verwendet `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`; ladet `.env`, ohne bestehende Prozessvariablen zu überschreiben. Verlangt HTTPS für den Veranstalter-Endpunkt; erlaubt HTTP für lokale Mock-Tests.
  - Gebt Secrets und rohe API-Fehlerantworten nicht aus. Protokolliert Statuscode, Dokument-ID, Fehlerklasse, Versuchsanzahl und Laufzeit.
  - Iteriert ausschließlich über `rec['schema']['properties']`; Inferenz muss ohne `gold` funktionieren.
  - Behaltet `5_score.py` unverändert. Ladet seine Normalisierer und Bewertungsfunktionen für Evaluation über `importlib`; bestimmt deren tatsächliche Signaturen vor Verwendung.
  - Entwickelt auf `dev_train`, wählt den Threshold auf `dev_cal`, wertet `test_public` erst nach Freeze aus. Gruppiert zusammengehörige Dokumentseiten im Split.
  - Berichtet erfolglose Dokumente und den angefragten Umfang zusätzlich zu Kennzahlen erfolgreicher Teilmengen.
  - Erzwingt Abstention durch `value=null, confidence=0.0`; allein Confidence 0 würde bei Threshold 0 einen nicht-null Wert weiter akzeptieren.
  - Interpretiert Modell-Confidence als unkalibrierten Score. Berichtet eine empirische Threshold-Auswahl. Leitet aus der Rule of Three und abhängig ausgewählten Feldern keine pauschale 99-%-Garantie ab.
  - Berichtet Fehlerkosten 20/100/500 bei demselben Threshold; positive Ersparnis bei 500 ist keine Voraussetzung für die Abgabe.
- **DSGVO:**
  - Nutzt ausschließlich die vom Veranstalter erlaubten öffentlichen/Mock-Daten und den vorgesehenen API-Endpunkt.
  - Speichert Cache, Eingaben und detaillierte Vorhersagen lokal und gitignoriert; begrenzt den Zugriff auf das Team und entfernt diese lokalen Artefakte nach Ende des vorgesehenen Nutzungszwecks.
  - Vermeidet personenbezogene Inhalte in Logs und Screenshots; dokumentiert den externen API-Datenfluss in `SUBMISSION.md`.
  - Fügt keine Telemetrie oder extern geladenen Schriften hinzu; erstellt Folien mit lokalen Schriftarten. Eine pauschale rechtliche Bewertung internationaler Datenübermittlung ist kein Bestandteil dieses technischen Plans.

- **Audit der sechs ursprünglichen Probleme (Codeprüfung bei dieser Revision):**

| Problem | Aktueller Code | Bisheriger Plan | Verbindliche Reparatur / Eigentümer |
|---|---|---|---|
| 1. 60k-Abschneiden | Weiterhin `[:MAX_CHARS]` in mehreren Pfaden | Nur Abstention bei Überlänge | A, 2.A8: vollständiger Text, überlappende Chunks, Zusammenführung |
| 2. Alle Felder gleichzeitig | `describe()` erhält das ganze Schema | Fehlte | A, 2.A8: stabile Batches mit maximal 10 Feldern |
| 3. Grounding | Lange Werte/komplexe Typen erhalten Freipass; Confidence wird halbiert | Enthalten | B, 2.B1–3: Evidenzprüfung und null/0 |
| 4. Scans/kaputte PDFs | Raw-PDF-Base64-Fallback vorhanden | Enthalten | A, 2.A5: Textprüfung, sauberer null-Fallback ohne Request |
| 5. Sequenzielle HTTP-Aufrufe | Sequenzielle Schleife, keine Poolsteuerung | Retry enthalten; Pool fehlte | A, 2.A9: konfigurierbarer Pool, gemeinsamer Rate-Limit-Stopp |
| 6. Prompt-Regeln | Generische Kopierregeln; Beschreibungen auf 300 Zeichen gekürzt | Unvollständig | A, 2.A10: Typ/Normalizer/vollständige Beschreibung und Checkbox-Regeln |

- **Zusätzliche C1–C7:** C1/C2 existieren im Starter; ihre Regressionstests bleiben erforderlich. C3 wird durch passende Gold-Mengen gelöst. C4/C5/C6 sind in Phase 2 vorgesehen. C7 wird vor Poolstart durch einmaliges Laden des CUAD-Texts behoben. Eine Dokumentationsänderung ist kein Nachweis einer Code-Reparatur.
- **Verbindliche Schnittstellen für parallele Implementierung:**
  - **Paralleler Start von C:** C entwickelt Split, Validator, Threshold-Auswahl, Scorer-Anbindung und Bericht von Beginn an mit eigenen synthetischen Records und Predictions im definierten Format. Erst die integrierte CLI-Prüfung und reale Ergebnisbefüllung benötigen A/B. Die lokalen Funktionsprüfungen von C dürfen A/B-Module nicht importieren.
  - **C besitzt Vertrags-Fixtures:** C erstellt `tests/fixtures/contracts/input.jsonl`, `gold.jsonl`, `predictions.jsonl`, `diagnostics.jsonl` und `decision.json` mit ausschließlich erfundenen Daten. `input.jsonl` enthält `doc_id`, `source_dataset`, `pages`, `schema` mit `properties`; `gold.jsonl` enthält dieselben Records plus die zum Scorer passende `gold`-Map. Die anderen Dateien folgen den nachstehenden Verträgen. A/B verwenden diese Fixtures als gemeinsame Beispiele. C teilt die ersten Fixtures spätestens nach zehn Minuten; bis dahin entwickeln A/B anhand der Signaturen. C erlaubt ausschließlich diese synthetischen Fixtures gezielt in Git, auch wenn eine allgemeine JSONL-Ignore-Regel besteht.
  - **Fixtures müssen Entscheidungen prüfen:** Enthaltet korrekte, falsche und fehlende Werte, null-Felder und mindestens zwei verschiedene Scores. Erstellt zusätzlich ungültige Varianten direkt in den Tests für doppelte IDs und ungültige Confidence. Setzt erwartete Counts und Net Saving von Hand fest, um Validator und Threshold-Auswahl unabhängig von einer echten Modellantwort zu prüfen.
  - **C arbeitet ohne Wartephase:** Minute 0–10 Vertrags-Fixtures; Minute 10–30 Split und Validator; Minute 30–55 Threshold-Auswahl, Scorer-Tests und Berichtgerüst; Minute 55–75 integrierter CLI-Test nach Übergabe. Während A reale Läufe ausführt, erstellt C Baseline-Tabelle, Folien und Reproduktionsanleitung. C tauscht anschließend ausschließlich die Fixture-Dateipfade gegen echte Ergebnisdateien aus.
  - Verwendet für Übergaben ausschließlich JSON-kompatible Dictionaries und Listen. Definiert keine gemeinsam zu bearbeitende Klassen-Datei. Alle Funktionen verändern ihre Eingaben nicht. B importiert keine A-/C-Module; C importiert für Evaluation den offiziellen Scorer. A orchestriert B.
  - `FieldPrediction` enthält `value` als JSON-Wert oder null und `confidence` als endliche Zahl in [0,1]. `Fields` ist eine Map von Schema-Feldname auf `FieldPrediction`.
  - `Sample` enthält `sample_idx: int`, `complete: bool`, `fields: Fields`. A führt zunächst alle Chunks und Batches eines Samples zusammen. Fehlgeschlagene Jobs setzen `complete=false`; B behandelt ein unvollständiges Ensemble konservativ mit null/0. Mehrere Chunks zählen niemals als mehrere unabhängige Samples.
  - `pipeline.requests.build_jobs(text: str, schema: dict, *, chunk_chars: int, overlap_chars: int, batch_size: int, samples: int) -> list[dict]` gehört A. Jeder Job enthält `chunk_id`, `start`, `end`, `text`, `field_names`, `schema` mit nur diesen Properties und `sample_idx`. Offsets beziehen sich auf den vollständigen Text. Validiert `0 <= overlap_chars < chunk_chars`, positive Batchgröße und Sampleanzahl.
  - `pipeline.merge.merge_sample(job_results: list[dict], schema: dict, sample_idx: int) -> dict` gehört A. Jobresultate enthalten Job-Metadaten, `answer: Fields` und `ok: bool`. Liefert ein `Sample`. Behaltet Provenienz intern; ignoriert zusätzliche Antwortfelder. Deterministische Zusammenführung muss unabhängig von Pool-Reihenfolge sein.
  - `uncertainty.grounding.is_grounded(value: object, text: str | None, field_schema: dict) -> bool` gehört B. Prüft Evidenz im vollständigen Text. Für zusammengesetzte CUAD-Antworten prüft jedes mit ` | ` verbundene Teilstück separat.
  - `uncertainty.policy.apply_policy(answer: dict, schema: dict, text: str | None) -> Fields` gehört B. Validiert jede vorgeschlagene Feldvorhersage und liefert exakt alle Schema-Felder. Fehlendes/ungültiges/unbelegtes wird null/0. A kann damit den K=1-Pfad direkt prüfen.
  - `uncertainty.uq_probly.aggregate_samples(samples: list[dict], schema: dict, text: str | None) -> dict` gehört B. Liefert `fields: Fields` und `diagnostics: dict`. Bei K=1 entspricht `fields` exakt `apply_policy`; Agreement 1 darf den Modellscore nicht auf 1 erhöhen. Bei leerer Liste oder unvollständigem Sample liefert alle Felder null/0 und einen Diagnosegrund.
  - `diagnostics` enthält `n_samples`, `complete`, `method` und `per_field`. Pro Feld stehen `agreement`, `entropy`, `n_clusters`, `grounded` und `reason`. Diese Daten sind unkalibrierte Diagnosen und kommen in eine separate lokale Datei.
  - A schreibt finale Prediction-JSONL ausschließlich als `doc_id: str` und `fields: Fields`. A schreibt Diagnostics-JSONL als `doc_id: str`, `diagnostics: dict`; ein Manifest enthält Run-ID, Modell, Promptversion, K, Workerzahl, Chunk-/Batchkonfiguration, Cache-Hits, Requests, Fehler und Laufzeit. C liest diese Dateien, ohne Extraktionslogik umzubauen.
  - `evaluation.validate.validate_predictions(records: list[dict], predictions: list[dict]) -> list[str]` gehört C. Eine leere Fehlerliste bedeutet gültig. Die CLI übersetzt dies in `VALID`/Exit 0, sonst Exit 1. Gold wird für die Strukturprüfung nicht benötigt.
  - `evaluation.select_threshold.choose_threshold(gold_records: list[dict], predictions: list[dict], error_cost: float = 100.0) -> dict` gehört C. Verwendet intern die originale `score`-Funktion mit Predictions als Map `doc_id -> Fields` (Format von `load_preds`); wandelt die Listenparameter ausdrücklich in dieses Format um. Liefert die Entscheidungsdatei mit `threshold`, `abstain_all`, `method`, `n_docs`, `n_fields`, `accepted`, `wrong`, `hallucinated`, `net_saving_pct`. CLI ergänzt Run-ID und Pipelinekonfiguration. Verwendet konsistente Einheiten wie der offizielle Scorer und benennt Prozent versus Anteil ausdrücklich im Bericht.
  - A implementiert `--decision PATH`; lädt daraus `abstain_all` und die eingefrorene Pipelinekonfiguration. C ruft in `run_hidden.sh` diese Option auf. Threshold wird deklariert und zur Evaluation verwendet; die ausgegebenen Scores behalten ihre Bedeutung. Unbekannte Konfiguration oder widersprechende CLI-Overrides führen zu einer klaren Fehlermeldung.


## Präzisierung der gemeinsamen Übergabe

- Vertragsversion 1 gilt in allen drei Rollenplänen. Stimmt Änderungen an Parametern, Rückgaben und Dateinamen mit den betroffenen Rollen vor Integration ab.
- A schreibt zu `--out results/run.jsonl` die Begleitdateien `results/run.diagnostics.jsonl` und `results/run.manifest.json`. C liest diese Dateien. Diagnostics enthalten eine Zeile pro geschriebener Prediction.
- Manifest-Keys sind `contract_version`, `run_id`, `pipeline`, `n_requested`, `n_written`, `n_failed`, `requests`, `cache_hits`, `elapsed_seconds`. `pipeline` enthält `model`, `prompt_version`, `samples`, `temperature`, `workers`, `chunk_chars`, `overlap_chars`, `batch_size`. Zugangsdaten bleiben in der lokalen Umgebung.
- C schreibt `submission/decision.json` mit `contract_version=1`, `run_id`, `threshold`, `abstain_all`, `method`, `pipeline`, `n_docs`, `n_fields`, `accepted`, `wrong`, `hallucinated`, `net_saving_pct`. Pipelinewerte stammen aus dem bewerteten Manifest. All-Abstain verwendet Threshold 1.0 und `abstain_all=true`.
- `net_saving_pct` übernimmt den Anteil aus dem offiziellen Scorer. Für die Prozentanzeige multipliziert C mit 100.
- A lädt mit `--decision` die gespeicherten Pipelineparameter und prüft Modell/Promptversion. C ruft final `4_extract.py --data INPUT --out OUTPUT --mode llm --on-error abstain --decision submission/decision.json` auf. Unbekannte Vertragsversionen und widersprechende Overrides erzeugen klare Fehler. All-Abstain funktioniert ohne API-Aufruf.
- A ergänzt Jobs um `batch_id`. Die eindeutige Job-ID besteht aus Sample-ID, Chunk-ID und Batch-ID. Für jeden geplanten Job existiert auch bei Fehler ein Resultat mit `ok=false`; `merge_sample` erkennt so unvollständige Samples.
- A übergibt B eine Liste aus Sample-Objekten mit `sample_idx`, `complete`, `fields` sowie Schema und vollständigem Quelltext. B liefert genau `fields` und `diagnostics`. A ergänzt anschließend `doc_id` für die Prediction-Datei.
- Für K>1 verwendet Sample 0 Temperatur 0, weitere Samples die konfigurierte Temperatur (Startwert 0.7 sofern unterstützt). Bei fehlender Modellunterstützung stimmt A mit B/C eine dokumentierte Promptvariation ab. Wiederholte deterministische Antworten begründen keine hohe Korrektheitswahrscheinlichkeit.
- C erzeugt Fixtures mit allen vom offiziellen Scorer benötigten Metadaten einschließlich `tags`. Lokale C-Tests importieren ausschließlich C-Code und den Scorer; der separate Integrationstest prüft die echte A/B-Pipeline.
## Kommunikationsregeln und Teamablauf


  - Übernehmt zu Beginn die vom Benutzer genannte Rolle A, B oder C. Prüft aktuellen Branch, Arbeitsstand und nächste Aufgabe. Nennt kurz die eigenen Dateien und den nächsten Übergabepunkt. Fragt nach der Rolle, falls sie noch nicht feststeht.
  - Gebt nach jedem abgeschlossenen Arbeitspaket eine kurze Statusmeldung mit fünf Punkten aus: erledigte Aufgabe und Dateien; tatsächlich ausgeführte Tests samt Ergebnis; benötigte Abstimmung mit Person und Thema; nächster Git-Schritt mit Zielbranch; nächste unabhängig ausführbare Aufgabe.
  - Unterscheidet ausdrücklich zwischen tatsächlich ausgeführten Git-Aktionen und empfohlenen nächsten Aktionen. Meldet einen Push oder Merge nur nach erfolgreicher Toolausführung. Leitet aus diesem Kommunikationshinweis keine zusätzliche Erlaubnis zum Pushen oder Mergen ab; verwendet die bestehende Autorisierung der Sitzung.
  - Nennt bei einem nötigen Git-Schritt den tatsächlichen aktuellen Branch. Lasst eigene Änderungen vor Übernahme von `main` gezielt committen. Empfehlt im Feature-Branch `git fetch origin` und `git merge origin/main`; prüft danach die eigenen Tests. Prüft vor einem Push, ob der Branch bereits einen Upstream hat; verwendet andernfalls `git push -u origin <eigener-branch>`.
  - Fordert eine mündliche Abstimmung nur an konkreten Übergaben, bei Schnittstellenänderungen, Blockaden oder Freeze an. Erfindet keine Wartepflicht nach jedem kleinen Schritt. Setzt unabhängige Arbeit fort und benennt ausdrücklich, welcher abhängige Schritt auf welche Person wartet.
  - Schlägt eine Schnittstellenänderung vor, nennt alte und neue Parameter/Rückgaben sowie die betroffenen Aufrufer. Fordert vor ihrer Integration Abstimmung mit den betroffenen Personen an. Implementiert währenddessen unabhängig mögliche Aufgaben im eigenen Bereich.
  - Verwendet überprüfbare Fertigmeldungen: Implementierung abgeschlossen, lokal getestet, zur Integration bereit, integriert und End-to-End-getestet sind unterschiedliche Zustände. Kennzeichnet fehlende echte API- oder Linux-Tests.
  - **Nach Phase 1, alle Rollen:** Meldet „Bitte bestätigt jetzt mit A, B und C den Start-Commit und die Schnittstellen. Danach kannst du dein Paket in Phase 2 auf deinem Feature-Branch beginnen.“ Nennt bereits bestätigte Punkte und vermeidet wiederholte Rückfragen dazu.
  - **Nach einem lokalen A-Paket:** Meldet beispielsweise „Chunking ist lokal getestet. Committe und pushe diese Dateien auf `feat/extraction`. Du kannst jetzt Batching bearbeiten. Für die spätere Einbindung benötigst du Bs getestete `aggregate_samples`-Funktion.“ Passt den Text an den tatsächlich erreichten Stand an.
  - **Wenn B zur Übergabe bereit ist:** Meldet „Besprich mit A kurz Eingabe, Rückgabe und Grenzfälle der Prüffunktion. Pushe deinen getesteten Stand auf `feat/abstention` und gib C die Commit-ID zur Integration. Danach kannst du Demo-Beispiele vorbereiten.“ Gebt eine kurze kopierbare Übergabenachricht mit Dateien, Signaturen, Testbefehl und offenen Grenzen aus.
  - **Wenn C B integriert hat:** Meldet „Informiere A, dass Bs Stand auf `main` liegt, und nenne den Commit. A soll seine Arbeit committen, `origin/main` in `feat/extraction` mergen und B einbinden. Du kannst parallel Evaluation und Folien fortsetzen.“ Falls der Merge noch aussteht, formuliert dies als nächsten Schritt statt als erledigte Aktion.
  - **Wenn A integriert hat:** Meldet „Pushe den getesteten A-Stand und gib C die Commit-ID für den gemeinsamen CLI-Test. Besprecht mit B die UQ-Diagnosen. Die nächste Freigabe ist der End-to-End-Test durch C.“ Gebt Teststatus und verbleibende Fehler konkret an.
  - **Nach C-Evaluation mit Fixtures:** Meldet „Deine Auswertung ist mit Beispieldaten getestet. Du kannst Bericht und Slides vorbereiten. Für echte Kennzahlen benötigst du von A die Predictions und das Run-Manifest; eine weitere Änderung der Schnittstelle ist dafür nicht erforderlich.“
  - **Vor Freeze und Abgabe:** Fordert die gemeinsame kurze Bestätigung von Pipelineversion, Threshold, Modell, K, Kennzahlen und Grenzen an. Nennt anschließend den zuständigen Integrator C sowie den finalen Git-Schritt. Erinnert nach Fertigstellung der Slides an die gemeinsame Erklärung aller drei Beiträge und den Probelauf.
  - **Bei API-Blockade:** Meldet den beobachteten Fehler und die betroffene Aufgabe. Verweist auf A als Koordinator echter API-Läufe und nennt die nächste lokale Aufgabe für die eigene Rolle. Meldet keine vermutete Reset-Zeit als bestätigte Tatsache.

- **Gemeinsamer Arbeits- und Abstimmungsplan:**

| Zeit ab Start | Mündliche Abstimmung | A | B | C | Git und Abhängigkeit |
|---|---|---|---|---|---|
| 0–10 Min. Planung | Alle bestätigen Kopie `4_extract.py`, Schnittstellen, Rollen, Quote | Prüft Kopie und lokale Änderungen | Bestätigt Policy-/Sample-Vertrag | Teilt Fixtures und Originaldatei-Referenz | C veröffentlicht Plan + Startstand auf `main`; alle starten eigene Branches vom selben Commit |
| 10–30 Min. Code | Nur bei Schnittstellenfragen | Transport, Chunking, Batches | Grounding, Policy, probly lokal | Split, Ausgabeprüfung, unveränderten Scorer an Fixtures ausführen | Jeder pusht eigenen Branch; C arbeitet ohne A/B-Imports |
| Minute 30 Checkpoint | Alle maximal 3 Minuten: Blocker, Scope, Schnittstellen | Nennt API-Status | Nennt Modulstatus | Nennt Prüfstatus | Neue Schnittstellen gemeinsam festhalten; kein Pflichtmerge unfertiger Arbeit |
| 30–55 Min. Code | A/B klären Integrationsfragen | Merge der Chunkantworten, Prompt, Pool, Tests | Aggregation und Tests fertigstellen | Dünner Score-Adapter, Bericht-/Foliengerüst | Getestete Stände auf Feature-Branches pushen |
| 55–65 Min. erste Integration | B erklärt Input/Return und Grenzen | Holt B-Stand und bindet ein | Unterstützt Übergabe | Merged getesteten B-Branch nach `main`, pusht | A committet eigene Arbeit, führt `git fetch origin` und `git merge origin/main` im A-Branch aus |
| 65–75 Min. Systemtest | Alle 5 Minuten | Liefert integrierten Extractor | Prüft Diagnosen | Merged A und C, prüft echte CLI mit lokalem Mock | C pusht `main`; alle übernehmen ihn vor weiteren Fixes in ihren Branch |
| 75–105 Min. Evaluation | Nur relevante Fehler gemeinsam | Betreut echte Requests | Analysiert Dev-Fehler | Nutzt offiziellen Scorer, wählt Threshold auf Dev, füllt Folien | Fixes über Eigentümerbranches; C integriert getestete Fixes |
| 105–110 Min. Freeze | Alle bestätigen Variante, Threshold, Grenzen | Bestätigt Modell/Parameter | Bestätigt UQ-Verfahren | Dokumentiert Entscheidung | C pusht Freeze-Commit; alle holen denselben Stand |
| 110–130 Min. Abgabe | Direkte Rückfragen | Prüft Start in frischer Umgebung | Liefert zwei verständliche Beispiele | Erstellt Slides, How-to-run und Ergebnisbericht | C integriert gezielte Abgabefixes |
| 130–140 Min. Wissensübergabe | Jeder erklärt Beitrag; gemeinsamer 3-Minuten-Probelauf | Erklärt Dokument- und API-Pfad | Erklärt Grounding, Agreement und Entropie | Erklärt Zahlen, Kosten und Grenzen | C pusht finale Abgabe bis Minute 140 |
| 140–150 Min. Puffer | Alle bestätigen finalen Stand | Startbefehl prüfen | Beispielaussagen prüfen | GitHub-Dateien und PDF prüfen | C bestätigt finalen Remote-Commit |

- **Abstimmungsregel:** Phase 1 endet mit gemeinsam bestätigtem Vertrag. Innerhalb Phase 2 arbeitet jeder unabhängig; regelmäßige Feature-Branch-Pushes erfordern keinen Merge nach `main`. Nur konkrete Abhängigkeiten und Integrationstests benötigen die Übergabe des anderen Moduls. C kann seine Auswertung vollständig mit Fixtures prüfen.
- **Codefreigabe:** Vergleicht zum Abschluss die Hashes der sechs geschützten Originaldateien mit dem Startstand. Änderungen sind ausschließlich in `4_extract.py`, eigenen Unterordnern sowie notwendigen Konfigurations-/Abgabedateien vorgesehen. `run_hidden.sh` wird gemäß README an die finale CLI angepasst.


## Gemeinsame Integration und Abgabe

#### Phase 3: Integration der drei Branches — Minute 55–75

- [ ] **Step 3.1 — B/C:** B committet und pusht ausschließlich seine Dateien. C übernimmt den getesteten Branch mit Git in `main` des Team-Repos. A holt diesen Stand in `feat/extraction` und löst eigene Konflikte dort.
- [ ] **Step 3.2 — A:** Verbindet in `4_extract.py` vollständigen Text, Chunk-/Batch-Jobs, Transport, Parser, `merge_sample` und `uncertainty.uq_probly.aggregate_samples` in dieser Reihenfolge. Gibt `doc_id` zusammen mit `fields` aus und schreibt Diagnosen separat. Implementiert `--abstain-all` und `--decision` vor HTTP-Zugriff. C ergänzt in `tests/test_c_integration.py` einen K=3-Test über die echte CLI und den lokalen Mock-Endpoint, der den A→B→C-Datenvertrag nachweist.
- [ ] **Step 3.3 — A/C:** A übergibt nach erfolgreichem Test seinen Branch. C merged zuerst A, dann die eigenen Evaluation-Dateien und behebt Überschneidungen mit dem jeweiligen Eigentümer. Führt ab jetzt nur gezielte Fixes in den Eigentümerdateien durch.
- [ ] **Step 3.4 — C:** Erstellt in `tests/test_c_integration.py` mit `unittest`, `http.server`, `subprocess` und `tempfile` einen lokalen Endpoint-Test über die echte CLI. Prüft gold-freie Eingabe, eine erfolgreiche Extraktion, einen unbelegten Wert, kaputtes JSON, 429 mit begrenzten Requests und `--abstain-all`. Verwaltet Fixture und HTTP-Konfiguration vollständig temporär.
- [ ] **Step 3.5 — C:** Passt `run_hidden.sh` mit Bash so an, dass der Aufruf aus `Project_1` mit zwei Dateiparametern funktioniert, eine frische Ergebnisdatei verwendet und Python-Exitcodes weitergibt. Nutzt final `--mode llm --on-error abstain` oder den dokumentierten All-Abstain-Modus gemäß `submission/decision.json`. Verlangt vorhandene Outputpfade bewusst als Fehler, damit alte Ergebnisse nicht unbemerkt übernommen werden.
- [ ] **Verification:** Führt `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` und `.venv\Scripts\python.exe -m unittest discover -s . -p test_score.py` aus. Erwartet Exit 0 und Mock-geprüfte normale CLI-Ausführung einschließlich Fehlerpfaden.

#### Phase 4: Messung und feste Entscheidung — Minute 75–110

- [ ] **Step 4.1 — A:** Prüft gemeinsam mit dem Topic Owner die reale API-Quote und ihr Reset-Fenster. Führt bei verfügbarer Quote `4_extract.py` auf einer vorher festgelegten kleinen gemischten Dev-Auswahl ohne Gold aus; speichert Eingabe und Vorhersagen unter `results/final_dev_*`. Erfasst versuchte/erfolgreiche Dokumente, Fehler, Requests, Laufzeit und Modell in einem lokalen Run-Protokoll.
- [ ] **Step 4.2 — C:** Prüft mit `evaluation/validate.py` die vollständige Ausgabe. Nutzt für Teilversuche einen vorab erzeugten passenden Gold-Ausschnitt und nennt den angefragten Umfang. Verwendet die zwei bekannten Smoke-Dokumente ausschließlich zur Fehlerdiagnose, wenn sie bereits für Änderungen betrachtet wurden.
- [ ] **Step 4.3 — A/C:** Reserviert verfügbare Requests für eine vorher festgelegte Dev-Cal-Auswahl. Führt A auf `results/split/dev_cal_input.jsonl` beziehungsweise einem deterministisch gezogenen Ausschnitt aus. Friert vor dieser Auswertung Prompt und Grounding ein. Wiederholte Anpassungen nach Cal-Fehleranalyse erfordern eine neue unbenutzte Validierungsmenge oder eine klare Deklaration als explorative Evaluation.
- [ ] **Step 4.4 — C:** Ruft `evaluation/select_threshold.py` auf der passenden Cal-Menge auf und schreibt `submission/decision.json`. Dokumentiert bei unzureichender Quote den fehlenden Nachweis. Wählt bei fehlendem belastbarem positiven Ergebnis die ausführbare All-Abstain-Variante und berichtet die gemessenen Teilversuche separat.
- [ ] **Step 4.5 — C:** Führt `5_score.py` auf denselben finalen Vorhersagen mit `--threshold` aus `submission/decision.json` und jeweils `--error-cost 20`, `--error-cost 100`, `--error-cost 500` aus. Übernehmt Kennzahlen am deklarierten Threshold und absolute Counts; verwechselt den automatisch optimierten `business`-Block nicht mit dem deklarierten Ergebnis.
- [ ] **Step 4.6 — A/C:** Wertet `test_public` nach Freeze einmal aus, sofern Zeit und Quote reichen. Dokumentiert vollständige oder explizit partielle Auswertung und jeden technischen Ausfall. Nutzt diese Ergebnisse ausschließlich für den Abschlussbericht.
- [ ] **Verification:** Führt `.venv\Scripts\python.exe -m evaluation.validate --input results/final_dev_input.jsonl --pred results/final_dev_predictions.jsonl` aus; erwartet `VALID`. Führt `.venv\Scripts\python.exe -m json.tool submission/decision.json` aus; erwartet gültiges JSON mit finaler Methode und Threshold. C stellt für diese Prüfung die tatsächlich ausgewertete, festgehaltene Dev-Auswahl unter diesen Dateinamen bereit.

#### Phase 5: Freeze, Abgabe und Puffer — Minute 110–150

- [ ] **Step 5.1 — C:** Vervollständigt `SUBMISSION.md` mit exakten Startbefehlen, Abhängigkeiten, Modell, benötigten Variablennamen, Threshold, Datenumfang, Baselines und Ergebnissen bei 20/100/500. Berichtet API-Blockaden und nicht geprüfte Linux-Ausführung ausdrücklich. Prüft `EDA.md` gegen die vorhandenen Zahlen und korrigiert nur nachgewiesene Fehler.
- [ ] **Step 5.2 — B:** Liefert C anhand von Dev-Beispielen eine akzeptierte belegte Extraktion und eine nachvollziehbare Abstention. Erläutert in Stichpunkten den Fehler, den die Abstention verhindert, und die verbleibende Grenze: Textvorkommen allein beweist keine korrekte Feldzuordnung.
- [ ] **Step 5.3 — C:** Erstellt `submission/slides.pdf` mit maximal fünf Folien: Problem/Kosten, Pipeline, gemessener Vergleich, akzeptiertes/abstiniertes Beispiel, Wiederverwendbarkeit/Grenzen. Verwendet vorhandene lokale Präsentationssoftware und PDF-Export. Öffnet die PDF und prüft Seitenzahl, Lesbarkeit und Übereinstimmung mit `SUBMISSION.md`.
- [ ] **Step 5.4 — A:** Prüft den aktuellen Abgabe-Commit in einem separaten Checkout mit installierten Abhängigkeiten. Führt den echten Einstiegspunkt auf gold-freiem Input aus. C stellt einen kleinen `results/release_input.jsonl` aus der festgelegten Dev-Auswahl bereit; führt bei knapper Quote zuerst die Mock-Integration aus und dokumentiert, welche echten Tests möglich waren.
- [ ] **Step 5.5 — C:** Prüft vor Minute 140 mit Git die gestagten Dateien und Secret-Ausschlüsse, integriert alle erforderlichen Commits und pusht `main` ins Team-Repo. Prüft auf GitHub, dass `run_hidden.sh`, `SUBMISSION.md`, `EDA.md`, benötigte Python-Pakete und `submission/slides.pdf` im letzten Commit vorhanden sind.
- [ ] **Verification:** Führt unter Linux aus `Project_1` `bash run_hidden.sh results/release_input.jsonl results/release_predictions.jsonl` und anschließend `.venv/bin/python -m evaluation.validate --input results/release_input.jsonl --pred results/release_predictions.jsonl` aus. Erwartet Exit 0 und `VALID`. Falls Linux fehlt, führt die dokumentierte Python-CLI unter Windows und die Mock-Tests aus und markiert Linux als ungetestet. Führt `git status --short`, `git rev-parse HEAD` und `git ls-remote origin refs/heads/main` aus; erwartet identischen lokalen und Remote-Commit sowie keine fehlenden Abgabedateien. Nutzt Minute 140–150 für Korrekturen dieser Prüfung.

## 3. Global Testing Strategy

- [ ] **Normaler Einstiegspunkt:** Prüft die vollständige CLI mit gold-freien Records; erzeugt genau eine Ausgabe pro Eingabedokument und alle Schema-Felder.
- [ ] **Konfiguration:** Prüft CRLF in `.env`, gesetzte Umgebungsvariablen, fehlende URL-Schemata und fehlende Variablen; prüft Logs auf Secret-Freiheit.
- [ ] **Ausgabevertrag:** Prüft fehlende, doppelte und zusätzliche IDs, fehlende Felder, NaN/Infinity, Bool als Confidence, numerische Strings und falsche Modellantworttypen.
- [ ] **Abstention:** Prüft null/0 bei unbelegten Werten, fehlender Confidence, unlesbaren PDFs und übergroßen Dokumenten; prüft explizit Threshold 0.
- [ ] **Grounding:** Prüft lange CUAD-Spans, verschiedene Zahlentrennzeichen, Teilzahlen, Whitespace und Werte aus einem unpassenden Feldkontext; dokumentiert die Grenzen der reinen Textprüfung.
- [ ] **HTTP und Quote:** Simuliert 429, 500, Timeout, ungültige Response-Struktur und wiederholten Retry; begrenzt Wartezeit und Requestanzahl und prüft den Laufabbruch beziehungsweise den dokumentierten Abstention-Modus.
- [ ] **Cache und Wiederaufnahme:** Prüft gültige Cache-Hits, veränderte Payloads, atomare Schreibvorgänge, defekte Cache-Dateien und beschädigte letzte JSONL-Zeilen. Defekte lokale Artefakte müssen sichtbar behandelt werden.
- [ ] **Evaluation:** Prüft Gruppendisjunktheit, passende Gold-Mengen, identische Vergleichsdokumente und die korrekte Verwendung des deklarierten Thresholds. Führt vorhandene Scorer-Tests erfolgreich aus.
- [ ] **Business:** Prüft für E=100 die Identität `saving = accepted - 100 * (wrong + hallucinated)` bei Review-Kosten 1; vollständige Abstention muss Net Saving 0 liefern.
- [ ] **Abgabe:** Prüft den Start in einer frischen Umgebung, den finalen Remote-Commit, die PDF und die Übereinstimmung zwischen Entscheidungsdatei, tatsächlicher Pipeline und Bericht.


## Fertigmeldung deiner Rolle

- Nenne Branch und tatsächliche Commit-ID, eigene Dateien sowie übergebene Schnittstellen.
- Nenne Testbefehle, Ergebnisse und offene Einschränkungen einschließlich echter API-/Linux-Tests.
- Nenne die konkrete Übergabe an A/B/C und den nächsten Git-Schritt.
- Bestätige Rollenabschluss nach Tests, Übergabe und vereinbarter Integrationsunterstützung.
