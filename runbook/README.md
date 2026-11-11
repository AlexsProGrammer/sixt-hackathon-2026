# Hackathon Runbook (Organizers)

> This folder lives in the repo participants clone. Keep it free of anything sensitive, or move it to an organizer-only repo before inviting participants.

## 1. Repository setup

- **Private repo on a personal GitHub account** (not the Sixt org, never public). Verify: `gh repo view --json visibility` says `PRIVATE`.
- Add each participant as a collaborator with Write access (they must accept the email invite):
  ```bash
  gh api -X PUT repos/<owner>/<repo>/collaborators/<github-username> -f permission=push
  ```
- Participants clone or fork (forks of a private repo stay private; teams that want a public repo create a new one with only their project folder; otherwise they add their topic owner as collaborator by email or GitHub username). Test on day one that forking works on the free plan. Branch protection may be unavailable on the free plan, so rely on the convention that participants do not push to this repo.
- Public or mock data only. No internal code, real data, credentials or internal URLs in files or commit messages.
- After the event: remove collaborators and archive the repo.

## 2. Projects

| Folder | Topic | Data |
| --- | --- | --- |
| Project_1 | Structured Extraction from Documents | Public datasets, sample scenarios |
| Project_2 | Nowcasting / Forecasting Mileage | Mock or anonymized vehicle status sample |
| Project_3 | Meta-Evaluation of LLM-as-Judge | Bitext (5 languages) + fictional policy, hidden test set |
| Project_4 | Fleet Allocation Challenge | Mock fleet data (in Project_4/data) |
| Project_5 | Enterprise Data Agent Challenge (TUM x SIXT collaboration) | Provided separately by TUM |

Owners and contact emails are in each project README.

## 3. Checklist

### Timeline
| When | What |
| --- | --- |
| Until 11 Nov | Finish data and setup sections; collect GitHub usernames; all 5 topics are final |
| 11 Nov | Dry run: fresh clone and setup on a clean machine for every project |
| 12 Nov, 09:00 | Send repo invites (participants accept the link and can start), topics, agenda and the "Before you arrive" checklist |
| 13 Nov | Hackathon (agenda in `runbook/handout.html` and `internal-agenda.md`) |
| Following week | Remove collaborators, archive repo, follow up with interested students |

