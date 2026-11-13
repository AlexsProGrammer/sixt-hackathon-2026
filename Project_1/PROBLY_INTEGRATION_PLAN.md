# PROBLY_INTEGRATION_PLAN — belastbare UQ und messbare Entscheidung

- Stand: 13.11.2026; Analyseziel: `S:/Test/Project_1`.
- Arbeitsweise: Eine Person mit einem Coding-Agent arbeitet die Phasen von oben nach unten ab. Keine Rollen A/B/C, keine zwischenzeitlichen Team-Merges.
- Dieser Folgeplan konkretisiert und ersetzt die UQ-, Messungs- und Freigabeschritte des bisherigen `IMPLEMENTATION.md`. Bereits funktionierendes Chunking, Batching, Transport und Evaluation weiterverwenden.
- Status: Plan, keine implementierte Änderung. Checkboxen bedeuten noch auszuführende Arbeiten. Bestehende Fähigkeiten sind unten als Befund gekennzeichnet.
- Ziel: Den besten **gemessenen** Ansatz im verfügbaren Budget finden; keine optimale Performance oder kalibrierte Zuverlässigkeit ohne Daten versprechen.

## 1. Project Context & Architecture

### Ziel und Befund

- Integriere probly nachvollziehbar in `Text → K Samples → Evidenzprüfung → Antwortverteilung → UQ → Entscheidung → offizieller Scorer`.
- Behalte zwei klar bezeichnete Betriebsarten: aktive UQ-Extraktion und All-Abstain als wirtschaftlichen Fallback. Ein Fallback ist keine erfolgreiche Evaluation der Extraktion.
- Verändere niemals `1_download.sh`, `2_prepare.py`, `3_baseline.py`, `4_extract_example.py`, `5_score.py` oder `test_score.py`. Eigene Adapter und Tests sind erlaubt.

| Geprüfter Bereich | Aktueller Befund | Konsequenz |
|---|---|---|
| `submission/decision.json`, `run_hidden.sh` | `abstain_all=true` setzt auch bei `--mode llm` den Null-Ausgabepfad durch | Im finalen Pfad erfolgen weder Extraktion noch probly-Auswertung |
| `uncertainty/uq_probly.py` | Echte probly-Aufrufe für kategorische Verteilung und Entropie vorhanden | Bibliothek ist integriert, aber Entropie ist bislang nur Diagnose |
| Aktuelle Confidence | Minimum aus Mehrheitsanteil und kleinster Modell-Confidence der Gewinner | Kein kalibriertes P(korrekter Feldwert); Entropie beeinflusst Entscheidung nicht |
| K=1 | Ein Cluster, Entropie 0, Agreement 1 | Keine Aussage über Antwortvariation; keine nachgewiesene Sicherheit |
| Sample-Fehler | Ein unvollständiges Sample verwirft das Dokument | Unnötiger Coverage-Verlust für unabhängig vollständige Felder |
| Parsing/Merge | Fehlendes Feld wird wie gültiges null behandelt; Merge prüft nicht selbst gegen vollständige geplante Job-IDs | Technische Lücken können als inhaltliche Übereinstimmung erscheinen |
| Grounding | Belegt Vorkommen, nicht Feldzugehörigkeit; bool/JSON abstinieren | Systematische Feldverwechslungen bleiben möglich; bestimmte Typen fehlen |
| Bisherige Messung | Sechs Dokumente, nur eines vollständig inferiert, vier durch 429 beeinträchtigt, ein Scan | Funktionale Teilmessung, keine Grundlage für Methodenwahl oder verlässlichen Threshold |
| Resume/Decision | Unzureichende Bindung an Input, Modus und komplette Entscheidung; Resume-Zählung nicht eindeutig kumulativ | Risiko gemischter Ausgaben und unpassender Kalibrierung |
| Dokumentzugriff | PDF-Textzugriff verwendet erste Seite | Prüfen, ob der jeweilige Datensatz absichtlich einzelne Seiten referenziert; sonst relevante Folgeseiten ergänzen |

### Paper als Referenz und Grenzen

