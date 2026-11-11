"""Dio (discriminative input-output): typed, probabilistic judgments from Claude.

Dio uses Claude as a discriminative model. You pass a state and typed questions,
and get back one answer per question with a probability distribution over its
options. Each run samples headless Claude Code (`claude -p`) several times in
parallel, under a JSON schema that admits only each question's options. The
distribution is the share of samples that picked each option. Calls run on your
Claude subscription login, so no API key is needed.
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass

SYSTEM_PROMPT = (
    "You answer questions about a state. Judge only from the state given. "
    "For each question, pick the single option that fits best."
)


class DioError(Exception):
    pass


@dataclass(frozen=True)
class Question:
    kind: str  # "noul", "choice" or "score"
    text: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    answer: bool | str  # bool for noul questions, the chosen option otherwise
    confidence: float  # probability of the chosen answer
    distribution: dict[str, float]
    score: float | None = None  # score questions only: expected level, 0 (lowest) to 1 (highest)


def noul(text: str) -> Question:
    """A true/false question."""
    return Question("noul", text, ("true", "false"))


def choice(text: str, options: list[str]) -> Question:
    """A question whose answer is one of several unordered options."""
    return _checked(Question("choice", text, tuple(options)))


def score(text: str, levels: list[str]) -> Question:
    """A question answered on an ordered scale; list levels from lowest to highest."""
    return _checked(Question("score", text, tuple(levels)))


def _checked(question: Question) -> Question:
    if len(question.options) < 2 or len(set(question.options)) != len(question.options):
        raise ValueError(f"{question.text!r} needs at least two distinct options")
    return question


def build_prompt(state: str, questions: dict[str, Question]) -> str:
    lines = [f"<state>\n{state}\n</state>", "", "Questions:"]
    lines += [f"- {key}: {q.text} Options: {', '.join(q.options)}" for key, q in questions.items()]
    return "\n".join(lines)


def answer_schema(questions: dict[str, Question]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(questions),
        "properties": {key: {"type": "string", "enum": list(q.options)} for key, q in questions.items()},
    }


def aggregate(questions: dict[str, Question], samples: list[dict[str, str]]) -> dict[str, Answer]:
    """Turn sampled answers into one Answer per question."""
    if not samples:
        raise DioError("every sample failed; no answers to aggregate")
    answers = {}
    for key, q in questions.items():
        counts = Counter(sample[key] for sample in samples)
        distribution = {option: counts[option] / len(samples) for option in q.options}
        top = max(q.options, key=distribution.__getitem__)  # ties go to the earlier option
        answers[key] = Answer(
            answer=(top == "true") if q.kind == "noul" else top,
            confidence=distribution[top],
            distribution=distribution,
            score=(
                sum(i * p for i, p in enumerate(distribution.values())) / (len(q.options) - 1)
                if q.kind == "score"
                else None
            ),
        )
    return answers


async def _sample(claude: str, prompt: str, schema: dict, model: str) -> dict[str, str] | None:
    """One headless Claude Code judgment, or None if the run gave no structured output."""
    # Formatter off so each flag stays on one line with its value.
    # fmt: off
    proc = await asyncio.create_subprocess_exec(
        claude, "-p",
        "--model", model,
        "--effort", "low",
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    # fmt: on
    out, _ = await proc.communicate(prompt.encode())  # stdin avoids Windows' command-line length limit
    try:
        return json.loads(out).get("structured_output")
    except json.JSONDecodeError:
        return None


async def ask(state: str, questions: dict[str, Question], samples: int, model: str) -> dict[str, Answer]:
    claude = shutil.which("claude")
    if claude is None:
        raise DioError("the claude CLI is not on PATH")
    prompt, schema = build_prompt(state, questions), answer_schema(questions)
    results = await asyncio.gather(*(_sample(claude, prompt, schema, model) for _ in range(samples)))
    return aggregate(questions, [r for r in results if r is not None])


class _AddQuestion(argparse.Action):
    """Collects --noul/--choice/--score into one ordered list, so answers keep the order given."""

    def __call__(self, parser, namespace, values, option_string=None):
        namespace.questions.append((self.dest, values))


def parse_questions(parser: argparse.ArgumentParser, specs: list[tuple[str, list[str]]]) -> dict[str, Question]:
    if not specs:
        parser.error("ask at least one question with --noul, --choice or --score")
    questions = {}
    for kind, (key, text, *options) in specs:
        if key in questions:
            parser.error(f"question key {key!r} is used twice")
        try:
            if kind == "noul":
                questions[key] = noul(text)
            else:
                values = [o.strip() for o in options[0].split(",")]
                questions[key] = choice(text, values) if kind == "choice" else score(text, values)
        except ValueError as e:
            parser.error(str(e))
    return questions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dio",
        description="Ask Claude typed questions about a state. Prints one answer per question, "
        "with a probability distribution, as JSON.",
        epilog='example: dio --state "HP 12/100, imp firing" --noul hostile "Is the enemy hostile?" '
        '--choice move "Best next move?" attack,flee,hide',
    )
    parser.set_defaults(questions=[])
    parser.add_argument("--state", help="the state to judge; read from stdin when omitted")
    parser.add_argument("--noul", nargs=2, metavar=("KEY", "TEXT"), action=_AddQuestion, help="a true/false question")
    parser.add_argument(
        "--choice",
        nargs=3,
        metavar=("KEY", "TEXT", "OPTIONS"),
        action=_AddQuestion,
        help="pick one of comma-separated OPTIONS",
    )
    parser.add_argument(
        "--score",
        nargs=3,
        metavar=("KEY", "TEXT", "LEVELS"),
        action=_AddQuestion,
        help="rate on comma-separated LEVELS, lowest first",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="parallel Claude calls per run; probabilities come in steps of 1/SAMPLES (default 5)",
    )
    parser.add_argument("--model", default="haiku", help="model alias or name for claude --model (default haiku)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    questions = parse_questions(parser, args.questions)
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    if args.state is not None:
        state = args.state
    elif not sys.stdin.isatty():
        state = sys.stdin.read()
    else:
        state = ""
    if not state.strip():
        parser.error("give the state with --state or pipe it on stdin")
    try:
        answers = asyncio.run(ask(state, questions, args.samples, args.model))
    except DioError as e:
        sys.exit(f"dio: {e}")
    json.dump({key: asdict(a) for key, a in answers.items()}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
