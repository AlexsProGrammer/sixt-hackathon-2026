# P7 student arXiv report template

Use [main.tex](main.tex) and [references.bib](references.bib) to write your team's report about **Problem 7: SIXT + TUM Enterprise Data Agent Challenge**. This is a simple, single-column LaTeX `article` starter for student method reports. The dataset's later Data in Brief paper is a separate publication.

## Two required steps

1. **Hackathon day:** submit `Project_7/SUBMISSION.md` and the other deliverables by **16:45 CET on 13 November 2026**, following the [method report template](../METHOD_REPORT_TEMPLATE.md). Do not delay that submission while preparing the manuscript.
2. **After the Hackathon:** adapt the report using this LaTeX starter, coordinate the author list, content, dataset citation and upload timing with the organizers, then upload the manuscript to arXiv to finalize your P7 submission. Send the upload confirmation and arXiv identifier/link when available. The later upload date will be agreed with the organizers. It does not reopen locked CSVs or event results.

Contact: **Ioannis Tzachristas**, [ioannis.tzachristas@tum.de](mailto:ioannis.tzachristas@tum.de). Discuss any submission difficulty with the organizers.

## Fill in the report

- Replace every `[TODO: ...]`, including the title, student authors, actual affiliations and measurements. The template contains prompts, not measured results. Delete instructional text when the report is complete.
- Explain the method, validation, results, efficiency, limitations, reproducibility and business relevance. Use a diagram of your own workflow if helpful.
- Keep the dataset citation in `references.bib`, checking it against the citation in the issued package. The prepared citation is **Ioannis Tzachristas (2026), Enterprise Data Agent Challenge 2026: expanded multi-table question answering, Version 6.0.0, unpublished data set**. No DOI or public dataset URL is asserted. Update only from verified organizer-provided citation metadata; cite any later Data in Brief article separately.
- Record both issued archive filenames, SHA-256 hashes, access dates, dataset versions, event content revisions and policy versions. Use hashes supplied with the actual event packages, rather than a historical archive's hash. Add citations for external models, frameworks and reused code.
- Complete the model-use section and reconcile it with [MODEL_DECLARATION.csv](../MODEL_DECLARATION.csv). Disclose coding assistants, planners, validators and fallbacks, exact revisions, total parameter counts and evidence. State unknown sizes explicitly. Separately disclose any model assistance used only for the later manuscript.
- If claiming the **+15-point bonus**, document compliance with the [P7 small-model policy](../README.md#small-model-bonus-15-points): at most **40B total parameters per generative model** throughout the challenge workflow, including coding assistance. For mixture-of-experts models, count all experts. Quantization does not change the count. Organizers verify eligibility.

## Compile

In Overleaf, create a blank project, upload `main.tex` and `references.bib`, set `main.tex` as the main document and use the **pdfLaTeX** compiler. No data files, custom class or shell escape are needed.

With a local TeX distribution, run these commands from this folder:

```sh
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

Check `main.pdf` and the log for missing references, overflow and remaining TODOs. Use `\nolinkurl{...}` for long hashes, filenames and code revisions; escape special LaTeX characters in ordinary prose, such as `\_`, `\%` and `\&`.

## Prepare the coordinated arXiv upload

After organizer coordination, assemble a **report-only** source folder containing the completed `main.tex`, `references.bib`, the freshly generated `main.bbl` and only any authorized figures that the manuscript uses. If your editor names the generated bibliography `output.bbl`, rename it to `main.bbl` to match `main.tex`. Recompile this clean folder and inspect the PDF. Follow [arXiv's current TeX submission instructions](https://info.arxiv.org/help/submit_tex.html); [Overleaf's export guidance](https://docs.overleaf.com/navigating-in-the-editor/generated-files) explains how to obtain generated bibliography files.

**Do not upload the whole team repository or a Hackathon package.** Keep challenge datasets, answer CSVs, golden answers, private evaluation details, organizer files, credentials and private logs out of the manuscript, TeX comments, source archive and ancillary attachments. Use the public toy examples for illustrations. Dataset citation does not grant permission to redistribute the data. Publication of the report does not authorize release of restricted materials.

Record the upload confirmation and later arXiv link in the publication follow-up section of `SUBMISSION.md`. The [P7 challenge rules](../README.md) remain authoritative for grading and submission requirements.