- Quelle: beigefügtes `probly- Uncertainty-Aware Mach….pdf`, insbesondere §§3, 4.1, 4.3, 5.1 und Einschränkungen; PDF hat zehn bereitgestellte Seiten, referenzierte Anhänge liegen darin nicht vor.
- §§3/5.1: Trenne Erzeugung, Repräsentation, Quantifizierung, Entscheidung und Evaluation. Mehrere LLM-Antworten ermöglichen Entropie über Antwortcluster.
- §5.1: Semantic Entropy nutzt NLI-Cluster; Spectral Entropy einen Embedding-Kernel. Aktuelle exakte String-Cluster sind **keine vollständige Implementierung dieser Verfahren**.
- §4.1: Die Einzelmodell-Baseline ist in der untersuchten Bildklassifikation stark; Ensemble-Konstruktion ist relevant. Daraus folgt die Notwendigkeit unserer Baseline-Vergleiche, keine Garantie für K=3.
- §4.3: Kalibrierungsansätze schneiden im untersuchten Active-Learning-Setting gut ab. Übertragbarkeit auf Vertragsextraktion muss gemessen werden.
- Keine Übertragung der Rangfolge von ImageNet/OpenML auf CUAD/ExtractBench ohne eigene Experimente; keine Behauptung epistemischer/aleatorischer Zerlegung aus unserer Häufigkeitsentropie.
- Versionsgrenze: In lokal installiertem `probly==0.9.1` fehlt `probly.uncertainty.llm`. Keine Imports aus Paper-Abbildungen ungeprüft übernehmen, kein stilles Upgrade auf Entwicklungsstände.
- Verfügbare Basis: `create_categorical_distribution(probs)` und `entropy(distribution)`; lokal existiert außerdem `probly.transformation.calibration.platt_scaling(base)`, das einen **BinaryLogitClassifier-Predictor** benötigt. Eine Liste von Scores ist kein gültiger Ersatz für diesen Vertrag.

### Stack und Abhängigkeiten

- Python 3.12 für eigene Pipeline und probly; Python 3.11-Hinweis der Originalskripte nicht als Kompatibilitätszusage für probly übernehmen.
- Basisinstallation: `python -m pip install -r requirements.txt`; `probly==0.9.1` beibehalten.
- Verwende vorhandene Standardbibliothek, NumPy, pypdf und probly. Keine neuen Pakete für den Pflichtpfad erforderlich.
- Für optionale Platt-Kalibrierung zuerst Backend und Predictor-Vertrag im installierten probly prüfen; falls sklearn-Backend gewählt, `python -m pip install scikit-learn`, getestete konkrete Version anschließend in `requirements.txt` festhalten. Keine ungetesteten Versionsnummern erfinden.
- `python` in allen Befehlen meint den zuvor aktivierten und verifizierten Projektinterpreter; fehlt `.venv`, isolierte Umgebung anlegen. Keine Abhängigkeit von der Umgebung eines anderen Checkouts in der Abgabe.

### Dateistruktur

```text
Project_1/
├── PROBLY_INTEGRATION_PLAN.md         # dieser Folgeplan
├── IMPLEMENTATION.md                 # Verweis auf Folgeplan und Status
├── 4_extract.py                      # Integration, Resume, Artefaktprüfung
├── requirements.txt
├── pipeline/
│   ├── requests.py                   # vollständiger Jobplan, Sampling-Konfiguration
│   ├── transport.py                  # Parsing-Vertrag, Budget und Cache
│   └── merge.py                      # Feldstatus, Evidenz und Vollständigkeit
├── uncertainty/
│   ├── contracts.py                  # NEU: versionierte interne Verträge
│   ├── grounding.py                  # Evidenz je Typ und Feld
│   ├── policy.py                     # harte Ausschlussgründe
│   ├── uq_probly.py                  # Verteilung, Entropie und Features
│   ├── decision.py                   # NEU: getrennte UQ-Score-/Entscheidungsregel
│   └── calibration.py                # NEU: optionale Predictor-/Artefaktadapter
├── evaluation/
│   ├── prepare.py                    # gruppengetrennte Partitionen
│   ├── validate.py
│   ├── select_threshold.py           # unveränderter Scorer, strengere Freigabe
│   ├── preflight.py                  # NEU: Daten-/Request-/Konfigurationsprüfung
│   ├── ablation.py                   # NEU: identische Samples vergleichen
│   ├── calibrate.py                  # NEU: Trainingslabels und Kalibrierung
│   └── report.py                     # NEU: Messung, Herkunft und Ausfälle
├── tests/
│   ├── test_uq_contract.py           # NEU
│   ├── test_uq_decision.py           # NEU
│   ├── test_uq_calibration.py        # NEU
│   ├── test_run_provenance.py        # NEU
│   └── test_measurement_gate.py      # NEU; bestehende Tests weiterverwenden
├── submission/
│   ├── decision.json                 # erst nach Auswahl aktualisieren
│   ├── calibration.json             # nur bei tatsächlich trainierter Kalibrierung
│   └── slides.pdf
├── run_hidden.sh
├── SUBMISSION.md
├── docs/probly_integration_uncertainty_quantification_guide.md
└── results/                          # lokale ignorierte Daten und Messartefakte
```

