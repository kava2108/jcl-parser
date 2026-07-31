import unittest

from jcl_disp_check import check_disp_conflicts
from jcl_dsn import build_dsn_graph, collect_dsn_usages
from jcl_models import to_model
from jcl_parser import build_ast, parse_jcl


def _usages(lines):
    model = to_model(build_ast(parse_jcl(lines)))
    return collect_dsn_usages(model)


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


if __name__ == "__main__":
    unittest.main()
