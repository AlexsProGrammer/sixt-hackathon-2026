# SIXT Hackathon 2026

Welcome! This is the repo for the SIXT Hackathon, **Friday 13 November 2026**. Each project has its own folder with the problem, data and what to hand in.

> **The goal is not a perfect solution. It is *a* solution.**
> We will guide you and help you hack. Come fresh with your ideas, and let's build something cool together as **ONE team** #team_orange

<p align="center"><img src="assets/exist-first.svg" alt="Just make it exist first, you can make it good later" width="420"></p>

Three steps:

- **1.** Read the projects
- ⭐ **2. Fill in the Team + Topic Registration form, the most important one!**
- **3.** Do a little prep before you arrive

## 1. Read the projects at a glance

<img src="assets/time-projects.svg" alt="About 10 minutes" width="360">

Have a look at each project, open the full README of any that catches your eye, then pick your top 3.

### [Project 1](Project_1/README.md): Teach a machine to say "I don't know"
*Structured Extraction from Documents*

**SIXT Tech Team:** Sruthi Radhakrishnan, Ihsan Soydemir

- **What it solves:** Right now people type contract and form data into our systems by hand. AI can do it in seconds, but one confident wrong value costs way more than a minute of human time. Build an extractor that books what it's sure about and hands the rest to a person.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Less typing, fewer expensive mistakes, and a clear number for how much each document saves.

### [Project 2](Project_2/README.md): Where is that car's odometer *right now*?
*Mileage Forecasting & Erroneous Mileage Detection*

**SIXT Tech Team:** Julian Hackinger, Ernest Quintana

- **What it solves:** On long-term rentals we only see the mileage when the car comes back, sometimes 4 weeks late. Yet valuation and defleet decisions need it today. Predict current and future mileage, and spot the reports that look fishy.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Better timing for selling cars, fewer valuation surprises, and wrong or manipulated reports caught early.

### [Project 3](Project_3/README.md): Judge the Judge
*Meta-Evaluation of LLM-as-Judge*

**SIXT Tech Team:** Jigyasa Singhal

- **What it solves:** We use AI judges to decide if a chatbot change is an improvement. But they miss sneaky edits, like a dropped "as long as the car isn't reserved", that turn into promises we can't keep. Build a recipe that makes any judge catch them.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Chatbot releases we can actually trust, and no accidental promises to customers.

### [Project 4](Project_4/README.md): Right car, right station, next 14 days
*Fleet Allocation Challenge*

**SIXT Tech Team:** Sara Michetti, Julian Mehne

- **What it solves:** Some stations are drowning in cars while others run dry. Decide what to add, remove or move between stations to make the most profit, using only 8 weeks of history to guess demand.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Fewer missed rentals, higher utilization, and lower holding and transfer costs.

### [Project 5](Project_5/README.md): From business question to correct answer
*Enterprise Data Agent Challenge (TUM x SIXT)*

**TUM Team:** Ioannis Tzachristas

- **What it solves:** "What was net revenue?" sounds simple, but it means joining orders, payments and refunds, applying the right rules and the right exchange rates. Build an AI workflow that gets the numbers right, ideally with small, cheap models.
- **Possibility to collaborate after the hack:** Yes (thesis and arXiv publication)
- **Business value:** Trustworthy numbers on demand, without needing a data expert or a huge model every time.

### [Project 6](Project_6/README.md): Task Time Detective
*Turnaround Task Duration Estimation*

**SIXT Tech Team:** Iulia Pasov

- **What it solves:** When a car comes back we clean, check, refuel or charge it, but we only know which tasks were done and the total time until it was ready, not how long each task took. Work out each task's duration from totals alone, and predict when a returned car will be ready.
- **Possibility to collaborate after the hack:** Yes
- **Business value:** Better staff planning at branches, and reliable "your car is ready at" times for customers.

## 2. Fill in the Team + Topic Registration form

<img src="assets/time-register.svg" alt="About 3 minutes" width="360">

We would love to know who is coming, it only takes about 3 minutes, and nothing is final, so just pick what sounds fun right now :)

