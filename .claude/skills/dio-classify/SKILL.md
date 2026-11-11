---
name: dio-classify
description: Get typed answers from Claude (true/false, pick-one, or ordered-scale) with a probability distribution for each question about a state, using the Dio command-line tool. Use it whenever a discriminative model would help, meaning a question with a fixed set of possible answers rather than open text. That includes classifying, labeling, routing, triaging, scoring, rating, ranking against a scale, yes/no checks, verification, guardrails, deciding which branch to take, and needing a confidence or probability for a judgment.
when_to_use: Also load it when building a script, workflow, or program that has to make such a decision, or when judging many items the same way. Not for free-text answers, summaries, explanations, or generation, and not for changing Dio's own code.
user-invocable: false
---

# Classifying with Dio

## When Dio fits

Reach for Dio when a judgment has a fixed set of possible answers, and any of these hold:

- The user wants a confidence, a probability, or a sense of how clear-cut the call is.
- The same judgment has to be made consistently over many items, such as log lines, records, or files.
- A script or program needs the decision as data. Have it call `dio` and parse the JSON, instead of prompting Claude and parsing free text.
- The answer gates an action, such as a guardrail, a triage step, or a branch. A typed answer with a confidence is safer to act on than prose.

Answer directly yourself when one quick judgment needs no confidence, because a Dio run takes about 13 seconds. Don't use Dio when the answer is open-ended: Dio only picks among the options you give it.

Dio prints JSON. Report the answer together with its `confidence`. Don't restate the whole distribution unless the user asks for it.

## Run it

Dio must be installed as the `dio` command; this skill doesn't include it. If `dio` isn't found, tell the user that Dio needs to be installed and that its README has the steps, then answer the question directly. Don't give a number for your confidence, because without Dio there's nothing measured behind it. Don't install it yourself.

```sh
dio --state "<state>" \
    --noul KEY "Question?" \
    --choice KEY "Question?" opt1,opt2,opt3 \
    --score KEY "Question?" lowest,...,highest
```

- Pipe large or file-based states on stdin instead of passing `--state`: `cat state.json | dio --choice ...`. Long `--state` arguments run into the Windows command-line length limit.
- Give each question a short snake_case key. Answers come back as `{"KEY": {"answer", "confidence", "distribution", "score"}}`, in the order you asked.
- `--noul` answers are JSON booleans. `--score` answers also carry `score`, the expected level from 0 (lowest) to 1 (highest). Use it when the user wants a number.
- Batch independent questions about the same state into one run. Every run costs about 13 seconds and several subscription calls, however many questions it carries. When judging many items, run them as separate states in parallel rather than one after another.
- Keep the default `--samples 5`. Raise it, for example to 10, only when the user needs finer probabilities. Lower it to 1 when only the answer matters.

## Write good questions

- Write options the state can actually decide between. Make them mutually exclusive and phrase them the way the state does.
- List `--score` levels from lowest to highest. `score` is computed from that order, so reversing it inverts the number.
- Phrase a `--noul` question so that `true` means the thing being checked for.

## Gotchas

- Options are split on commas, so an option can't contain one. Rephrase it, for example `"low or none"` instead of `"low, none"`.
- A question can't depend on another question's answer, because all questions go into one call. Run Dio twice and put the first answer into the second run's state.
- `confidence` is the share of samples that agreed, not a calibrated probability. Every sample often agrees on clear questions, so a 1.0 means "unanimous", not "certain". Say so if the user is about to act on it.
- The state is all Dio sees. It has no tools and doesn't read files or the conversation, so put everything the judgment needs into the state.
- Exit code 2 means a bad invocation: no questions, no state, a duplicate key, or fewer than two options. Read the stderr message and fix the command. Exit code 1 means the `claude` CLI is missing or every sample failed. Report this to the user rather than retrying in a loop.
