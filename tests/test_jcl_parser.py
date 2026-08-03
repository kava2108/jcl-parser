import unittest

import yaml

from jcl_models import DDStatement, ExecStep, JobAST, to_model
from jcl_parser import build_ast, parse_jcl
from jcl_to_gha import to_github_actions


class ParseJclFlatTest(unittest.TestCase):
    def test_parses_job_exec_and_dd(self) -> None:
        lines = [
            "//JOB1     JOB  CLASS=A,MSGCLASS=X\n",
            "//STEP1    EXEC PGM=IEFBR14\n",
            "//DD1      DD   DSN=TEST.FILE,DISP=SHR\n",
            "//* コメント行\n",
            "//STEP2    EXEC PGM=MYPROG,PARM='ABC,DEF'\n",
        ]

        parsed = parse_jcl(lines)

        self.assertEqual(
            parsed,
            [
                {
                    "type": "JOB",
                    "name": "JOB1",
                    "params": {"CLASS": "A", "MSGCLASS": "X"},
                },
                {
                    "type": "EXEC",
                    "name": "STEP1",
                    "params": {"PGM": "IEFBR14"},
                },
                {
                    "type": "DD",
                    "name": "DD1",
                    "params": {"DSN": "TEST.FILE", "DISP": "SHR"},
                },
                {
                    "type": "EXEC",
                    "name": "STEP2",
                    "params": {"PGM": "MYPROG", "PARM": "ABC,DEF"},
                },
            ],
        )


class ParseDdAttributesTest(unittest.TestCase):
    def test_disp_positional_tuple(self) -> None:
        lines = ["//DD2      DD   DSN=NEW.FILE,DISP=(NEW,CATLG,DELETE)\n"]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"]["DISP"], ["NEW", "CATLG", "DELETE"])

    def test_dcb_keyword_subparams(self) -> None:
        lines = ["//DD3      DD   DSN=MY.FILE,DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)\n"]
        parsed = parse_jcl(lines)
        self.assertEqual(
            parsed[0]["params"]["DCB"],
            {"RECFM": "FB", "LRECL": "80", "BLKSIZE": "800"},
        )

    def test_space_nested_group(self) -> None:
        lines = ["//DD4      DD   DSN=MY.FILE,SPACE=(CYL,(10,5),RLSE)\n"]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"]["SPACE"], ["CYL", ["10", "5"], "RLSE"])

    def test_disp_two_element(self) -> None:
        lines = ["//DD5      DD   DSN=MY.FILE,DISP=(SHR,KEEP)\n"]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"]["DISP"], ["SHR", "KEEP"])


class ParseExecParmTest(unittest.TestCase):
    def test_parm_parenthesized_list(self) -> None:
        lines = ["//STEP3    EXEC PGM=MYPROG,PARM=(OPT1,OPT2,OPT3)\n"]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"]["PARM"], ["OPT1", "OPT2", "OPT3"])

    def test_parm_quoted_string_unchanged(self) -> None:
        lines = ["//STEP4    EXEC PGM=MYPROG,PARM='ABC,DEF'\n"]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"]["PARM"], "ABC,DEF")

    def test_parm_simple_value(self) -> None:
        lines = ["//STEP5    EXEC PGM=MYPROG,PARM=SIMPLE\n"]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"]["PARM"], "SIMPLE")


class BuildAstTest(unittest.TestCase):
    def test_ast_hierarchy(self) -> None:
        lines = [
            "//JOB1     JOB  CLASS=A,MSGCLASS=X\n",
            "//STEP1    EXEC PGM=IEFBR14\n",
            "//DD1      DD   DSN=TEST.FILE,DISP=SHR\n",
            "//DD2      DD   DSN=WORK.FILE,DISP=(NEW,DELETE,DELETE)\n",
            "//STEP2    EXEC PGM=MYPROG,PARM=(OPT1,OPT2)\n",
            "//DD3      DD   DSN=OUT.FILE,DISP=(NEW,CATLG)\n",
        ]
        ast = build_ast(parse_jcl(lines))

        self.assertEqual(ast["type"], "JOB")
        self.assertEqual(ast["name"], "JOB1")
        self.assertEqual(ast["params"], {"CLASS": "A", "MSGCLASS": "X"})

        steps = ast["steps"]
        self.assertEqual(len(steps), 2)

        step1 = steps[0]
        self.assertEqual(step1["name"], "STEP1")
        self.assertEqual(step1["params"], {"PGM": "IEFBR14"})
        self.assertEqual(len(step1["dds"]), 2)
        self.assertEqual(step1["dds"][0]["name"], "DD1")
        self.assertEqual(step1["dds"][1]["name"], "DD2")
        self.assertEqual(step1["dds"][1]["params"]["DISP"], ["NEW", "DELETE", "DELETE"])

        step2 = steps[1]
        self.assertEqual(step2["name"], "STEP2")
        self.assertEqual(step2["params"]["PARM"], ["OPT1", "OPT2"])
        self.assertEqual(len(step2["dds"]), 1)
        self.assertEqual(step2["dds"][0]["name"], "DD3")

    def test_ast_no_job_statement(self) -> None:
        lines = [
            "//STEP1    EXEC PGM=IEFBR14\n",
            "//DD1      DD   DSN=TEST.FILE,DISP=SHR\n",
        ]
        ast = build_ast(parse_jcl(lines))
        self.assertIsNone(ast["name"])
        self.assertEqual(len(ast["steps"]), 1)