### Sicherheits- und Architekturregeln

- Secrets nur über bestehende Konfiguration laden; fehlende Variablen nur namentlich melden (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). URL-Schema prüfen, Werte niemals in Logs schreiben.
- API-Nutzung nur im freigegebenen Budget; 429 ist Infrastrukturfehler und kein UQ-Signal. Kein paralleler zweiter Lauf gegen dieselbe Teamquote.
- Keine Goldwerte in Prompts, Cache-Keys oder Inferenzinputs. Gold nur im lokalen Evaluationsprozess verwenden.
- Kein `test_public` in diesem Folgeplan verwenden. Partitionen ausschließlich aus Dev bilden und ihre IDs einfrieren.
- Keine automatischen Commits, Pushes oder Änderungen an geschützten Originalen.
- Datenschutz: Externe Verarbeitung nur über den für den Hackathon freigegebenen Dienst; neue OCR-, NLI- oder Embedding-Dienste nicht still ergänzen. Sensible Dokumenttexte, Rohantworten und Caches lokal und gitignored halten; Lösch-/Aufbewahrungsregeln dokumentieren. Keine unbegründete pauschale DSGVO-Rechtsbehauptung.

### Verbindliche Schnittstellen — intern Version 2

- `pipeline.requests.build_jobs(...) -> list[Job]`: Jeder Job enthält stabile `job_id`, `sample_idx`, `chunk_id`, `batch_id`, `field_names`, Textoffsets, Promptversion und Sampling-Konfiguration. Vollständigen erwarteten Jobplan mitführen.
- `pipeline.merge.merge_sample(job_results, schema, sample_idx, *, planned_jobs) -> SampleV2`: `SampleV2` enthält `contract_version=2`, ganzzahlige eindeutige `sample_idx`, globale `complete`-Diagnose und eine Feldmap.
- Feldbeobachtung: `value`, `model_confidence`, `status`, `complete`, `evidence`. Statuswerte: `present`, `absent`, `invalid`, `missing`, `error`, `unsupported`, `unreadable`. Evidenz enthält Seite/Chunk, Quelle und Originalpassage/Offsets; keine Goldreferenz.
- `absent` heißt explizite, gültige Modellantwort nach vollständiger Bearbeitung aller relevanten Chunks. Fehlendes Feld oder gescheiterter Request heißt niemals `absent`.
- `complete` pro Feld erfordert alle geplanten relevanten Jobs. Globale Unvollständigkeit eines anderen Batches darf ein vollständig bearbeitetes Feld nicht verwerfen.
- `uncertainty.uq_probly.aggregate_samples(samples, schema, text, *, expected_k) -> AggregationV2`: Prüfe Version/IDs/Anzahl; gib `candidates` und `diagnostics` zurück. Je Kandidat: `value`, `eligible`, `reason`, `features`; noch keine behauptete kalibrierte Confidence.
- Features: `k_expected`, `k_valid`, `agreement`, `entropy_nats`, `entropy_norm`, `n_clusters`, `null_share`, `grounded`, Modellscore-Zusammenfassung und Evidenzstatus. Fehler nicht als Null-Cluster zählen.
- `uncertainty.decision.make_prediction(aggregation, schema, *, method, calibration) -> dict`: Gib genau alle Schema-Felder mit `value` und endlicher numerischer `confidence` in [0,1] zurück. Harte Ausschlussgründe ergeben null/0.0. Threshold-Filterung separat und konsistent mit offizieller Auswertung halten.
- `uncertainty.calibration.predict_correctness(features, artifact) -> float`: Nur bei kompatiblem trainiertem Artefakt zulässig; fehlendes/inkompatibles Artefakt führt zu klarer Fehlermeldung, nicht zu stiller Ersatz-Confidence.
- Prediction-JSONL bleibt unverändert: `doc_id`, `fields`. Neue Features/Status gehören in Diagnose-Dateien. Ein temporärer V1-Adapter ist zulässig, muss V1-Unvollständigkeit konservativ erhalten und darf keine Evidenz erfinden.

