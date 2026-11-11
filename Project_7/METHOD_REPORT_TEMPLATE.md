# Problem 7 method report

Copy this file to `Project_7/SUBMISSION.md` in your team's registered repository and submit it by **16:45 CET on 13 November 2026**. Keep it concise and link supporting code and evidence.

**P7 submission finalization also requires an arXiv manuscript upload after coordination with the organizers.** The Hackathon-day report and later coordinated upload are both required. Agree the timing, author list, dataset citation and manuscript content before uploading. The later upload does not reopen locked answers or event results.

Team name:

Team members and contributions:

Public and final submission filenames and SHA-256 hashes:

Code revision used for your calculations (a commit made before this report update):

The organizers record the locked public and final submission commit IDs separately at 14:45 and 16:45 CET on 13 Nov 2026. Do not attempt to embed this report's own final commit hash inside the report.

## 1. Approach in one paragraph

Explain how your workflow turns a business question into a CSV answer. State what the models do, what ordinary code/tools do, and where people intervene.

## 2. Architecture and implementation

Include a simple diagram. List the framework or custom orchestration, relevant code files, dependencies, tools and model configurations. Explain how the workflow selects tables and applies business rules. Provide setup/run instructions for your method evidence; the automatic grader reads the submitted CSVs.

## 3. Validation and results

Describe checks for joins, duplicate counting, record eligibility, dates, exchange rates, rounding and CSV structure. Explain representative errors and fixes. Distinguish your own checks from any official feedback. Do not claim unmeasured accuracy, speed or cost.

## 4. Model use and efficiency

Complete MODEL_DECLARATION.csv for every generative model used in challenge-specific design, coding, analysis, answer generation or validation, including assistants and fallbacks. Record exact revisions, total parameter counts and evidence sources. Explain the substantive role of each model and the accompanying tools.

If measured, report hardware, run time, token usage, memory and cost, with the method used to measure them. Otherwise state “not measured.”

## 5. Small-model bonus declaration

Bonus claimed: yes / no

All generative models within scope have at most 40B total parameters: yes / no

Evidence locations for model sizes, settings and representative usage/run records:

Explain how the qualifying models perform meaningful analysis work. Include both stages and all fallbacks. The organizers verify eligibility; this declaration is not itself approval. Remove API keys, access tokens and other secrets from evidence.

## 6. Limitations and reflection

Which questions or rules were difficult? Where could the method fail? What would you change with more time? Explain the trade-offs behind your design choices.

## 7. References and attribution

Cite the dataset exactly as specified in the released stage package. Include version, archive filename, SHA-256 and access date. A DOI must only be included if one has actually been assigned. Cite external models, frameworks, libraries and reused code.

## Presentation preparation

Submit either `submission/demo.mp4` (1 minute, under 50 MB) or `submission/slides.pdf` (at most 5 slides) inside `Project_7/`. Prepare to demonstrate one question flowing through your system, explain your validation evidence, and discuss your design choices and limitations. If selected as a finalist, give a 3-minute pitch plus 2 minutes of Q&A.

The five human criteria are problem understanding, quality of approach, business relevance and reusability, code quality and reproducibility, and presentation and demo. They contribute 35 points together. Explain a baseline where available and how SIXT could reuse your approach.

## 8. Publication follow-up after the Hackathon

This section may remain pending at the 16:45 deadline. Complete it after coordination; do not delay the Hackathon-day report while preparing the arXiv version.

- Coordination status and organizer contact:
- Agreed manuscript title, author list and contributions:
- Agreed upload timing:
- Manuscript location/version reviewed with the organizers:
- Confirmed dataset citation and other references:
- arXiv upload confirmation and submission date:
- arXiv identifier or public link, when available:

Send the upload confirmation and later arXiv link to the organizers to complete the publication follow-up. Do not include challenge dataset files, golden answers, private evaluation details or organizer materials in the manuscript, its source files or attachments. The coordinated report upload is not permission to release those materials. Use public toy examples for illustrations and discuss any submission difficulty with the organizers.
