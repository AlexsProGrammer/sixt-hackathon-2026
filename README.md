# SIXT Hackathon 2026 (TUM x SIXT)

Welcome! This is the **private, invite-only** repository for the hackathon. Each project has its own folder with a README describing the problem, approach, data and expected outcome.

## Step-by-step: how to get started

1. **Accept your invite.** You will receive a GitHub invitation by email. Accept it, otherwise you will see a 404 on this repo. Make sure 2FA is enabled on your GitHub account.
2. **Clone the repo.**
   ```bash
   git clone https://github.com/<organizer-github-username>/sixt-hacakthon-2026.git
   cd sixt-hacakthon-2026
   ```
3. **Pick your project.** Read the README in each folder and agree on one with your team:

   | Folder | Topic |
   | --- | --- |
   | [Project_1](Project_1/README.md) | Structured Extraction from Documents |
   | [Project_2](Project_2/README.md) | Nowcasting / Forecasting Mileage |
   | [Project_3](Project_3/README.md) | Predict Turnaround Action Time |
   | [Project_4](Project_4/README.md) | Predict Turnaround Tasks |
   | [Project_5](Project_5/README.md) | Meta-Evaluation Framework for LLM-as-Judge Agentic Systems |
   | [Project_J](Project_J/README.md) | Placeholder, to be announced |

4. **Create your team branch.** Work only inside your project folder.
   ```bash
   git checkout -b team/<project-number>-<team-name>
   ```
5. **Set up your environment.** Follow the setup section in your project README (Python version, dependencies, data download).
6. **Build.** Commit early and often. Push your branch regularly:
   ```bash
   git add Project_<n>/
   git commit -m "Short description"
   git push -u origin team/<project-number>-<team-name>
   ```
7. **Ask for help.** Find a volunteer or post in the hackathon channel (see the runbook for details).
8. **Submit.** Before the deadline, make sure your branch contains your code, a short `SUBMISSION.md` in your project folder (approach, results, how to run) and anything else your project README asks for. Open a pull request against `main`.
9. **Present.** Demo your results to the jury.

## Rules

- Use **public or mock data only**. Never commit real SIXT, customer or personal data.
- Never commit secrets (API keys, tokens). Use environment variables and `.env` (already git-ignored).
- Stay inside your own project folder.
- Do not share this repository or its contents outside the hackathon.

## Repository layout

```
sixt-hacakthon-2026/
├── README.md        <- you are here
├── runbook/         <- organizer runbook
├── Project_1/ ... Project_5/
└── Project_J/       <- placeholder
```