> **[Open the Team + Topic Registration form](https://forms.cloud.microsoft/e/S2dvqjeFBX)**
> If you can, please fill it in by **Thursday 12 November, 17:00** and we will share the matches here by **18:00**

What we will ask:

1. **A team name**, teams have 1 to 3 people, coming alone is fine, and if you want teammates just tell an organizer
2. **Your top 3 topics** from the [projects at a glance](#1-read-the-projects-at-a-glance), they are here from **Thu 09:00** and there are no wrong choices
3. **Your repo link**, [fork this repo](#get-started) first, it takes about two minutes, and if you get stuck just ask us

**Running late? No problem!** The form stays open until **Fri 13 Nov, 9:30** (hint: you can only start hacking once your topic is confirmed, so register early to start sooner) and late teams get the topics that still have room

## 3. Before you arrive

<img src="assets/time-before-you-arrive.svg" alt="About 5 minutes" width="360">

This takes about **5 minutes** and means more time for the fun part, no stress if you can't tick everything off

- [ ] Have a **GitHub account** ready
- [ ] Install **git** and a language you like, we start with **Python 3.11+** but anything works
- [ ] Bring your favourite **LLM coding agent**, and if your project needs an API key we will hand one out on site
- [ ] **Fork this repo** (see [Get started](#get-started)), its link goes into the Team + Topic Registration form
- [ ] Questions? Email your project owner, they're happy to hear from you
- [ ] Bring a laptop, a charger and good energy :)

## Get started

1. **Get your own copy of the repo.** Never push to this one.

   **Option A: Fork (recommended)**
   ```bash
   gh repo fork sixt-hackathon-2026/sixt-hackathon-2026 --clone
   cd sixt-hackathon-2026
   ```
   No `gh`? Click **Fork** on GitHub, then `git clone <your fork url>`.

   **Option B: Clone and push to your own new repo**
   ```bash
   git clone https://github.com/sixt-hackathon-2026/sixt-hackathon-2026.git
   cd sixt-hackathon-2026
   git remote rename origin upstream
   gh repo create my-sixt-hackathon --public --source=. --remote=origin --push
   ```

   **Check:** `git remote -v` shows your repo as `origin`.

   **Access:** your repo must be **public** so organizers and your topic owner can read it. A fork is public by default. In a team, one person creates the repo and adds the others as collaborators.

2. **Find your project** once your team and topic match is published (Thu by 18:00), then delete the other `Project_*` folders (recommended, it keeps your repo tidy). Keep everything else, like the LICENSE, README and handout:
   ```bash
   git rm -r Project_2 Project_3 Project_4 Project_5 Project_6   # example: matched to Project_1
   git commit -m "Keep only my project folder"
   git push
   ```
3. **Set up (under 5 min).** In your project folder run `bash setup.sh`. It creates a Python environment (`.venv`), installs the dependencies and runs a quick check. Prefer another language? Skip it and follow the project README.
   - Project 4 needs **Python 3.14+**; the others need 3.11+. Use `PYTHON=python3.x bash setup.sh` to pick a version.
   - Projects 1 and 3 copy `.env.example` to `.env`. Add the LLM key handed out on site there (git-ignored, never commit it).
   - Project 2 runs on a small `example_file.csv` until you get the full data. Put it in `data/` when you do.
4. **Build.** Stay in your project folder. Commit and push often, `git pull` before each session.
5. **Ask for help.** Any organizer or your topic owner, on site.
6. **Submit by 16:45.** Your repo link from the Team + Topic Registration form is your submission. It needs:
   - your code,
   - a short `SUBMISSION.md` ([template](SUBMISSION_TEMPLATE.md)),
   - **either** a 1-minute demo video (`submission/demo.mp4`, under 50 MB) **or** max 5 slides (`submission/slides.pdf`),
   - anything else your project README asks for.
7. **Present** to the jury (finalist teams)

## Let your coding agent do the setup

Let your coding agent do it, but understand what it does. Check that `git` and `gh auth status` work, open a terminal in an empty folder and paste:

```text
Set up my SIXT hackathon repo.
1. Fork sixt-hackathon-2026/sixt-hackathon-2026 into MY OWN GitHub account (not an org)
   with gh repo fork --clone, then cd into the cloned folder.
   Never push to the original. If the fork fails, tell me and stop.
2. Ask me which project my team was matched to (<Project_N>). Delete only the other
   Project_* folders with git rm -r. Keep everything else (LICENSE, README, runbook,
   handout, assets). Then commit and push to my fork's default branch.
3. From inside Project_N/, read README.md and run bash setup.sh.
4. Tell me what you did and what the task is.
Rules: public or mock data only, no secrets or .env, stay in my project folder.
Do not ask for or fill in API keys, they are handed out on site.
```

Then keep the agent in your project folder and read what it commits.

## Rules

- **Public or mock data only.** No real SIXT, customer or personal data.
- **No secrets** in git. Use `.env` (git-ignored).
- Stay in your project folder. Do not push branches to this repo.
- Your team repo can hold more than your project folder, but your `SUBMISSION.md` must say which project you chose.

## Good to know

- **Publication.** You can turn your work into an arXiv-style paper. Ask the TUM people. Templates will be in [arxiv_templates/](arxiv_templates/README.md). Reach out even after the hackathon.
- **AI code review (optional).** Curious about AI-based code reviews? Try CodeRabbit on your own fork, the [setup guide](CodeRabbit_Python/README.md) takes a few minutes and comes with a small sample project to play with.

## Repository layout

```
sixt-hackathon-2026/
├── README.md              <- you are here
├── Project_1/ ... Project_6/
├── SUBMISSION_TEMPLATE.md
├── arxiv_templates/       <- optional paper templates
├── CodeRabbit_Python/     <- optional AI code review
└── runbook/               <- runbook
```
