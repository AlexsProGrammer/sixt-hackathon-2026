# Hackathon Runbook (Organizers)

> Note: this folder lives in the same repo that participants clone. Keep it free of anything sensitive, or move it to a separate organizer-only repo before inviting participants.

## 1. Repository setup (private, invite only)

Hosted as a **private repo on a personal GitHub account** (not in the Sixt org, not public).

```bash
# from the repo root; --private is mandatory, never use --public
gh repo create sruthi-sixt-26/sixt-hacakthon-2026 --private --source=. --remote=origin --push
```

- Visibility: **private**. Verify after creation: `gh repo view --json visibility` must say `PRIVATE`.
- Personal repos have no teams, so add each participant as a collaborator with **Write** access (they get an email invite and must accept):
  ```bash
  gh api -X PUT repos/sruthi-sixt-26/sixt-hacakthon-2026/collaborators/<github-username> -f permission=push
  ```
- Free personal private repos allow collaborators, but branch protection on `main` may be unavailable on the free plan. If so, rely on the PR convention in the root README and review PRs before merging.
- Participants can fork a private repo only if they have access; ask them not to. Do not post the repo link publicly.
- Only commit public or mock data. Since this lives outside Sixt infrastructure, no internal code, real data, credentials or internal URLs in any file or commit message.
- After the event: remove collaborators and archive the repo.

## 2. Project overview

| Folder | Topic | Project owner | Data |
| --- | --- | --- | --- |
| Project_1 | Structured Extraction from Documents | Sruthi Radhakrishnan | Public datasets, sample scenarios |
| Project_2 | Nowcasting / Forecasting Mileage | Julian Hackinger | Mock or anonymized vehicle status sample |
| Project_3 | Predict Turnaround Action Time | Iulia Pasov | Mock or random sample |
| Project_4 | Predict Turnaround Tasks | Iulia Pasov | Mock or random sample |
| Project_5 | Meta-Evaluation of LLM-as-Judge | Jigyasa Singhal | Bitext (5 languages) + fictional policy, hidden test set |
| Project_J | Placeholder | TBD | TBD |

## 3. Checklist

### Before the event
- [ ] Confirm participant list and GitHub usernames
- [ ] Create the private repo and send invites
- [ ] Prepare and review data for each project (public or mock only; no real customer data)
- [ ] Fill in the "Setup" section of each project README
- [ ] Prepare the Project 5 starter toolkit, baseline judge and hidden test set (keep hidden set outside this repo)
- [ ] Decide on team sizes and assignment of teams to projects
- [ ] Set up the communication channel and tell participants where to ask for help
- [ ] Provide compute / LLM access (LLM API keys, graph database instance, etc.)
- [ ] Define judging criteria and jury
- [ ] Decide on Project_J topic

### Day of event
- [ ] Verify everyone can clone the repo
- [ ] Kickoff: walk through the root README step by step
- [ ] Volunteers visit teams on a schedule
- [ ] Remind teams of the submission deadline

### After the event
- [ ] Collect submissions (PRs per team)
- [ ] Score and announce results
- [ ] Remove collaborator access and archive the repo
- [ ] Follow up with interested students on next steps

## 4. Suggested agenda
_To be defined._

## 5. Judging
_To be defined. Suggested: problem understanding, quality of approach, results, presentation, reusability._
