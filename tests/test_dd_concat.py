import unittest

from jcl_models import to_model
from jcl_parser import build_ast, parse_jcl


class DdConcatenationTest(unittest.TestCase):
    def test_anonymous_dd_is_captured(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG\n",
            "//DD1   DD   DSN=FIRST,DISP=SHR\n",
            "//         DD   DSN=SECOND,DISP=SHR\n",
        ]
        parsed = parse_jcl(lines)
        dd_statements = [s for s in parsed if s["type"] == "DD"]

        self.assertEqual(len(dd_statements), 2)
        self.assertEqual(dd_statements[0]["name"], "DD1")
        self.assertNotIn("concatenated", dd_statements[0])

        self.assertIsNone(dd_statements[1]["name"])
        self.assertTrue(dd_statements[1]["concatenated"])
        self.assertEqual(dd_statements[1]["params"]["DSN"], "SECOND")

    def test_concatenated_dd_kept_under_same_step(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG\n",
            "//DD1   DD   DSN=FIRST,DISP=SHR\n",
            "//         DD   DSN=SECOND,DISP=SHR\n",
            "//STEP2 EXEC PGM=PROG2\n",
        ]
        ast = build_ast(parse_jcl(lines))
        step1 = ast["steps"][0]
        self.assertEqual(len(step1["dds"]), 2)
        self.assertEqual(step1["dds"][0]["name"], "DD1")
        self.assertIsNone(step1["dds"][1]["name"])

    def test_pydantic_model_accepts_anonymous_dd(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG\n",
            "//DD1   DD   DSN=FIRST,DISP=SHR\n",
            "//         DD   DSN=SECOND,DISP=SHR\n",
        ]
        model = to_model(build_ast(parse_jcl(lines)))
        dd = model.steps[0].dds[1]
        self.assertIsNone(dd.name)
        self.assertTrue(dd.concatenated)


if __name__ == "__main__":
    unittest.main()
