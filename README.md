# Dio

Dio (discriminative input-output) is a command-line tool that uses Claude as a discriminative model. You give it a state and some typed questions. For each question it prints an answer, a confidence, and a probability distribution over the allowed options, as JSON. It never returns free text.

Dio runs headless Claude Code (`claude -p`) under your Claude subscription login, so you don't need an API key.

Dio doesn't provide access to Claude. It runs your own Claude Code install, signed in to your own account, and every sample counts against that account's usage limits. Your use of Claude through Dio is covered by the terms of your Claude plan.

This repository also includes a Claude Code skill, `dio-classify`, that teaches Claude when and how to use Dio.

## Install

You need:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- The [Claude Code](https://code.claude.com) CLI on your `PATH`, signed in to your Claude subscription (run `claude` once and log in)

uv provides Python 3.10 or later if you don't already have it.

From this folder, run:

```sh
uv tool install .
uv tool update-shell
```

The first command installs the `dio` command, in an environment of its own. Both the command line and the `dio-classify` skill need it. The second command adds uv's tool folder to your `PATH`. You only need to run it once per machine, and then open a new terminal. Check that `dio` works:

```sh
dio --help
```

`uv tool install` copies Dio as it is now. After you change `dio.py` or pull a new version, run `uv tool install --reinstall .` to update it. To remove Dio, run `uv tool uninstall dio`.

If you'd rather use pip, `pip install .` also installs `dio`. If your shell then reports `dio: command not found`, add Python's scripts folder to your `PATH`. `python -c "import sysconfig; print(sysconfig.get_path('scripts'))"` prints where it is.

## Use it from the command line

### Ask questions

Pass the state with `--state`, or pipe it on stdin. Add one flag per question. Each question needs a key, which names it in the output:

| Flag | Question type | `answer` value |
|---|---|---|
| `--noul KEY TEXT` | True/false | `true` or `false` |
| `--choice KEY TEXT OPTIONS` | Pick one of several options | one of the comma-separated `OPTIONS` |
| `--score KEY TEXT LEVELS` | Ordered scale | one of the comma-separated `LEVELS`, listed from lowest to highest |

`--choice` and `--score` need at least two distinct options. You can repeat any flag. Answers come back in the order you asked.

```sh
dio --state "Player HP 12/100, no ammo. Imp 3 tiles east, firing." \
    --noul hostile "Is the nearest enemy hostile?" \
    --choice move "Best next move?" attack,flee,hide \
    --score danger "How dangerous is this?" none,low,medium,high
```

```json
{
  "hostile": {"answer": true, "confidence": 1.0, "distribution": {"true": 1.0, "false": 0.0}, "score": null},
  "move": {"answer": "hide", "confidence": 0.6, "distribution": {"attack": 0.0, "flee": 0.4, "hide": 0.6}, "score": null},
  "danger": {"answer": "high", "confidence": 1.0, "distribution": {"none": 0.0, "low": 0.0, "medium": 0.0, "high": 1.0}, "score": 1.0}
}
```

The real output is indented over several lines.

- `answer`: the most likely option. If options tie, the one listed first wins.
- `confidence`: the probability of `answer`.
- `distribution`: the probability of every option.
- `score`: for `--score` questions, the expected level, from 0 (lowest) to 1 (highest). `null` for other question types.

The state can be any text: a description, JSON, or log lines. To judge a file, pipe it in:

```sh
cat game_state.json | dio --choice move "Best next move?" attack,flee,hide
```

To use an answer in a script, pull it out with [jq](https://jqlang.org/):

```sh
move=$(cat game_state.json | dio --choice move "Best next move?" attack,flee,hide | jq -r .move.answer)
```

### Options

| Option | Default | Effect |
|---|---|---|
| `--samples N` | `5` | How many parallel Claude calls to make. Probabilities come in steps of 1/N. More samples give finer probabilities, but cost more subscription usage and take as long as the slowest call. |
| `--model MODEL` | `haiku` | Any model alias or full name that `claude --model` accepts. |

`dio --help` lists every flag.

If the input is wrong (no questions, no state, a key used twice, or too few options), Dio prints an error and exits with code 2. If the `claude` CLI isn't found or every sample fails, it exits with code 1.

## Use it from Claude Code

Install Dio first (see [Install](#install)), so that `dio` is on your `PATH`. The skill calls that command and doesn't include its own copy.

The `dio-classify` skill lives in `.claude/skills/dio-classify/`. Claude Code loads it automatically in this project. To use it in every project, copy the `dio-classify` folder to `~/.claude/skills/`.

You don't need to mention Dio. Claude loads the skill whenever a question has a fixed set of possible answers, for example:

- classifying, labeling, triaging, or routing items
- scoring or rating something on a scale
- yes/no checks, verification, and guardrails
- any judgment where you want a confidence

It also loads when Claude writes a script or workflow that has to make such a decision. Claude answers free-text requests, such as summaries or explanations, without Dio. If `dio` isn't installed, Claude says so and answers without a confidence.

## How it works

Each sample is a separate `claude -p` run with tools, settings, MCP servers, and slash commands turned off, so your `CLAUDE.md` and project config don't affect the answers. Every run gets the same prompt and a JSON schema that allows only each question's options, so the answers always have the right type. The distribution is the share of samples that picked each option.

All questions in one run go into one call, so a question can't depend on another question's answer. If you need that, run Dio twice.

## Limitations

- **Speed:** each sample starts a full Claude Code process. A run takes several seconds: about 13 seconds for 3 or 5 samples in testing.
- **Uncalibrated probabilities:** a confidence of 1.0 means every sample agreed, not that the answer is certain. Claude's samples rarely disagree on clear questions, so the distribution is most informative on ambiguous ones. To calibrate it, compare Dio's confidence with real accuracy on examples you've labeled yourself.
- **Usage limits:** every sample counts against your subscription's limits.
- **Commas:** options are split on commas, so an option can't contain one.

## Project layout

```
dio.py                              # Dio itself
pyproject.toml                      # builds the dio command; Ruff and dev dependency settings
uv.lock                             # exact dev dependency versions
test_dio.py                         # unit tests
.claude/skills/dio-classify/
└── SKILL.md                        # the dio-classify skill: when and how Claude uses Dio
```

## Develop

uv manages a development environment in `.venv/`, with Dio installed in editable mode and [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. The first `uv run` creates it. `uv.lock` pins the exact versions, so commit it.

To try your changes without reinstalling, run:

```sh
uv run dio --help
```

Run the tests:

```sh
uv run python -m unittest
```

The tests cover aggregation, schemas, and parsing of the command line. They don't call Claude.

Lint and format the code:

```sh
uv run ruff check
uv run ruff format
```

Ruff's settings live in `pyproject.toml`, under `[tool.ruff]`. `ruff format` leaves the block of `claude` flags in `dio.py` alone, because it's marked `# fmt: off`. That keeps each flag on one line with its value.