class ToModelTest(unittest.TestCase):
    def _parse(self, lines):
        return to_model(build_ast(parse_jcl(lines)))

    def test_returns_job_ast(self) -> None:
        lines = [
            "//JOB1     JOB  CLASS=A\n",
            "//STEP1    EXEC PGM=IEFBR14\n",
            "//DD1      DD   DSN=TEST.FILE,DISP=SHR\n",
        ]
        model = self._parse(lines)
        self.assertIsInstance(model, JobAST)
        self.assertEqual(model.name, "JOB1")
        self.assertEqual(model.params["CLASS"], "A")

    def test_steps_are_exec_step(self) -> None:
        lines = [
            "//JOB1     JOB  CLASS=A\n",
            "//STEP1    EXEC PGM=IEFBR14\n",
            "//DD1      DD   DSN=TEST.FILE,DISP=(SHR,KEEP)\n",
        ]
        model = self._parse(lines)
        step = model.steps[0]
        self.assertIsInstance(step, ExecStep)
        self.assertEqual(step.name, "STEP1")
        dd = step.dds[0]
        self.assertIsInstance(dd, DDStatement)
        self.assertEqual(dd.params["DISP"], ["SHR", "KEEP"])

    def test_no_job_statement(self) -> None:
        lines = ["//STEP1    EXEC PGM=IEFBR14\n"]
        model = self._parse(lines)
        self.assertIsNone(model.name)
        self.assertEqual(len(model.steps), 1)


class JsonSchemaTest(unittest.TestCase):
    def test_schema_has_required_structure(self) -> None:
        schema = JobAST.model_json_schema()
        self.assertEqual(schema["title"], "JobAST")
        self.assertIn("steps", schema["properties"])
        defs = schema.get("$defs", {})
        self.assertIn("ExecStep", defs)
        self.assertIn("DDStatement", defs)

    def test_schema_type_literals(self) -> None:
        schema = JobAST.model_json_schema()
        defs = schema["$defs"]
        exec_type = defs["ExecStep"]["properties"]["type"]
        self.assertEqual(exec_type.get("const"), "EXEC")
        dd_type = defs["DDStatement"]["properties"]["type"]
        self.assertEqual(dd_type.get("const"), "DD")


class ToGitHubActionsTest(unittest.TestCase):
    def _convert(self, lines):
        return to_github_actions(to_model(build_ast(parse_jcl(lines))))

    def test_workflow_name(self) -> None:
        lines = ["//JOB1  JOB  CLASS=A\n", "//STEP1 EXEC PGM=MYPROG\n"]
        self.assertIn("name: JOB1", self._convert(lines))

    def test_step_becomes_job(self) -> None:
        lines = ["//JOB1  JOB  CLASS=A\n", "//STEP1 EXEC PGM=MYPROG\n"]
        out = self._convert(lines)
        self.assertIn("STEP1:", out)
        self.assertIn("run: MYPROG", out)

    def test_parm_string_appended(self) -> None:
        lines = ["//JOB1  JOB  CLASS=A\n", "//STEP1 EXEC PGM=MYPROG,PARM='ABC,DEF'\n"]
        self.assertIn("run: MYPROG ABC,DEF", self._convert(lines))

    def test_parm_list_joined_with_space(self) -> None:
        lines = ["//JOB1  JOB  CLASS=A\n", "//STEP1 EXEC PGM=MYPROG,PARM=(A,B,C)\n"]
        self.assertIn("run: MYPROG A B C", self._convert(lines))

    def test_dd_mapped_to_env(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=MYPROG\n",
            "//DD1   DD   DSN=TEST.FILE,DISP=SHR\n",
        ]
        out = self._convert(lines)
        self.assertIn("DD_DD1: data/TEST/FILE", out)
        self.assertIn("DISP=SHR", out)

    def test_disp_tuple_in_comment(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=MYPROG\n",
            "//DD2   DD   DSN=NEW.FILE,DISP=(NEW,CATLG,DELETE)\n",
        ]
        self.assertIn("DISP=(NEW,CATLG,DELETE)", self._convert(lines))

    def test_sequential_steps_have_needs(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//STEP2 EXEC PGM=PROG2\n",
            "//STEP3 EXEC PGM=PROG3\n",
        ]
        out = self._convert(lines)
        self.assertIn("needs: [STEP1]", out)
        self.assertIn("needs: [STEP2]", out)
        # STEP1 should not have needs
        step1_section = out.split("STEP2:")[0]
        self.assertNotIn("needs:", step1_section)

    def test_output_is_valid_yaml(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//DD1   DD   DSN=FILE1,DISP=SHR\n",
            "//STEP2 EXEC PGM=PROG2,PARM=(OPT1,OPT2)\n",
            "//DD2   DD   DSN=FILE2,DISP=(NEW,CATLG,DELETE)\n",
        ]
        parsed = yaml.safe_load(self._convert(lines))
        self.assertEqual(parsed["name"], "JOB1")
        jobs = parsed["jobs"]
        self.assertIn("STEP1", jobs)
        self.assertIn("STEP2", jobs)
        self.assertEqual(jobs["STEP2"]["needs"], ["STEP1"])
        self.assertEqual(jobs["STEP1"]["env"]["DD_DD1"], "data/FILE1")
        self.assertEqual(jobs["STEP2"]["env"]["DD_DD2"], "data/FILE2")

    def test_no_job_statement_uses_default_name(self) -> None:
        lines = ["//STEP1 EXEC PGM=MYPROG\n"]
        self.assertIn("name: JCL_JOB", self._convert(lines))


if __name__ == "__main__":
    unittest.main()
