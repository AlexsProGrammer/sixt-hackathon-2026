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
| Project_3-4 | Turnaround: Predict Action Time and Predict Tasks (run as one topic for now, to be adapted after hearing from the owner) | Mock or random sample |
| Project_5 | Meta-Evaluation of LLM-as-Judge | Bitext (5 languages) + fictional policy, hidden test set |
| Project_7 | TUM x SIXT topic | TBD |
| Project_6 | Placeholder | TBD |

Owners and contact emails are in each project README.

## 3. Checklist

### Timeline
| When | What |
| --- | --- |
| Until 11 Nov | Finish data and setup sections; collect GitHub usernames; decide Project_6 and define Project_7 |
| 11 Nov | Dry run: fresh clone and setup on a clean machine for every project |
| 12 Nov, 09:00 | Send repo invites (participants accept the link and can start), topics, agenda and the "Before you arrive" checklist |
| 13 Nov | Hackathon (agenda in `runbook/handout.html` and `internal-agenda.md`) |
| Following week | Remove collaborators, archive repo, follow up with interested students |

### Before the event
- [ ] Review data for each project (public or mock only)
- [ ] Fill in each project's "Setup" section
- [ ] Prepare the Project 5 starter toolkit, baseline judge and hidden test set (keep the hidden set outside this repo)
- [ ] Create the topic form (one or two topics per team, max 5 teams per topic, closes 10:00 on 13 Nov; asks for team members, primary topic and the link to the team's GitHub repo) and add its link to the handout and README
- [ ] Put owner emails in the root README and handout
- [ ] Tell participants to bring their own LLM coding agent (no SIXT LLM access); check each project works that way
- [ ] Define judging criteria and jury
- [ ] Print the handout (`runbook/handout.pdf`, 2 pages, double-sided), one per team

### Day of event
- [ ] Verify everyone can clone and run the setup check; fix broken setups first
- [ ] Walk through the root README for needed teams
- [ ] Visit teams on a schedule stay close touch and remind them on deadlines

### After the event
- [ ] Export repo links from the form, score, announce results
- [ ] Remove collaborators and archive the repo
- [ ] Follow up with interested students

## 4. Event details

| | |
| --- | --- |
| Date | Friday, 13 November 2026 (repo invites and topics sent 12 Nov, 09:00) |
| Location | HQ Pullach, Academy |
| Team size / topics | 1 to 3 people; max 5 teams per topic |
| Topic selection | One team can work on one or two topics, form closes 10:00 on 13 Nov. Link: **[TBD]** |
| LLM tools | Participants bring their own |
| Help | On site; before the event email the topic owner |

Keep this in sync with `runbook/handout.html`.

### Topic selection and balancing
Expect 40 to 50 participants, so about 14 to 25 teams. Encourage teams of 2 to 3.
- **09:45:** check counts, announce topics with room, help undecided people.
- **10:00:** form closes; rebalance until about 10:15.

**Not enough people for a topic (decide before 12 Nov):**
1. Set a go / no-go rule (recommended: a topic runs with at least 2 teams) and announce it at kick-off.
2. Keep active topics few (about 5); open Project_6 and Project_7 only if ready.
3. Projects 3 and 4 already run as one topic (3-4) for now.
4. Ask before moving anyone; let solo participants join existing teams.
5. A topic with 1 or 2 teams can still run; finalists are chosen across all topics.
6. Closed-topic owners can float as mentors.

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
- A team on two topics names one primary topic; it counts towards that topic's cap of 5 teams and the go / no-go rule, and is reviewed and scored there (the second topic's owner may read along). Team counts below are by primary topic.
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
| Project_3-4 | Project 3: error on total turnaround time (MAE). Project 4: precision / recall / F1 per task. Sensible feature importance for both |
| Project_5 | Score on the hidden test set, kappa and consistency, reusability |

### Bonus and penalties
- **Bonus (up to +5):** exceptional insight or particularly clean engineering.
- **Disqualification:** real Sixt, customer or personal data; committed secrets; training on the hidden test set (Project_5).
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