### Before the event
- [ ] Review data for each project (public or mock only)
- [ ] Fill in each project's "Setup" section
- [ ] Prepare the Project 3 starter toolkit, baseline judge and hidden test set (keep the hidden set outside this repo)
- [ ] Registration form (https://forms.cloud.microsoft/e/S2dvqjeFBX): team name, top 3 topics, GitHub repo link. Round 1 closes Thursday 12 Nov 17:00; run the matching and publish results in the repo by 18:00. Final deadline Friday 13 Nov 10:00: second matching for late teams, first come, first served, into topics with room. Link is in the handout and README
- [ ] Put owner emails in the root README and handout
- [ ] Tell participants to bring their own LLM coding agent; SIXT provides LLM API keys for tasks that need one (Project_3, Project_4 setup lines say so); check each project works that way
- [ ] Define judging criteria and jury
- [ ] Print the handout (`runbook/handout.pdf`, 2 pages, double-sided), one per team

### Day of event
- [ ] Verify everyone can clone and run the setup check; fix broken setups first
- [ ] Walk through the root README for needed teams
- [ ] Visit teams on a schedule stay close touch and remind them on deadlines

### After the event
- [ ] Collect repo links from teams, score, announce results
- [ ] Remove collaborators and archive the repo
- [ ] Follow up with interested students

## 4. Event details

| | |
| --- | --- |
| Date | Friday, 13 November 2026 (repo public and topics available Thursday 12 Nov, 09:00) |
| Location | HQ Pullach, Academy |
| Team size / topics | 1 to 3 people; max 5 teams per topic (set as the capacity in the matching program) |
| Topic selection | Form (team name, top 3 topics, repo link): round 1 closes Thursday 17:00, results in the repo by 18:00; final deadline Friday 10:00, late teams matched first come, first served. Form: https://forms.cloud.microsoft/e/S2dvqjeFBX |
| LLM tools | Participants bring their own coding agent; SIXT provides LLM API keys for tasks that need one |
| Help | On site; before the event email the topic owner |

Keep this in sync with `runbook/handout.html`.

### Topic selection and balancing
Expect 40 to 50 participants, so about 14 to 25 teams. Encourage teams of 2 to 3.
- **Thursday 17:00:** round 1 closes. Matching runs; results published by 18:00.
- **Friday 10:00:** final deadline. Second matching for late teams, first come, first served, into topics with room; fix remaining problems by about 10:15.

**Not enough people for a topic (decide before 12 Nov):**
1. Set a go / no-go rule (recommended: a topic runs with at least 2 teams) and announce it at kick-off.
2. Keep active topics few (all 5 are final; merge or drop a topic only if it is clearly under-subscribed).
3. Ask before moving anyone; let solo participants join existing teams.
4. A topic with 1 or 2 teams can still run; finalists are chosen across all topics.
5. Closed-topic owners can float as mentors.

## 5. Collaboration after the event

Tell participants up front that strong work can lead to follow-ups: thesis, working student, internship, guided research, or an entry-level role.

To prepare:
- [ ] Confirm which positions are really open (headcount, start dates) with owners and HR; list them per project
- [ ] Agree thesis supervision with TUM
- [ ] Confirm which HR colleagues attend and what they can offer
- [ ] Collect interest (short form), tell participants how data is used (GDPR), keep it only for this purpose
- [ ] Have the jury note standout individuals; plan a "what's next" slot and follow-ups within a week
- [ ] Make no promises at the event; say "we would like to talk"

## 6. Judging

### Principles
- Judge what teams built and can show, not slideware. Same criteria for every project.
- Each team has one assigned topic from the matching; it is reviewed and scored there. Team counts below are by assigned topic.
- Stage 1: topic owners review their teams and pick 6 finalists overall. Stage 2: the jury scores finalists at the pitches. Jurors score independently before discussing.

### Scoring (100 points)

| Criterion | Points | What the jury looks for |
| --- | --- | --- |
| Problem understanding | 15 | Grasp of the business problem and constraints |
| Quality of approach | 25 | Sound, justified method; baseline comparison; awareness of limits |
| Results | 25 | Measured evidence against project metrics; honest evaluation, no leakage |
| Business relevance and reusability | 15 | Could Sixt use it? Clear next steps |
| Code quality and reproducibility | 10 | Runs from `SUBMISSION.md`, readable, no secrets or real data |
| Presentation and demo | 10 | Clear story, working demo, good answers |

### Project-specific results metrics

| Project | Results are judged on |
| --- | --- |
| Project_1 | Field-level precision / recall, schema validity, business KPIs, novelty |
| Project_2 | Error on held-out vehicles / periods (MAE, MAPE) vs a naive baseline |
| Project_3 | Score on the hidden test set, kappa and consistency, reusability |

### Bonus and penalties
- **Bonus (up to +5):** exceptional insight or particularly clean engineering.
- **Disqualification:** real Sixt, customer or personal data; committed secrets; training on the hidden test set (Project_3).
- **Late:** a repo with no pushes by the deadline (or a link that cannot be opened) loses the Code and Results points that cannot be verified.

### Process
1. **16:45:** submission = the team's GitHub repo (link collected in the form) with code, `SUBMISSION.md`, and **either** a 1-min demo video (`submission/demo.mp4`, under 50 MB) **or** slides (`submission/slides.pdf`, max 5).
2. **16:45 – 17:45 reviews:** owners read each submission and ask clarifying questions (remote owners use the GitHub links). Owners fill in the score sheet.
3. **17:45:** owners pick 6 finalists across all topics. If a topic has no submission meeting the owner's standard, the next best from another topic takes its place.
4. **17:45 – 18:20 final pitches:** 3 min + 2 min Q&A each; jury scores independently.
5. **18:20 prizes:** highest total wins; ties go to the higher Results score, then jury discussion. Give feedback to every team afterwards.

### Jury and prizes
- Stage 1: topic owners. Stage 2: **[TBD: jury composition]**; owners should not score finalists of their own topic if feasible.
- Prizes: **[TBD]**

### Score sheet (one per juror per team)

| Team / Project | Problem (15) | Approach (25) | Results (25) | Relevance (15) | Code (10) | Demo (10) | Bonus (0-5) | Total | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | | |

## 7. Participant handout

Source `runbook/handout.html`, printable `runbook/handout.pdf` (agenda and contacts on the front; deliverables and criteria on the back). After filling in the **[TBD]** fields, re-export:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --no-pdf-header-footer \
  --print-to-pdf="$PWD/runbook/handout.pdf" "file://$PWD/runbook/handout.html"
```

Check it is exactly 2 A4 pages; print double-sided, flip on the long edge.
