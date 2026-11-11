import contextlib
import io
import unittest

import dio


class AggregateTest(unittest.TestCase):
    def test_noul_returns_bool_with_sample_share_as_confidence(self):
        questions = {"hostile": dio.noul("Hostile?")}
        samples = [{"hostile": "true"}] * 3 + [{"hostile": "false"}]
        a = dio.aggregate(questions, samples)["hostile"]
        self.assertIs(a.answer, True)
        self.assertEqual(a.confidence, 0.75)
        self.assertEqual(a.distribution, {"true": 0.75, "false": 0.25})
        self.assertIsNone(a.score)

    def test_choice_includes_unpicked_options_at_zero(self):
        questions = {"move": dio.choice("Move?", ["attack", "flee", "hide"])}
        a = dio.aggregate(questions, [{"move": "flee"}, {"move": "flee"}])["move"]
        self.assertEqual(a.answer, "flee")
        self.assertEqual(a.distribution, {"attack": 0.0, "flee": 1.0, "hide": 0.0})

    def test_score_is_expected_level_from_zero_to_one(self):
        questions = {"danger": dio.score("Danger?", ["none", "low", "high"])}
        a = dio.aggregate(questions, [{"danger": "low"}, {"danger": "high"}])["danger"]
        self.assertEqual(a.score, 0.75)  # (1/2 * 0.5 + 1 * 0.5)

    def test_tie_goes_to_earlier_option(self):
        questions = {"move": dio.choice("Move?", ["attack", "flee"])}
        a = dio.aggregate(questions, [{"move": "flee"}, {"move": "attack"}])["move"]
        self.assertEqual(a.answer, "attack")

    def test_no_samples_raises(self):
        with self.assertRaises(dio.DioError):
            dio.aggregate({"hostile": dio.noul("Hostile?")}, [])


class QuestionTest(unittest.TestCase):
    def test_rejects_too_few_or_duplicate_options(self):
        with self.assertRaises(ValueError):
            dio.choice("Move?", ["attack"])
        with self.assertRaises(ValueError):
            dio.score("Danger?", ["low", "low"])

    def test_schema_restricts_each_answer_to_its_options(self):
        schema = dio.answer_schema({"hostile": dio.noul("Hostile?"), "move": dio.choice("Move?", ["a", "b"])})
        self.assertEqual(schema["required"], ["hostile", "move"])
        self.assertEqual(schema["properties"]["move"], {"type": "string", "enum": ["a", "b"]})
        self.assertFalse(schema["additionalProperties"])


class CommandLineTest(unittest.TestCase):
    def parse(self, *argv):
        parser = dio.build_parser()
        return dio.parse_questions(parser, parser.parse_args(argv).questions)

    def test_questions_keep_the_order_given(self):
        questions = self.parse(
            "--score",
            "danger",
            "Danger?",
            "low, high",
            "--noul",
            "hostile",
            "Hostile?",
            "--choice",
            "move",
            "Move?",
            "attack,flee",
        )
        self.assertEqual(list(questions), ["danger", "hostile", "move"])
        self.assertEqual(questions["danger"], dio.Question("score", "Danger?", ("low", "high")))
        self.assertEqual(questions["move"].options, ("attack", "flee"))

    def test_rejects_missing_duplicate_or_bad_questions(self):
        for argv in [(), ("--noul", "k", "A?", "--noul", "k", "B?"), ("--choice", "k", "A?", "only")]:
            with self.subTest(argv=argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.parse(*argv)


if __name__ == "__main__":
    unittest.main()
