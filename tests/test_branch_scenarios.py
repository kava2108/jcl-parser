import unittest

from jcl_branch import DEFAULT_MAX_SCENARIOS, build_scenarios
from jcl_parser import parse_jcl


def _exec_names(scenario):
    return [s["name"] for s in scenario.statements if s["type"] == "EXEC"]


class NoBranchTest(unittest.TestCase):
    def test_no_if_yields_single_default_scenario(self) -> None:
        lines = [
            "//JOB1 JOB  CLASS=A\n",
            "//S1   EXEC PGM=P1\n",
            "//S2   EXEC PGM=P2\n",
        ]
        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(warnings, [])
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0].label, "default")
        self.assertEqual(_exec_names(scenarios[0]), ["S1", "S2"])


class SimpleIfElseTest(unittest.TestCase):
    def test_then_and_else_are_mutually_exclusive_scenarios(self) -> None:
        lines = [
            "//JOB1 JOB  CLASS=A\n",
            "//S1   EXEC PGM=P1\n",
            "// IF (S1.RC = 0) THEN\n",
            "//S2   EXEC PGM=P2\n",
            "// ELSE\n",
            "//S3   EXEC PGM=P3\n",
            "// ENDIF\n",
            "//S4   EXEC PGM=P4\n",
        ]
        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(warnings, [])
        self.assertEqual(len(scenarios), 2)

        by_label = {s.label: _exec_names(s) for s in scenarios}
        self.assertEqual(by_label["(S1.RC = 0):THEN"], ["S1", "S2", "S4"])
        self.assertEqual(by_label["(S1.RC = 0):ELSE"], ["S1", "S3", "S4"])


class IfWithoutElseTest(unittest.TestCase):
    def test_missing_else_branch_is_empty_but_present(self) -> None:
        lines = [
            "//JOB1 JOB  CLASS=A\n",
            "// IF (A) THEN\n",
            "//S1   EXEC PGM=P1\n",
            "// ENDIF\n",
            "//S2   EXEC PGM=P2\n",
        ]
        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(warnings, [])
        self.assertEqual(len(scenarios), 2)

        by_label = {s.label: _exec_names(s) for s in scenarios}
        self.assertEqual(by_label["(A):THEN"], ["S1", "S2"])
        self.assertEqual(by_label["(A):ELSE"], ["S2"])


class NestedIfTest(unittest.TestCase):
    def test_nested_if_multiplies_scenarios(self) -> None:
        lines = [
            "//JOB1 JOB  CLASS=A\n",
            "// IF (A) THEN\n",
            "// IF (B) THEN\n",
            "//S1   EXEC PGM=P1\n",
            "// ELSE\n",
            "//S2   EXEC PGM=P2\n",
            "// ENDIF\n",
            "// ELSE\n",
            "// IF (C) THEN\n",
            "//S3   EXEC PGM=P3\n",
            "// ELSE\n",
            "//S4   EXEC PGM=P4\n",
            "// ENDIF\n",
            "// ENDIF\n",
        ]
        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(warnings, [])
        self.assertEqual(len(scenarios), 4)

        all_execs = sorted(name for s in scenarios for name in _exec_names(s))
        self.assertEqual(all_execs, ["S1", "S2", "S3", "S4"])
        # every scenario should be a distinct single-step path
        for scenario in scenarios:
            self.assertEqual(len(_exec_names(scenario)), 1)


class CondImplicitBranchTest(unittest.TestCase):
    def test_cond_step_splits_into_skip_and_run_scenarios(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//S1    EXEC PGM=P1\n",
            "//S2    EXEC PGM=P2,COND=(4,LT)\n",
            "//DD1   DD   DSN=A.FILE,DISP=SHR\n",
            "//S3    EXEC PGM=P3\n",
        ]
        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(warnings, [])
        self.assertEqual(len(scenarios), 2)

        by_label = {s.label: _exec_names(s) for s in scenarios}
        self.assertEqual(by_label["COND=(4,LT):SKIP"], ["S1", "S3"])
        self.assertEqual(by_label["COND=(4,LT):RUN"], ["S1", "S2", "S3"])

        run_scenario = next(s for s in scenarios if s.label == "COND=(4,LT):RUN")
        dd_names = [s["name"] for s in run_scenario.statements if s["type"] == "DD"]
        self.assertEqual(dd_names, ["DD1"])

    def test_cond_even_and_only_are_not_branched(self) -> None:
        for keyword in ("EVEN", "ONLY"):
            with self.subTest(keyword=keyword):
                lines = [
                    "//JOB1  JOB  CLASS=A\n",
                    "//S1    EXEC PGM=P1\n",
                    f"//S2    EXEC PGM=P2,COND={keyword}\n",
                ]
                scenarios, warnings = build_scenarios(parse_jcl(lines))
                self.assertEqual(warnings, [])
                self.assertEqual(len(scenarios), 1)
                self.assertEqual(scenarios[0].label, "default")
                self.assertEqual(_exec_names(scenarios[0]), ["S1", "S2"])

    def test_multiple_cond_steps_combine_with_explicit_if(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//S1    EXEC PGM=P1,COND=(4,LT)\n",
            "// IF (A) THEN\n",
            "//S2    EXEC PGM=P2\n",
            "// ENDIF\n",
        ]
        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(warnings, [])
        # COND(S1) x IF(A) = 2 x 2 = 4 scenarios
        self.assertEqual(len(scenarios), 4)


class CondScenarioCapTest(unittest.TestCase):
    def test_too_many_cond_steps_falls_back_with_warning(self) -> None:
        lines = ["//JOB1  JOB  CLASS=A\n"]
        # 2**7 = 128 > DEFAULT_MAX_SCENARIOS(64): should trigger the fallback
        for i in range(7):
            lines.append(f"//S{i}    EXEC PGM=P{i},COND=(4,LT)\n")

        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(len(warnings), 1)
        self.assertIn("COND-based branching disabled", warnings[0])
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0].label, "default")
        self.assertEqual(len(_exec_names(scenarios[0])), 7)

    def test_explicit_if_unaffected_by_cond_cap(self) -> None:
        lines = ["//JOB1  JOB  CLASS=A\n"]
        for i in range(7):
            lines.append(f"//S{i}    EXEC PGM=P{i},COND=(4,LT)\n")
        lines += [
            "// IF (A) THEN\n",
            "//RUN1  EXEC PGM=RUNNER\n",
            "// ELSE\n",
            "//RUN2  EXEC PGM=RUNNER2\n",
            "// ENDIF\n",
        ]
        scenarios, warnings = build_scenarios(parse_jcl(lines))
        self.assertEqual(len(warnings), 1)
        # explicit IF still produces its 2 branches even though COND got disabled
        self.assertEqual(len(scenarios), 2)
        labels = {s.label for s in scenarios}
        self.assertEqual(labels, {"(A):THEN", "(A):ELSE"})

    def test_default_cap_constant_is_reasonable(self) -> None:
        self.assertGreaterEqual(DEFAULT_MAX_SCENARIOS, 8)


if __name__ == "__main__":
    unittest.main()
