# Our recipe for building an LLM judge

Fill this in as you go. It is what you hand in, next to your code: a repeatable recipe someone else could follow
for a criterion they have never seen. Keep each step short. Numbers come from `score.py`.

## Step 1. Diagnose
What did you look at, and where does the baseline fail? (edit types, languages, a few example misses)

- Check before moving on: you can name the 2-3 failure types that cost the most.

## Step 2. Split: rules vs. LLM
Which parts of the criterion can plain code check (numbers, policy facts)? What still needs the LLM?

- Check: each rule is tested on dev and never fails a harmless edit.

## Step 3. Improve the LLM part
What did you change (instructions, examples, sub-questions, voting, per-language prompts, model)? Why?

- Check: catch goes up on dev without keep going down.

## Step 4. Verify
Before and after, on the full dev set and per language.

| | combined | catch | keep |
|---|---|---|---|
| Baseline | | | |
| Ours | | | |

- Check: the gain holds on edit types and phrasings you did not tune on.

## Surprise criterion
What did you change for the new criterion? (Only inputs may change: the criterion text and the examples.)

| | combined | catch | keep |
|---|---|---|---|
| Baseline | | | |
| Ours, recipe unchanged | | | |

## What did not work
