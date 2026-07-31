import unittest

from jcl_branch import build_scenarios
from jcl_disp_check import check_disp_conflicts
from jcl_dsn import build_dsn_graph, collect_dsn_usages
from jcl_models import to_model
from jcl_parser import build_ast, parse_jcl


def _usages(lines):
    model = to_model(build_ast(parse_jcl(lines)))
    return collect_dsn_usages(model)


def _usages_with_scenarios(lines):
    statements = parse_jcl(lines)
    scenarios, _ = build_scenarios(statements)
    usages = []
    for scenario in scenarios:
        model = to_model(build_ast(scenario.statements))
        usages.extend(collect_dsn_usages(model, scenario=scenario.label))
    return usages


class DuplicateNewTest(unittest.TestCase):
    def test_r1_duplicate_new_flagged(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
            "//STEP2 EXEC PGM=P2\n",
            "//DD2   DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "error")
        self.assertIn("STEP2", conflicts[0].reason)


class ReadBeforeCreateTest(unittest.TestCase):
    def test_r2_first_reference_without_prior_new(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=Y.FILE,DISP=OLD\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "info")
        self.assertIn("STEP1", conflicts[0].reason)

    def test_r2_not_flagged_when_created_first(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=W.FILE,DISP=(NEW,CATLG)\n",
            "//STEP2 EXEC PGM=P2\n",
            "//DD2   DD   DSN=W.FILE,DISP=SHR\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual(conflicts, [])


class UseAfterDeleteTest(unittest.TestCase):
    def test_r3_reference_after_delete(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=Z.FILE,DISP=(NEW,DELETE)\n",
            "//STEP2 EXEC PGM=P2\n",
            "//DD2   DD   DSN=Z.FILE,DISP=SHR\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "error")
        self.assertIn("STEP2", conflicts[0].reason)
        self.assertIn("deleted", conflicts[0].reason)


class PassNeverReclaimedTest(unittest.TestCase):
    def test_r5_pass_with_no_later_claim_flagged(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=TEMP.FILE,DISP=(NEW,PASS)\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "warning")
        self.assertIn("STEP1", conflicts[0].reason)
        self.assertIn("PASS", conflicts[0].reason)

    def test_r5_not_flagged_when_later_step_claims_it(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=TEMP.FILE,DISP=(NEW,PASS)\n",
            "//STEP2 EXEC PGM=P2\n",
            "//DD2   DD   DSN=TEMP.FILE,DISP=(OLD,DELETE)\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual(conflicts, [])


class CrossJobEnqTest(unittest.TestCase):
    def test_r4_two_jobs_hold_exclusive_disp(self) -> None:
        job_a = _usages(
            [
                "//JOBA   JOB  CLASS=A\n",
                "//STEP1  EXEC PGM=P1\n",
                "//DD1    DD   DSN=SHARED.FILE,DISP=OLD\n",
            ]
        )
        job_b = _usages(
            [
                "//JOBB   JOB  CLASS=A\n",
                "//STEP1  EXEC PGM=P2\n",
                "//DD1    DD   DSN=SHARED.FILE,DISP=(NEW,CATLG)\n",
            ]
        )
        graph = build_dsn_graph(job_a + job_b)
        conflicts = check_disp_conflicts(graph)

        warnings = [c for c in conflicts if c.severity == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("JOBA", warnings[0].reason)
        self.assertIn("JOBB", warnings[0].reason)

    def test_no_cross_job_warning_for_single_job(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=SOLO.FILE,DISP=(NEW,CATLG)\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual([c for c in conflicts if c.severity == "warning"], [])


class CleanJobTest(unittest.TestCase):
    def test_well_formed_job_has_no_conflicts(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//OUT   DD   DSN=CLEAN.FILE,DISP=(NEW,CATLG)\n",
            "//STEP2 EXEC PGM=P2\n",
            "//IN    DD   DSN=CLEAN.FILE,DISP=SHR\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages(lines)))
        self.assertEqual(conflicts, [])


class BranchAwareConflictTest(unittest.TestCase):
    def test_duplicate_new_across_mutually_exclusive_branches_is_not_flagged(self) -> None:
        lines = [
            "//JOB1   JOB  CLASS=A\n",
            "// IF (S1.RC = 0) THEN\n",
            "//STEPA  EXEC PGM=PA\n",
            "//DD1    DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
            "// ELSE\n",
            "//STEPB  EXEC PGM=PB\n",
            "//DD2    DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
            "// ENDIF\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages_with_scenarios(lines)))
        self.assertEqual(conflicts, [])

    def test_duplicate_new_within_same_branch_is_still_flagged(self) -> None:
        lines = [
            "//JOB1   JOB  CLASS=A\n",
            "// IF (S1.RC = 0) THEN\n",
            "//STEPA  EXEC PGM=PA\n",
            "//DD1    DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
            "//STEPB  EXEC PGM=PB\n",
            "//DD2    DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
            "// ELSE\n",
            "//STEPC  EXEC PGM=PC\n",
            "// ENDIF\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages_with_scenarios(lines)))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "error")
        self.assertIn("STEPB", conflicts[0].reason)

    def test_pass_precision_improves_when_claiming_step_is_cond_guarded(self) -> None:
        # STEP1 passes X.FILE forward. STEP2 (guarded by COND) is the only step
        # that claims it. Before COND-branching, STEP2 always appeared to claim
        # it, hiding the real risk that STEP2 might be skipped. Now the SKIP
        # scenario correctly shows nothing claims it (R5 fires there), while the
        # RUN scenario shows it being claimed (no R5 there).
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=X.FILE,DISP=(NEW,PASS)\n",
            "//STEP2 EXEC PGM=P2,COND=(4,LT)\n",
            "//DD2   DD   DSN=X.FILE,DISP=(OLD,DELETE)\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages_with_scenarios(lines)))
        pass_conflicts = [c for c in conflicts if "PASS" in c.reason]
        self.assertEqual(len(pass_conflicts), 1)
        self.assertEqual(pass_conflicts[0].scenario, "COND=(4,LT):SKIP")
        self.assertIn("STEP1", pass_conflicts[0].reason)

    def test_cond_on_a_step_marks_resulting_conflict_conditional(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
            "//STEP2 EXEC PGM=P2,COND=(4,LT)\n",
            "//DD2   DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages_with_scenarios(lines)))
        self.assertEqual(len(conflicts), 1)
        self.assertTrue(conflicts[0].conditional)

    def test_unconditional_duplicate_new_is_not_marked_conditional(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=P1\n",
            "//DD1   DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
            "//STEP2 EXEC PGM=P2\n",
            "//DD2   DD   DSN=X.FILE,DISP=(NEW,CATLG)\n",
        ]
        conflicts = check_disp_conflicts(build_dsn_graph(_usages_with_scenarios(lines)))
        self.assertEqual(len(conflicts), 1)
        self.assertFalse(conflicts[0].conditional)


if __name__ == "__main__":
    unittest.main()
