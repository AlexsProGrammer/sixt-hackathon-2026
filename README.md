# SIXT Hackathon 2026

Welcome! This is the repo for the SIXT Hackathon, **Friday 13 November 2026**. Each project has its own folder with the problem, data and what to hand in.

> **The goal is not a perfect solution. It is *a* solution.**
> We will guide you and hack alongside you. Come fresh with your ideas, and let's build something cool.

<p align="center"><img src="assets/exist-first.svg" alt="Just make it exist first, you can make it good later" width="420"></p>

## Before you arrive

- [ ] Have a **GitHub account**.
- [ ] Install **git** and a language you like. We start with **Python 3.11+**, but any language works.
- [ ] Bring your own **LLM coding agent**. SIXT provides LLM API keys if your project needs one. Ask on site.
- [ ] Read all project READMEs and pick your **top 3**.
- [ ] Form a **team** of 1 to 3 and choose a team name. Solo? Ask an organizer.
- [ ] **Fork this repo** (step 1 below). Its link goes into the form.
- [ ] **Register** in the [form](https://forms.cloud.microsoft/e/S2dvqjeFBX) by **Thu 12 Nov, 17:00**: team name, top 3 topics, repo link. Topics are published here by **18:00**. Late? Register until **Fri 13 Nov, 10:00**. Late teams get the topics that still have room.
- [ ] Questions? Email your project owner.
- [ ] Bring a laptop, a charger and good energy :)

## The projects at a glance

Read this first, then the full README of each project, then rank your top 3.

### [Project 1](Project_1/README.md): Teach a machine to say "I don't know"
*Structured Extraction from Documents*

- **What it solves:** Right now people type contract and form data into our systems by hand. AI can do it in seconds, but one confident wrong value costs way more than a minute of human time. Build an extractor that books what it's sure about and hands the rest to a person.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Less typing, fewer expensive mistakes, and a clear number for how much each document saves.

### [Project 2](Project_2/README.md): Where is that car's odometer *right now*?
*Mileage Forecasting & Erroneous Mileage Detection*

- **What it solves:** On long-term rentals we only see the mileage when the car comes back, sometimes 4 weeks late. Yet valuation and defleet decisions need it today. Predict current and future mileage, and spot the reports that look fishy.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Better timing for selling cars, fewer valuation surprises, and wrong or manipulated reports caught early.

### [Project 3](Project_3/README.md): Judge the Judge
*Meta-Evaluation of LLM-as-Judge*

- **What it solves:** We use AI judges to decide if a chatbot change is an improvement. But they miss sneaky edits, like a dropped "as long as the car isn't reserved", that turn into promises we can't keep. Build a recipe that makes any judge catch them.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Chatbot releases we can actually trust, and no accidental promises to customers.

### [Project 4](Project_4/README.md): Right car, right station, next 14 days
*Fleet Allocation Challenge*

- **What it solves:** Some stations are drowning in cars while others run dry. Decide what to add, remove or move between stations to make the most profit, using only 8 weeks of history to guess demand.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Fewer missed rentals, higher utilization, and lower holding and transfer costs.

### [Project 5](Project_5/README.md): From business question to correct answer
*Enterprise Data Agent Challenge (TUM x SIXT)*

- **What it solves:** "What was net revenue?" sounds simple, but it means joining orders, payments and refunds, applying the right rules and the right exchange rates. Build an AI workflow that gets the numbers right, ideally with small, cheap models.
- **Possibility to collaborate after the hack:** Yes (thesis and arXiv publication)
- **Business value:** Trustworthy numbers on demand, without needing a data expert or a huge model every time.

## Get started

1. **Get your own copy of the repo.** Never push to this one.

   **Option A: Fork (recommended)**
   ```bash
   gh repo fork sruthi-sixt-26/sixt-hacakthon-2026 --clone
   cd sixt-hacakthon-2026
   ```
   No `gh`? Click **Fork** on GitHub, then `git clone <your fork url>`.

   **Option B: Clone and push to your own new repo**
   ```bash
   git clone https://github.com/sruthi-sixt-26/sixt-hacakthon-2026.git
   cd sixt-hacakthon-2026
   git remote rename origin upstream
   gh repo create my-sixt-hackathon --private --source=. --remote=origin --push
   ```

   **Check:** `git remote -v` shows your repo as `origin`.

   **Access:** organizers and your topic owner must be able to read your repo. Make it public, or add them and `sruthi-sixt-26` as collaborators. A fork of this repo is always public, so use Option B for a private repo. In a team, one person creates the repo and adds the others.

2. **Find your project** once topics are published, then delete the others:
   ```bash
   git rm -r Project_2 Project_3 Project_4 Project_5   # example: matched to Project_1
   git commit -m "Keep only my project folder"
   git push
   ```
3. **Set up (about 10 min).** In your project folder run `bash setup.sh`. It creates a Python environment (`.venv`), installs the dependencies and runs a quick check. Prefer another language? Skip it and follow the project README.
   - Project 4 needs **Python 3.14+**; the others need 3.11+. Use `PYTHON=python3.x bash setup.sh` to pick a version.
   - Projects 1 and 3 copy `.env.example` to `.env`. Add the LLM key handed out on site there (git-ignored, never commit it).
   - Project 2 prints "No data yet" until you put the organizers' CSV in `data/`. That is expected.
4. **Build.** Stay in your project folder. Commit and push often, `git pull` before each session.
5. **Ask for help.** Any organizer or your topic owner, on site.
6. **Submit by 16:45.** Your repo link from the form is your submission. It needs:
   - your code,
   - a short `SUBMISSION.md` ([template](SUBMISSION_TEMPLATE.md)),
   - **either** a 1-minute demo video (`submission/demo.mp4`, under 50 MB) **or** max 5 slides (`submission/slides.pdf`),
   - anything else your project README asks for.
7. **Present** to the jury.

## Let your coding agent do the setup

Let your coding agent do it, but understand what it does. Check that `git` and `gh auth status` work, open a terminal in an empty folder and paste:

```text
Set up my SIXT hackathon repo.
1. Fork sruthi-sixt-26/sixt-hacakthon-2026 with gh repo fork --clone.
   Never push to the original.
2. My team was matched to <Project_N>. Delete every other Project_* folder
   with git rm -r, then commit and push to my fork.
3. Read my project's README.md and set up its environment.
4. Tell me what you did and what the task is.
Rules: public or mock data only, no secrets or .env, stay in my project folder.
```

Then keep the agent in your project folder and read what it commits.

## Rules

- **Public or mock data only.** No real SIXT, customer or personal data.
- **No secrets** in git. Use `.env` (git-ignored).
- Stay in your project folder. Do not push branches to this repo.
- A public team repo may only contain your project folder.

## Good to know

- **Publication.** You can turn your work into an arXiv-style paper. Ask the TUM people. Templates will be in [arxiv_templates/](arxiv_templates/README.md). Reach out even after the hackathon.

## Repository layout

```
sixt-hacakthon-2026/
├── README.md              <- you are here
├── Project_1/ ... Project_5/
├── SUBMISSION_TEMPLATE.md
├── arxiv_templates/       <- optional paper templates
├── CodeRabbit_Python/     <- optional AI code review
└── runbook/               <- organizer runbook
```