## 2. Execution Phases (The Executable State Machine)

### Phase 1: Bestand, Versionen und reproduzierbarer Ausgangspunkt

- [ ] **1.1:** Prüfe in Projektwurzel Git-Status, `IMPLEMENTATION.md`, `docs/` und vorhandene Resultate mit PowerShell/Git; markiere frühere Reports als historische Evidenz. Prüfe sechs Originaldateien gegen verfügbare Baseline-Hashes; bei fehlender Baseline keine Unverändertheit behaupten.
- [ ] **1.2:** Prüfe in `requirements.txt` Python-/probly-Version und lokale APIs mit `importlib.metadata`/`inspect`; protokolliere fehlendes LLM-Modul sowie optionales Kalibrierungsbackend in `results/uq_environment.json` ohne Secrets.
- [ ] **1.3:** Implementiere in `evaluation/preflight.py` mit argparse/json/pathlib einen Offline-Check für Pfade, Eingabe ohne Gold, Schema, sichere Konfigurationsprüfung und Anzahl geplanter Requests. CLI: `--input PATH --samples K --dry-run`; dry-run benötigt keine API-Verbindung und gibt keine Dokumenttexte aus.
- [ ] **Verification:** Führe `python test_score.py`, `python -m unittest discover -s tests` und `python -m evaluation.preflight --help` aus. Erwartung: Tests bestehen; Skips mit Gründen erfassen. Kein API-Aufruf.

### Phase 2: Verlässliche Samples und Evidenz statt künstlicher Sicherheit

- [ ] **2.1:** Definiere in `uncertainty/contracts.py` mit typing/dataclasses den V2-Vertrag. Passe `pipeline/requests.py`, `pipeline/transport.py` und `pipeline/merge.py` gemeinsam an; prüfe fehlende/zusätzliche/duplizierte Job-IDs und erwartete Feldschlüssel. Fehlende Confidence ist kein erfundener Score; bool, NaN und Infinity zurückweisen.
- [ ] **2.2:** Erhalte in `pipeline/merge.py` Status und Evidenz aller Kandidaten. Konflikt, fehlende Antwort und explizites null getrennt behandeln. Ein Feld mit fehlendem relevantem Chunk bleibt unvollständig, auch wenn andere Chunks denselben Wert liefern.
- [ ] **2.3:** Trenne in `uncertainty/policy.py` und `grounding.py` mit Standardbibliothek harte Ausschlüsse von Modell-Confidence. Erzwinge Evidenz für nicht-null-Werte; ergänze Feldkontext aus Beschreibung/Label als Zusatzprüfung, ohne Vorkommen mit korrekter Zuordnung gleichzusetzen. Bewahre bisherige Komma-, Whitespace- und Span-Normalisierung als Regressionstest.
- [ ] **2.4:** Prüfe in `4_extract.py` mit pypdf die Seitenreferenz-Semantik. Lese alle für den Datensatzdatensatz vorgesehenen Seiten und erhalte Seitenoffsets; erweitere explizite Einzelseiten-Aufgaben nicht auf fremde Seiten. Scan ohne lesbaren Text bleibt dokumentiertes `unreadable`.
- [ ] **2.5:** Erweitere bool/JSON in `grounding.py` nur mit belegbaren typbezogenen Regeln: bool nur mit expliziter Label-/Wert-Evidenz, JSON nur mit validierter Struktur und belegbaren Blattwerten. Ohne ausreichende Evidenz `unsupported` und null; keine automatische Ableitung „nicht gefunden = false“. OCR/Vision ist ein getrennt zu messender Ausbau, keine Voraussetzung dieses UQ-Pfades.
- [ ] **Verification:** Führe `python -m unittest discover -s tests -p test_uq_contract.py` sowie `python -m unittest discover -s tests -p test_extraction.py` aus. Prüfe fehlende Feldschlüssel, fehlenden Job, Nullantwort, widersprüchliche Chunks, Nachfolgeseite, Scan, bool/JSON sowie erfolgreiche Felder neben fehlgeschlagenem fremdem Batch.

