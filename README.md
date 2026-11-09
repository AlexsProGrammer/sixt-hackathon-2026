# SIXT Hackathon 2026

Welcome! This is the **private, invite-only** repository for the hackathon. Each project has its own folder with a README describing the problem, approach, data and expected outcome.

## Before you arrive (Thursday 12 November)

You get the GitHub invite on Thursday 12 November at 09:00. Accept it and you can get started right away.

The hackathon is on **Friday, 13 November 2026**. Please do this beforehand so you can spend the day on the problem, not on installing tools:

- [ ] Accept the GitHub invite and enable 2FA.
- [ ] Clone (or fork) this repo, see step 2 below, and confirm it works.
- [ ] Install **git** and **Python 3.11+** (and `uv` or `venv`). Your project README may list extra tools.
- [ ] Have your **own LLM coding agent** ready (whichever you are comfortable with). SIXT does not provide LLM access.
- [ ] Read the README of every project, pick your top choice and think about how you would approach it.
- [ ] Talk to your teammates (teams have 1 to 3 people; if you are on your own, you can join an existing team of up to 3, ask an organizer) and decide on your topic. Submit your team and **one or two topics per team** in the form (name one as your primary topic), together with the link to your fork, **by 10:00 on 13 November** _[form link TBD]_. We cannot take changes after that time. Since you have the topics a day ahead, we hope you can decide before you arrive.
- [ ] Questions before the day? Email the owner of the project directly.
- [ ] Bring a laptop and charger, plus a lot of cool energy :) 

## Step-by-step: how to get started

1. **Accept your invite.** You will receive a GitHub invitation by email. Accept it, otherwise you will see a 404 on this repo. Make sure 2FA is enabled on your GitHub account.
2. **Get the repo: clone it or fork it.** Everyone must clone the repo or fork it into their own GitHub account and work there. **Do not push branches to this repo**, we keep it simple.

   ```bash
   gh repo fork sruthi-sixt-26/sixt-hacakthon-2026 --clone
   cd sixt-hacakthon-2026
   ```
   Or click **Fork** on the repo page on GitHub, then `git clone` your fork. Your fork is private by default. For a team, one person forks and adds the teammates as collaborators on the fork (Settings, Collaborators). Your repo link goes into the form (see step 8). Your repo must be readable by the organizers: either make it public, or add your topic owner(s) as collaborators by email or GitHub username. GitHub does not let you make a fork of a private repo public, so if you want a public repo, create a new one and copy your project folder into it.

   Check it worked: `git remote -v` and `ls` should show the project folders.

3. **Pick your project.** Read the README in each folder and agree on one with your team:

   | Folder | Topic |
   | --- | --- |
   | [Project_1](Project_1/README.md) | Structured Extraction from Documents |
   | [Project_2](Project_2/README.md) | Nowcasting / Forecasting Mileage |
   | [Project_3-4](Project_3-4/README.md) | Turnaround: Predict Action Time and Predict Tasks (one topic for now) |
   | [Project_5](Project_5/README.md) | Meta-Evaluation Framework for LLM-as-Judge Agentic Systems |
   | [Project_7](Project_7/README.md) | TUM x SIXT topic, to be announced (not yet open for selection) |
   | [Project_6](Project_6/README.md) | Placeholder, to be announced (not yet open for selection) |

4. **Work in your own project folder.** Work only inside your project folder, in your fork (or clone). Teammates share the fork, so run `git pull` before each work session to get their changes.

5. **Set up your environment.** Follow the setup section in your project README (Python version, dependencies, data download).
6. **Build.** Commit early and often, and push regularly. If `git push` is rejected, run `git pull` first and push again.
   ```bash
   git add Project_<n>/
   git commit -m "Short description"
   git pull
   git push
   ```
7. **Ask for help.** On the day, ask any organizer or your topic owner on site. Before the day, email the owner of your project (see the README in each project folder).
8. **Submit.** Before the deadline, make sure your repo contains your code, a short `SUBMISSION.md` in your project folder (approach, results, how to run), **either** a **1-minute demo video** (`submission/demo.mp4`, under 50 MB) **or** a **small set of slides** (`submission/slides.pdf`, max 5 slides) in your project folder (your choice), and anything else your project README asks for. Push everything to your fork and **enter the link to your GitHub repo in the form**. Fork first, so you have the link when you submit your topic by 10:00; you can keep pushing to the same repo until 16:45. **The repo link is your submission**: what is in the repo at the deadline is what we review. Make sure the organizers and your topic owner can open it: either make the repo public, or add your topic owner(s) as collaborators by email or GitHub username (and `sruthi-sixt-26`). If you work on two topics, put each in its own project folder and say which is your primary topic. Use [SUBMISSION_TEMPLATE.md](SUBMISSION_TEMPLATE.md) as a starting point for `SUBMISSION.md`.
9. **Present.** Demo your results to the jury.

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
