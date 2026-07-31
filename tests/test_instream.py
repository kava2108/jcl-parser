import unittest

from jcl_models import to_model
from jcl_parser import build_ast, parse_jcl


class InstreamDataTest(unittest.TestCase):
    def test_default_delimiter(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG\n",
            "//SYSIN DD *\n",
            "DATA LINE 1\n",
            "DATA LINE 2\n",
            "/*\n",
            "//STEP2 EXEC PGM=PROG2\n",
        ]
        parsed = parse_jcl(lines)
        sysin = next(s for s in parsed if s.get("name") == "SYSIN")
        self.assertEqual(sysin["instream"], ["DATA LINE 1", "DATA LINE 2"])

        step_names = [s["name"] for s in parsed if s["type"] == "EXEC"]
        self.assertEqual(step_names, ["STEP1", "STEP2"])

    def test_dd_data_keyword_treated_as_instream(self) -> None:
        lines = [
            "//SYSIN DD DATA\n",
            "some data\n",
            "/*\n",
        ]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["instream"], ["some data"])

    def test_custom_delimiter(self) -> None:
        lines = [
            "//SYSIN DD *,DLM=ZZ\n",
            "line with /* inside it\n",
            "ZZ\n",
        ]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["instream"], ["line with /* inside it"])

    def test_instream_dd_survives_model_validation(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG\n",
            "//SYSIN DD *\n",
            "DATA LINE 1\n",
            "/*\n",
        ]
        model = to_model(build_ast(parse_jcl(lines)))
        dd = model.steps[0].dds[0]
        self.assertEqual(dd.instream, ["DATA LINE 1"])


if __name__ == "__main__":
    unittest.main()