### Phase 3: probly mit entscheidungsrelevanter UQ integrieren

- [ ] **3.1:** Implementiere in `uq_probly.py` Verteilungen nur aus gültigen inhaltlichen Antworten mit NumPy und probly. Bei K=3 verlange zunächst alle drei vollständigen Beobachtungen pro Feld; keine Annahme zufällig fehlender Samples. K=1 separat kennzeichnen, keine UQ-Zuverlässigkeit aus H=0 ableiten.
- [ ] **3.2:** Bewahre exakte normalisierte Cluster als reproduzierbare Baseline. Verwende keine paarweise Token-F1-Relation als transitive Clusterdefinition. Wähle deterministisch einen originalen evidenzbelegten Kandidaten, keine frei generierte Zusammenfassung.
- [ ] **3.3:** Berechne in `uq_probly.py` `H = entropy(create_categorical_distribution(p))` in nats; für K>1 zusätzlich `H/log(K)`. Null ist nur bei gültigem `absent` ein Cluster. Dokumentiere K, Sampling-Temperaturen und n gültige Beobachtungen.
- [ ] **3.4:** Implementiere in `decision.py` getrennte feste Vergleichsmethoden: `k1_grounded` (bestehende Modellscore-Baseline), `k3_agreement` (Gewinneranteil), `k3_entropy` (Score `1-H/log(3)`). Letzterer nutzt probly direkt in der Entscheidung, ist aber ausdrücklich unkalibriert. Nullmehrheit, Gleichstand oder fehlende Evidenz erzwingen null/0.0 für alle Varianten.
- [ ] **3.5:** Verwende in `requests.py` einen vorab festgelegten Sampling-Plan. Für Häufigkeitsvergleiche vorzugsweise identische stochastische Konfiguration je K=3-Sample; sample_idx trennt Cache-Einträge. Den bisherigen Mix aus Temperatur 0 und 0.7 nur als ausdrücklich benannte Variante behalten. K1-Vergleich mit identischer Temperatur aus Sample 0 auswerten; gesonderte deterministische K1-Baseline bei Budget zusätzlich erfassen.
- [ ] **3.6:** Verbinde in `4_extract.py` Aggregation und `make_prediction`; schreibe `probly_version`, `uq_method`, `uq_called`, effektives K und Ausschlussgründe in Manifest/Diagnose. Mock-Test muss zeigen: gleiche Gewinneranteile, verschiedene Verteilungen, verschiedene Entropie-Scores; nicht nur prüfen, ob import funktioniert.
- [ ] **Verification:** Führe `python -m unittest discover -s tests -p test_uq_decision.py` und `python -m unittest discover -s tests -p test_integration.py` aus. Erwartung: Entropie für [1,0] = 0 und für [0.5,0.5] = log(2); Entropievariante beeinflusst Scores; K1, null, fehlende Samples und Reihenfolge korrekt; aktiver Mock-Pfad ruft probly auf, All-Abstain nicht.

### Phase 4: Messbarkeit, Cache und sichere Artefaktbindung

- [ ] **4.1:** Ergänze in `4_extract.py`/`transport.py` mit hashlib/json den Run-Fingerprint aus Input-/Schema-Hashes, Modus, Modell, Endpoint-Identität ohne Credentials, Prompt, Sampling, Chunking, Policy/UQ-Version und Kalibrierungs-/Decision-Hash. API-Key niemals hashen oder loggen. Cache-Schlüssel müssen alle antwortrelevanten Parameter enthalten.
- [ ] **4.2:** Lehne in `4_extract.py` Resume bei inkompatibler Herkunft, doppelten IDs oder inkonsistenten Diagnosezeilen ab. Zähle neue und kumulative Dokumente/Requests separat; erhalte Run-/Segment-IDs und Fehlerhistorie. Keine Vermischung von Offline, All-Abstain, K1 und K3.
- [ ] **4.3:** Ergänze in `evaluation/preflight.py` exakte geplante Jobzahl: Summe über Dokumente aus Chunks × Batches × K; separat mögliche Retries und Cache-Treffer. Beispiel: 41 Felder bei Batchgröße 10 benötigen fünf Requests pro Chunk/Sample, K3 also 15. Zehn Dokumente sind deshalb nicht zehn Requests.
- [ ] **4.4:** Ergänze in `transport.py` kontrollierten Quotenstopp und begrenzte Gesamtwartezeit; keine automatische unbegrenzte Hintergrund-Wiederholung. Unvollständige Runs separat speichern und für Kalibrierung sperren. Timeout/Retry-Budget vor Start ausweisen.
- [ ] **4.5:** Erweitere `load_decision` in `4_extract.py`: endlicher Threshold in [0,1], vollständiger Parametersatz, unterstützte Version, Modell-/Prompt-/UQ-/Kalibrierungshash passend; keine stillen Defaults bei eingefrorener aktiver Entscheidung. All-Abstain weiterhin explizit möglich.
- [ ] **Verification:** Führe `python -m unittest discover -s tests -p test_run_provenance.py` aus. Erwartung: identischer Resume akzeptiert; geänderter Modus/Input/UQ/Kalibrator abgelehnt; simuliertes 429 nachvollziehbar; kumulative Counts stimmen; keine Secrets in Logs.

