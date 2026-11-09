# SIXT Hackathon 2026

Welcome! This is the **private, invite-only** repository for the hackathon. Each project has its own folder with a README describing the problem, approach, data and expected outcome.

## Before you arrive (Thursday 12 November)

The hackathon is on **Friday, 13 November 2026**. You get the GitHub invite on Thursday 12 November at 09:00. Please do the following beforehand so you can spend the day on the problem, not on setup:

- [ ] **Accept the GitHub invite** (check your email, otherwise you will see a 404 on this repo). Enabling 2FA is optional but recommended: it protects this private repo if your account is compromised.
- [ ] **Fork or clone this repo** (step 1 below, both are fine).
- [ ] Install **git** and **Python 3.11+** (and `uv` or `venv`). Your project README may list extra tools.
- [ ] Have your **own LLM coding agent** ready (whichever you are comfortable with). LLM API access from SIXT is still to be decided. If it is provided, you can request a key on site.
- [ ] Read the README of every project and pick your top choice.
- [ ] Agree on your team (1 to 3 people; if you are on your own, ask an organizer to join a team) and your topic(s). **Submit team, topic and fork link in the form by 10:00 on 13 November** _[form link TBD]_. We cannot take changes after that time.
  - Choose **one topic**, plus optionally **one backup topic** (name your primary). The maximum is 2. We really recommend one, but if you have the will to take on a second, we will make the way for you.
- [ ] Questions before the day? Email the owner of the project directly.
- [ ] Bring a laptop and charger, plus a lot of cool energy :)

## Get started

1. **Get your own copy of the repo.** Do **not** push to this repo. Choose **one** option (both work, you need a repo of your own either way, because its link goes into the form):

   **Option A: Fork (recommended, 2 commands)**
   ```bash
   gh repo fork sruthi-sixt-26/sixt-hacakthon-2026 --clone
   cd sixt-hacakthon-2026
   ```
   No `gh`? Click **Fork** on this repo's GitHub page, then `git clone <your fork url>`.

   **Option B: Clone and push to a new repo of your own**
   ```bash
   git clone https://github.com/sruthi-sixt-26/sixt-hacakthon-2026.git
   cd sixt-hacakthon-2026
   git remote rename origin upstream
   gh repo create my-sixt-hackathon --private --source=. --remote=origin --push
   ```
   No `gh`? Create an empty repo on GitHub, then `git remote add origin <your repo url>` and `git push -u origin main`.

   **Check it worked:** `git remote -v` shows your repo as `origin`, and `ls` shows the project folders.

   **Share access:** your repo must be readable by the organizers and your topic owner. Either make it public, or add them and `sruthi-sixt-26` as collaborators (Settings, Collaborators). For a team, one person creates the repo and adds the teammates. A fork of a private repo cannot be made public; if you want a public repo, use Option B.

2. **Pick your project(s)**, then **delete all other project folders** in your repo. Keep one (or two at most, see above).

   | Folder | Topic |
   | --- | --- |
   | [Project_1](Project_1/README.md) | Structured Extraction from Documents |
   | [Project_2](Project_2/README.md) | Nowcasting / Forecasting Mileage |
   | [Project_3-4](Project_3-4/README.md) | Turnaround: Predict Action Time and Predict Tasks (one topic for now) |
   | [Project_5](Project_5/README.md) | Meta-Evaluation Framework for LLM-as-Judge Agentic Systems |
   | [Project_7](Project_7/README.md) | TUM x SIXT topic, to be announced (not yet open for selection) |
   | [Project_6](Project_6/README.md) | Placeholder, to be announced (not yet open for selection) |

   ```bash
   git rm -r Project_2 Project_5 Project_6 Project_7   # example: keeping Project_1 and Project_3-4
   git commit -m "Keep only my project folders"
   git push
   ```

3. **Set up your environment.** Follow the setup section in your project README (Python version, dependencies, data download).
4. **Build.** Work only inside your project folder. Commit early and push regularly. Teammates share the fork, so run `git pull` before each session.

   ```bash
   git add Project_<n>/
   git commit -m "Short description"
   git pull
   git push
   ```

5. **Ask for help.** On the day, ask any organizer or your topic owner on site. Before the day, email the owner of your project (see the README in each project folder).
6. **Submit** before the deadline (**16:45**). Push everything to your fork; **the repo link you entered in the form is your submission**, and what is in the repo at the deadline is what we review. It must contain:
   - your code,
   - a short `SUBMISSION.md` in your project folder (approach, results, how to run), see [SUBMISSION_TEMPLATE.md](SUBMISSION_TEMPLATE.md),
   - **either** a **1-minute demo video** (`submission/demo.mp4`, under 50 MB) **or** a **small set of slides** (`submission/slides.pdf`, max 5 slides),
   - anything else your project README asks for.

   If you work on a backup topic too, keep each in its own project folder and say which is your primary one.
7. **Present.** Demo your results to the jury.

## Let your coding agent do it

You can hand the setup to your coding agent (Claude Code, Cursor, Copilot, etc.). Accept the invite and check that `git` and `gh auth status` work first, then open a terminal in an empty folder and paste:

```text
Set up my SIXT hackathon repo.
1. Get me my own copy of sruthi-sixt-26/sixt-hacakthon-2026: fork it with
   gh repo fork sruthi-sixt-26/sixt-hacakthon-2026 --clone (or, if I prefer cloning, clone it and
   push to a new private repo of my own). Never push to the original repo.
2. I chose <Project_N> (and optionally <Project_M> as backup). Delete every other
   Project_* folder with git rm -r, commit and push to my fork.
3. Read my project's README.md and set up the environment it describes
   (Python 3.11+, uv or venv, dependencies, data download).
4. Tell me what you did, and what the project README says the task is.
Rules: only public or mock data, never commit secrets or .env, work only inside my project folder.
```

Afterwards, keep the agent inside your project folder, and make sure it never commits secrets or real data (see Rules).

## Rules

- Use **public or mock data only**. Never commit real SIXT, customer or personal data.
- Never commit secrets (API keys, tokens). Use environment variables and `.env` (already git-ignored).
- Stay inside your own project folder and do not push branches to this repo.
- Your repo can be public or private. If it is public, it must contain only your own project folder and public or mock data. If it is private, add your topic owner(s) as collaborators.
- Do not share this repository or its contents outside the hackathon.

## Good to know

- **Publication opportunity.** There is also the possibility to turn your work into an arXiv-style publication. Reach out to the TUM people to get started. Reference templates will be added in [arxiv_templates/](arxiv_templates/README.md). Feel free to reach out to us even after the hackathon for this publication.

## Repository layout

```
sixt-hacakthon-2026/
├── README.md        <- you are here
├── runbook/         <- organizer runbook
├── CodeRabbit_Python/ <- optional AI code review setup (see its README)
├── arxiv_templates/ <- templates for the optional arXiv-style publication (coming later)
├── Project_1/, Project_2/, Project_3-4/, Project_5/
├── Project_6/       <- placeholder, not yet open
├── Project_7/       <- TUM x SIXT topic, not yet open
└── SUBMISSION_TEMPLATE.md
```
