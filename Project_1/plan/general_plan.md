## 1. Project Context & Architecture

- **Goal:** Erweitert den vorhandenen Dokument-Extractor um zuverlässige Ausgabevalidierung, Grounding und konservative Abstention. Liefert innerhalb von 150 Minuten eine reproduzierbare Pipeline mit gemessenen Ergebnissen, deklariertem Threshold und vollständiger Abgabe.
- **Verbindlicher Einstiegspunkt:** Bearbeitet `Project_1/4_extract.py`; die im Gespräch genannte `4_extract.py` existiert aktuell nicht. Behaltet den vorhandenen Dateinamen und CLI-Aufruf bei.
- **Projektwurzel:** `Project_1/`. Alle nachfolgenden Dateipfade und Python-Befehle sind relativ zu dieser Wurzel; Git-Befehle funktionieren dort ebenfalls.
- **Ausgangslage:** C1/C2 sind bereits implementiert. Die URL-Schema-Prüfung ist lokal geändert. Laut letztem Lauf liegen zwei CUAD-Ergebnisse vor; HTTP 429 blockiert weitere Dokumente. Behandelt diese Angaben als Ausgangspunkt und prüft den Stand vor Beginn.
- **Dokumentgrundlage:** `docs/00_start_here_review_and_fixes.md`, `docs/hackathon_master_plan_team_kickoff.md`, `docs/engineering_roadmap_refactoring_llm_cache.md`, `docs/data_reference_baselines_scoring_guide.md`, `docs/probly_integration_uncertainty_quantification_guide.md`.
- **Priorisierung:** Laufender Ein-Pass-Extractor → geprüfte Abstention → Dev-Evaluation → Abgabe. Aktiviert Multi-Sampling, Vision, Chunking und Kalibrierungsmodelle erst nach dem gemeinsamen Basistest und ausreichender API-Quote; diese Erweiterungen sind außerhalb des verbindlichen 150-Minuten-Umfangs.
- **Tech Stack & Dependencies:**
  - Verwendet Python 3.12 und die bestehende virtuelle Umgebung.
  - Erstellt eine fehlende Windows-Umgebung mit `py -3.12 -m venv .venv`.
  - Installiert vorhandene Abhängigkeiten mit `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
  - Verwendet `pypdf==7.0.0` für PDF-Text und das bestehende `jsonschema==4.26.0` beim Scoring.
  - Nutzt `argparse`, `json`, `pathlib`, `urllib`, `hashlib`, `tempfile`, `math`, `unittest` und `importlib` aus der Standardbibliothek.
  - Verwendet das bereits installierte `probly==0.9.1` nur bei einer ausdrücklich gemeinsam beschlossenen späteren Erweiterung; die Basis-Pipeline benötigt es nicht.
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
│   └── transport.py                     # A: HTTP, Retry, Cache
├── uncertainty/
│   ├── __init__.py                      # B: leeres Paket
│   ├── grounding.py                    # B: Evidenzprüfung
│   └── policy.py                       # B: Feldvalidierung + Abstention
├── evaluation/
│   ├── __init__.py                      # C: leeres Paket
│   ├── prepare.py                      # C: gruppierter Split, gold-freie Eingaben
│   ├── validate.py                     # C: Ausgabeprüfung
│   └── select_threshold.py             # C: Scorer-Anbindung + Threshold-Auswahl
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
  - Person C besitzt `evaluation/`, `tests/test_c_integration.py`, `run_hidden.sh`, `submission/`, `SUBMISSION.md`, `EDA.md` und nötige gezielte Ignore-Regeln; Branch `feat/eval-submission`.
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

## 2. Execution Phases (The Executable State Machine)

#### Phase 1: Gemeinsamer Ausgangspunkt und feste Verträge — Minute 0–10

- [x] **Step 1.1 — Alle:** Prüft mit Git den aktuellen Stand von `4_extract.py`, `run_hidden.sh` und den eigenen Dateien. A übernimmt vorhandene lokale Extractor-Änderungen bewusst in den gemeinsamen Ausgangsstand; C hält den Start-Commit fest. Prüft vorhandene Änderungen vor einem Pull oder Branchwechsel.
- [x] **Step 1.2 — Alle:** Erstellt vom vereinbarten Start-Commit die Branches mit `git switch -c feat/extraction`, `git switch -c feat/abstention` beziehungsweise `git switch -c feat/eval-submission`. Verwendet je Person ausschließlich den eigenen Befehl im eigenen Klon.
- [ ] **Step 1.3 — A/B/C:** Legt jeweils die leeren `__init__.py` in eurem Paket an. Nutzt Python-Pakete ohne zusätzliche Frameworks; importiert Module über `pipeline`, `uncertainty` und `evaluation` aus dem bestehenden Einstiegspunkt.
- [ ] **Step 1.4 — A und B:** Fixiert für `uncertainty/policy.py` den Vertrag `apply_policy(answer, schema, text) -> dict`: Eingabe ist das rohe Modellobjekt ohne `doc_id`; Rückgabe ist die vollständige `fields`-Map. B liest oder schreibt keine Dateien und führt keine API-Aufrufe aus.
- [ ] **Step 1.5 — B:** Fixiert für `uncertainty/grounding.py` den Vertrag `is_grounded(value, text, field_schema) -> bool`. Liefert bei fehlendem Text und nicht sicher prüfbaren Typen `False`.
- [ ] **Step 1.6 — A und C:** Erhaltet in `4_extract.py` `--data`, `--out`, `--limit`, `--mode`. Ergänzt `--on-error fail|abstain` mit Standard `fail`; nutzt den finalen Abgabemodus explizit. C schreibt `submission/decision.json` mit numerischem `threshold`, `method`, ausgewertetem Umfang und Run-ID. Der Scorer erhält den deklarierten Threshold; der Extractor gibt Scores aus.
- [ ] **Verification — Alle:** Führt `.venv\Scripts\python.exe -m unittest discover -s . -p test_score.py` und `.venv\Scripts\python.exe 4_extract.py --help` aus. Erwartet erfolgreiche Tests, Exit 0 und die bestehenden CLI-Optionen. Erst danach beginnen alle gleichzeitig Phase 2.

#### Phase 2: Drei parallele Arbeitspakete — Minute 10–55

- [ ] **Step 2.A1 — A:** Extrahiert in `pipeline/transport.py` die HTTP-Logik mit `urllib`. Akzeptiert Konfiguration und Request-Payload explizit. Begrenzt jeden Lauf auf höchstens einen Retry pro fehlgeschlagenem Request und ein Wartebudget von 60 Sekunden. Berücksichtigt `Retry-After` einschließlich HTTP-Datum. Bei längerer Warteangabe oder erneutem 429 beendet weitere Requests für diesen Lauf; erfasst den Zustand für den Aufrufer.
- [ ] **Step 2.A2 — A:** Implementiert in `pipeline/transport.py` einen SHA-256-Cache über kanonisches JSON aus Endpoint, Modell und vollständigem Request-Payload. Schließt den API-Key aus. Speichert nur erfolgreiche, gültige Modellobjekte mittels `tempfile` und atomarem `os.replace`. Verwendet lokal `cache/`; cached weder HTTP-Fehler noch Parsefehler. Eine veränderte Policy darf dieselbe rohe Modellantwort erneut auswerten.
- [ ] **Step 2.A3 — A:** Verbessert in `4_extract.py` das JSON-Parsing mit `json`: akzeptiert ein JSON-Objekt und klar abgegrenzte Markdown-Codefences; verwirft Listen, ungültiges JSON und leere Antworten als explizite Parsefehler. Erhaltet echte Feld-Nulls als gültige Modellantwort.
- [ ] **Step 2.A4 — A:** Behaltet in `4_extract.py` den bestehenden Textzugriff mit `pypdf`. Prüft CUAD vor dem PDF-Pfadzugriff, lest alle aufgeführten Seiten in Reihenfolge und normalisiert Pfade zentral. Verhindert Pfade außerhalb von `DATA` über `Path.resolve` und eine Prüfung des übergeordneten Verzeichnisses.
- [ ] **Step 2.A5 — A:** Gebt in `4_extract.py` für unlesbare Dokumente und überschrittenes Textbudget vollständige Null-Vorhersagen aus; protokolliert `unreadable` beziehungsweise `over_budget`. Entfernt stilles Abschneiden aus dem finalen LLM-Pfad. Übermittelt Scans in der Basisversion nicht als rohe PDF-Datei an einen unbestätigten Vision-Endpunkt.
- [ ] **Step 2.A6 — A:** Erhaltet in `4_extract.py` Resume nur für explizit fortgesetzte gleiche Runs. Verwendet neue Outputdateien für jede geänderte Pipeline. Prüft bestehende JSONL auf doppelte IDs und unvollständige Zeilen; meldet kaputte Dateien klar. Im Modus `fail` lasst technische Fehler ungeschrieben und beendet mit Exit 1; im Modus `abstain` schreibt für betroffene Dokumente alle Felder als null und erfasst Fehler separat. Nach ausgelöstem 429-Stopp verursacht der restliche Lauf keine weiteren Requests.
- [ ] **Step 2.A7 — A:** Erstellt in `tests/test_a_extraction.py` mit `unittest` und Mocks Prüfungen für fehlende Konfiguration, JSON-Listen, Parsefehler, 429-Stopp, Cache-Hit, Payload-Änderung, Resume und Windows-Pfade. Patched Wartezeiten müssen Tests ohne echte Pausen ermöglichen.
- [ ] **Step 2.B1 — B:** Implementiert in `uncertainty/grounding.py` mit `re` eine konservative Stringprüfung mit Casefold und normalisiertem Whitespace; erhaltet Kommas, Punkte und Währungssymbole. Fordert Token-Grenzen, damit `12` nicht in `312` matcht. Lasst lange Texte dieselbe Evidenzprüfung durchlaufen.
- [ ] **Step 2.B2 — B:** Prüft in `uncertainty/grounding.py` CUAD-Spans als normalisierte zusammenhängende Textstellen. Dokumentiert, dass dies konservativer als die Token-F1-Bewertung ist und Recall kosten kann. Prüft kein bloßes Vorkommen beliebiger Einzelwörter über das gesamte Dokument. Stellt JSON, native Bool-Werte und Checkbox-Felder zunächst zurück, solange keine vollständige prüfbare Evidenzlogik existiert.
- [ ] **Step 2.B3 — B:** Implementiert in `uncertainty/policy.py` mit `math.isfinite` eine vollständige Feldmap ausschließlich aus dem Schema. Akzeptiert Confidence nur als endliche Zahl im Bereich [0,1], schließt Bool aus, und behandelt fehlende/ungültige Scores mit Abstention. Übernehmt valide Scores ohne Aufrunden oder künstliche Erhöhung durch Grounding. Ignoriert zusätzliche Modellfelder. Setzt ungrounded, fehlende und null-Werte auf null/0.
- [ ] **Step 2.B4 — B:** Erstellt in `tests/test_b_policy.py` mit `unittest` Fälle für NaN, Infinity, Bool als Confidence, fehlende Felder, zusätzliche Felder, keine Evidenz, lange gültige Spans, falsche Zahlentrennzeichen und Teiltreffer in Zahlen. Verwendet kleine selbst erstellte Texte und lokale Dev-Beispiele.
- [ ] **Step 2.C1 — C:** Implementiert in `evaluation/prepare.py` mit `json`, `re` und `hashlib` eine deterministische Gruppenteilung analog zur Gruppierungsregel in `2_prepare.py`. Bietet `--data`, `--out-dir` und `--seed` an. Schreibt `dev_train_gold.jsonl`, `dev_cal_gold.jsonl` und jeweils eine `_input.jsonl` ohne `gold`. Prüft disjunkte Gruppen und eindeutige IDs; speichert den Seed und die Mengen im lokalen Manifest.
- [ ] **Step 2.C2 — C:** Implementiert in `evaluation/validate.py` mit `argparse`, `json` und `math` die Optionen `--input` und `--pred`. Prüft exakte Dokument-ID-Mengen, eindeutige Zeilen, exakte Schema-Feldmengen und explizite endliche numerische Confidence in [0,1]. Verlangt bei null Confidence 0. Meldet fehlende Dokumente als Fehler und gebt bei Erfolg `VALID` sowie Exit 0 aus.
- [ ] **Step 2.C3 — C:** Implementiert in `evaluation/select_threshold.py` mit `importlib` die Wiederverwendung von `5_score.py`. Bietet `--gold`, `--pred`, `--out` an. Prüft zuerst vollständige passende IDs; evaluiert beobachtete Scores und eine ausdrückliche All-Abstain-Option. Wählt empirisch maximalen Net Saving bei E=100, bei Gleichstand die konservativere Variante. Schreibt Threshold, Counts, Methode und Unsicherheit bei kleinem Umfang nach `submission/decision.json`. All-Abstain muss durch null-Ausgaben umgesetzt werden; definiert dafür mit A `--abstain-all`.
- [ ] **Step 2.C4 — C:** Erstellt in `SUBMISSION.md` das Gerüst für Problem, Ansatz, Baselines, Resultate, Modellwahl, Laufzeit, Fehlerkosten, How-to-run und Einschränkungen. Prüft in `.gitignore`, dass Cache, Rohdaten, `.env`, Prediction-JSONL und `results/*.log` ausgeschlossen sind; erlaubt gezielt kleine Score-Zusammenfassungen.
- [ ] **Verification — A:** Führt `.venv\Scripts\python.exe -m unittest discover -s tests -p test_a_extraction.py` aus; erwartet Exit 0 ohne echten API-Aufruf.
- [ ] **Verification — B:** Führt `.venv\Scripts\python.exe -m unittest discover -s tests -p test_b_policy.py` aus; erwartet Exit 0 und bestandene Grenzfälle.
- [ ] **Verification — C:** Führt `.venv\Scripts\python.exe -m evaluation.prepare --data data/unified/dev.jsonl --out-dir results/split --seed 42` aus; erwartet disjunkte Dokumentgruppen, vier JSONL-Dateien und ein Manifest. Die Phase endet gemeinsam erst nach diesen drei erfolgreichen Prüfungen.

#### Phase 3: Integration der drei Branches — Minute 55–75

- [ ] **Step 3.1 — B/C:** B committet und pusht ausschließlich seine Dateien. C übernimmt den getesteten Branch mit Git in `main` des Team-Repos. A holt diesen Stand in `feat/extraction` und löst eigene Konflikte dort.
- [ ] **Step 3.2 — A:** Verbindet in `4_extract.py` Transport, Parser und `uncertainty.policy.apply_policy`. Gibt `doc_id` zusammen mit der Policy-Feldmap aus. Implementiert `--abstain-all` vor Konfigurationsprüfung und HTTP-Zugriff, sodass der gewählte vollständige Abstention-Modus auch ohne API lauffähig ist.
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