### Phase 5: Datenpartitionen und vollständiger Funktionslauf

- [ ] **5.1:** Erweiterung in `evaluation/prepare.py` mit Standardbibliothek: gruppengetrennte `dev_fit`, `dev_select`, `dev_audit` innerhalb Dev. Bisheriges dev_cal ist bereits angesehen; nicht als neue unberührte Auditmenge ausgeben. Unberührte Gruppen identifizieren, sonst unabhängige Prüfung als fehlend dokumentieren. Seeds, IDs und Hashes einfrieren; Verteilung nach Quelle/Lesbarkeit dokumentieren.
- [ ] **5.2:** Erstelle mit `evaluation/preflight.py` ein repräsentatives Zehner-Smoke-Subset (nach Möglichkeit fünf CUAD, vier textlesbare ExtractBench, ein Scan) samt passendem Gold. Neue Dateipfade pro Pipelineversion; keine Vermischung mit alten Outputs. Falls Requestbudget nicht reicht, Umfang vor Beginn reduzieren und den Zehnerlauf ausdrücklich offen lassen.
- [ ] **5.3:** Führe `4_extract.py` explizit im aktiven LLM-Modus mit K3 und ohne die All-Abstain-Decision aus; konkrete CLI-Flags zuerst mit `python 4_extract.py --help` prüfen. Bei fehlender Konfiguration abbrechen und nur Variablennamen nennen. Setze nötiges URL-Schema korrekt, ohne Credentials auszugeben.
- [ ] **5.4:** Prüfe über `evaluation/validate.py` exakt identische doc_ids, jedes Schema-Feld und explizite endliche numerische Confidence. Prüfe zusätzlich Diagnose: K3 für jedes lesbare Dokument/Feld wie vorgesehen, keine technischen Fehler; Scan darf planmäßig unreadable sein. Zehn geschriebene Zeilen allein bedeuten keinen vollständigen K3-Erfolg.
- [ ] **Verification:** Führe `python -m evaluation.validate --input results/uq_smoke10_input.jsonl --pred results/uq_smoke10_predictions.jsonl` aus. Erwartung: VALID plus dokumentierter K3-/Fehlercheck aus Diagnose. Bei 429/Parsing-Ausfall Phase nicht als gemessen abschließen; Offline-Tests und Bericht weiterführen, keine Threshold-Freigabe.

### Phase 6: Ablation, optionale Kalibrierung und Threshold

