# Project 1: Structured Extraction from Documents

**Project owners:** Sruthi Radhakrishnan, Ihsan Soydemir

**Questions before the hackathon:** email the project owners directly: sruthi.radhakrishnan@sixt.com, ihsan.soydemir@sixt.com. On the day, ask on site.

## Problem
Documents are where business data hides. Getting that content out reliably means layout detection, OCR, table reconstruction and figure handling, producing structured output (mostly JSON or form fields). Today this needs a lot of human oversight, manual effort and causes cognitive overload.

## Approach
- Extract entities and relationships from fleet or support data and load them into a Knowledge Graph (e.g. Neo4j).
- Extract values of user-defined keys from a document. Use a meta layer, with or without a knowledge graph, to collect all the information correctly, and validate it against a JSON schema.

The focus is on exploring structured extraction (JSON, knowledge graphs, etc.). Validation is secondary.

## Data
Public datasets only. Sample datasets, sample scenarios / business cases and a tool setup checklist will be provided.

## Expected outcome
- New agentic techniques, such as context pruning or content summarization to grasp the content.
- Use of alternative storage techniques.
- A robust way to validate the responses.
- Business KPIs and extraction metrics.

**Results are judged on:** field-level precision / recall, schema validity, business KPIs and the novelty of the agentic technique.

## Setup
Do this **before the hackathon day** (repo is shared on 12 Nov).

- `git` and **Python 3.11+**, with a virtual environment (`python -m venv .venv` or `uv venv`).
- Your own LLM coding agent. No LLM access is provided by SIXT.
- Create `requirements.txt` / `pyproject.toml` in this folder for your own dependencies. Never commit secrets (use `.env`).
- A graph database is optional (e.g. Neo4j via Docker or Neo4j Desktop). Install it beforehand if you want to try the knowledge-graph route.
- Data: public datasets and sample scenarios will be added to this folder by the organizers. _[TBD: location]_
- Check: you can clone or fork the repo and run `python --version` in your environment.

## Submission
Code, a `SUBMISSION.md` in this folder (approach, results, how to run) and your metrics.
Also **either** a **1-minute demo video** (`submission/demo.mp4`, under 50 MB) **or** a **small set of slides** (`submission/slides.pdf`, max 5 slides) in your project folder, included in your repo.