- [ ] **6.1:** Implementiere in `evaluation/ablation.py` eine Offline-Auswertung derselben gespeicherten Samples für K1, K3-Agreement und K3-Entropie. Verwende `load_scorer()` aus `select_threshold.py`; ändere den Scorer nicht. Reporte Unterschiede bei Precision, Coverage, Hallucination Rate, akzeptiert/falsch, Net Saving und Request-/Zeitkosten. UQ-Nutzen als Differenz zur Baseline berichten.
- [ ] **6.2:** Verwende `evaluation/calibrate.py` nur bei ausreichenden vollständigen Fit-Daten mit richtigen und falschen Kandidaten. Erzeuge Labels „gewählter Feldkandidat korrekt“ aus dem offiziellen `collect()`/`values_match()` mit demselben Feldnormalizer; keine eigene abgeschwächte Korrektheitsdefinition. Null-/harte Ausschlussfälle nicht als leicht korrektes Training aufblasen.
- [ ] **6.3:** Implementiere optional in `uncertainty/calibration.py` einen getesteten BinaryLogitClassifier-Predictor für den festgelegten skalaren UQ-Score; transformiere begrenzte Scores mit dokumentiertem epsilon in Logits. Wende probly `platt_scaling(base)` und `calibrate(y_calib, ...)` gemäß tatsächlich installiertem Backend an. Speichere Parameter als JSON mit Feature-/Versionsschema. Vergleiche gegen unkalibrierten Score; keine komplexe Mehrfeature-Kalibrierung oder isotone Regression als Pflicht bei wenig Daten.
- [ ] **6.4:** Trenne in `evaluation/calibrate.py` Methodenentwicklung und Fit durch gruppenbasierte innere Splits innerhalb dev_fit. Nutze dev_select nur für vorab festgelegte Methoden-/Threshold-Auswahl; dev_audit genau einmal für die danach eingefrorene Entscheidung. Kein Nachjustieren nach Audit; Änderungen benötigen neue unabhängige Prüfung.
- [ ] **6.5:** Ergänze in `evaluation/report.py` Brier Score und Reliability-Bins für kalibrierte Kandidaten auf unabhängigen Daten; zeige Gruppengröße/Fehleranzahl. ECE bei kleinen Mengen nicht überinterpretieren. Ein monotones Platt-Mapping verbessert nicht automatisch das Ranking oder den maximal erreichbaren Net Saving.
- [ ] **6.6:** Verstärke in `select_threshold.py` das Freigabegate: Bei technischen Ausfällen, fehlenden Provenienzangaben, unvollständigem K oder inkompatiblem Artefakt keine Produktionsentscheidung überschreiben. Erzeuge stattdessen `measurement_incomplete` im Report. Separat End-to-End-Metriken einschließlich Ausfällen und diagnostische Metriken vollständig inferierter Fälle ausweisen; letztere nicht als Gesamtqualität ausgeben.
- [ ] **6.7:** Wähle τ auf dev_select mit unverändertem offiziellen Kostenscorer bei Review=1, Fehler=100; Sensitivität bei 20 und 500 nur zusätzlich. Deklariere gewählte Methode, Sample-/Score-Konfiguration, Kalibratorhash und Partitionen. All-Abstain bleibt separate Vergleichsaktion; τ=1 allein garantiert bei Confidence=1 keine Abstention.
- [ ] **6.8:** Bewerte eingefrorene Entscheidung auf dev_audit mit `evaluation/report.py`: Precision, offizielle Coverage, Hallucination Rate (Nenner: Gold-null-Felder), Net Saving, Fallzahlen, API-/Parsing-Fehler, Cachehits und Laufzeit. Ergänze dokumentgruppenweise Bootstrap-Intervalle mit festem Seed; bei wenigen Gruppen als instabil kennzeichnen. Keine pauschale Regel „300 Felder beweisen 99 %“ wegen Abhängigkeiten und Threshold-Auswahl.
- [ ] **Verification:** Führe `python -m unittest discover -s tests -p test_uq_calibration.py`, `python -m unittest discover -s tests -p test_measurement_gate.py` und `python test_score.py` aus. Erwartung: Label-Parität, keine Split-Leakage, identische Scores nach Artefakt-Roundtrip, unvollständiger Run blockiert Freigabe. Reale Metriken in `results/uq_report.json` nur aus tatsächlich durchgeführten Läufen übernehmen.

### Phase 7: Freigabe, Abgabe und ehrliche Darstellung

- [ ] **7.1:** Aktualisiere `submission/decision.json` nur anhand der eingefrorenen Auswahl und Abschlussbewertung. Setze `abstain_all=false` nicht allein zur Demonstration von probly. Fehlt eine belastbare positive Messung, behalte den Fallback und zeige die aktive UQ-Pipeline separat als Forschungs-/Demoergebnis. Wenn aktive UQ trotz negativer Kosten gewünscht ist, muss diese Priorität ausdrücklich entschieden und dokumentiert werden.
- [ ] **7.2:** Prüfe in `run_hidden.sh` Interpreter, Dependencyinstallation, relative Pfade und Decision-Bindung. Prüfe aktiven UQ-Pfad mit lokalem API-Mock und All-Abstain-Pfad separat auf goldfreier Eingabe. Führe Linux-Smoke-Test in verfügbarer Linux-Umgebung durch; andernfalls explizit offen lassen.
- [ ] **7.3:** Aktualisiere `SUBMISSION.md`, `IMPLEMENTATION.md`, UQ-Guide und `submission/slides.pdf`: Datenfluss, reale probly-APIs, exakt versus semantisch, K, Scores versus Wahrscheinlichkeiten, Baselinevergleich, Threshold, Fehler-/Kostenmessung und Grenzen. Entferne Team-Platzhalter, alte Rollenübergaben und überholte Aussagen über komplette Evaluation.
- [ ] **7.4:** Dokumentiere fehlende reale K3-/Linux-Prüfungen, nicht unterstützte Typen, Scan-Abstention und mögliche systematische Fehler durch gemeinsame Modellantworten. Stimmen drei Antworten überein, kann der Wert trotzdem falsch sein.
- [ ] **Verification:** Führe `python -m unittest discover -s tests`, `python test_score.py` und beide Startskript-Mock-Szenarien aus. Prüfe geschützte Originalhashes, ignorierte Daten/Secrets sowie Entscheidungshash. Ausgabe in aktivem Szenario: probly tatsächlich aufgerufen, Schema vollständig, eindeutige Provenienz. Dokumentiere Resultate; keinen Commit/Push ohne passende Freigabe.

### Optional nach dem Pflichtpfad: Semantic/Spectral Entropy

- [ ] **O.1:** Prüfe in einem separaten Experiment die Verfügbarkeit einer freigegebenen probly-Version mit LLM-Methoden. Bleibe andernfalls bei ehrlicher Bezeichnung „Entropie über exakt normalisierte Antwortcluster“; reimplementierte NLI-Cluster sind kein Aufruf einer fehlenden probly-LLM-API.
- [ ] **O.2:** Ergänze optional `uncertainty/semantic.py` mit lokalem NLI-Modell oder Embeddings nur nach Budget-/Abhängigkeitsprüfung. Vergleiche auf dev_fit; erhalte Originalkandidaten und exakte Cluster als Sicherheitsprüfung. Semantische Ähnlichkeit darf inkompatible Zahlen, Daten, Negationen oder Scorer-Werte nicht zu einem akzeptierten Wert verschmelzen.
- [ ] **Verification:** Lege `tests/test_semantic_uq.py` mit Paraphrase, anderer Partei, Negation und abweichenden Zahlen an; führe `python -m unittest discover -s tests -p test_semantic_uq.py` aus. Nutze den Ansatz nur bei anschließend separat gemessenem Nutzen; berichte zusätzliche Laufzeit und Speicherverbrauch.

## 3. Global Testing Strategy

- [ ] Teste den gesamten aktiven Pfad vom goldfreien Dokument bis zum offiziellen Scorer, nicht nur isolierte probly-Aufrufe.
- [ ] Prüfe K1=keine Variationsinformation; K3 einig, 2:1, dreifach verschieden, Nullmehrheit, Fehler und duplizierte Samples.
- [ ] Prüfe lange Texte mit entscheidender Evidenz nach Zeichen 60.000, Chunkgrenzen, überlappende Spans, mehrere relevante Seiten und explicit Einzelseiten-Datensätze.
- [ ] Prüfe Grounding-Fallen: richtiger Wert am falschen Label, Kommas, gekürzte Spans, Datum mit Satzzeichen, Zahlenformat, Checkbox und JSON.
- [ ] Prüfe reproduzierbare Run-/Cache-/Resume-Bindung, 429, Timeout, Parsingfehler, fehlende Confidence und fehlerhafte Decision-Dateien.
- [ ] Prüfe keine Gold-Leakage und keine gruppenübergreifenden Seiten desselben Dokuments in Fit/Select/Audit.
- [ ] Prüfe offizielle Scorer-Parität und zeige alle Nenner; Scorer-Regeln niemals zur Verbesserung eigener Zahlen verändern.
- [ ] Unterscheide „implementiert“, „lokal getestet“, „real mit API gemessen“ und „auf unabhängigen Daten bestätigt“ in jedem Abschlussbericht.
- [ ] Nach jeder Phase meldet der Agent: Ergebnis, Teststatus, reale Messungen, Blocker und nächsten Schritt. Keine Wartepflicht auf andere Personen; bei fehlender Quote weiterhin unabhängige Offline-Arbeiten erledigen.
