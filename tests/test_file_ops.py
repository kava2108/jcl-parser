import unittest

from jcl_file_ops import plan_dd_file_op, plan_step_file_ops
from jcl_models import to_model
from jcl_parser import build_ast, parse_jcl


def _model(lines):
    return to_model(build_ast(parse_jcl(lines)))


class PlanDdFileOpTest(unittest.TestCase):
    def test_new_catlg_delete_creates_and_keeps_on_normal_completion(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//OUT   DD   DSN=HLQ.OUT,DISP=(NEW,CATLG,DELETE)\n",
        ]
        dd = _model(lines).steps[0].dds[0]
        op = plan_dd_file_op(dd)

        self.assertEqual(op.path, "data/HLQ/OUT")
        self.assertEqual(op.pre_ops, ["mkdir -p 'data/HLQ'", ": > 'data/HLQ/OUT'"])
        # DELETE here is the *abnormal*-termination disposition, so normal
        # completion leaves the file in place.
        self.assertEqual(op.post_ops, [])

    def test_new_delete_on_normal_completion_removes_file(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//TMP   DD   DSN=HLQ.TMP,DISP=(NEW,DELETE)\n",
        ]
        dd = _model(lines).steps[0].dds[0]
        op = plan_dd_file_op(dd)

        self.assertEqual(op.post_ops, ["rm -f 'data/HLQ/TMP'"])

    def test_shr_expects_existing_file(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//IN    DD   DSN=HLQ.IN,DISP=SHR\n",
        ]
        dd = _model(lines).steps[0].dds[0]
        op = plan_dd_file_op(dd)

        self.assertEqual(op.pre_ops, ["test -e 'data/HLQ/IN'"])
        self.assertEqual(op.post_ops, [])

    def test_dummy_dd_has_no_dsn_and_is_skipped(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//DUM   DD   DUMMY\n",
        ]
        dd = _model(lines).steps[0].dds[0]
        self.assertIsNone(plan_dd_file_op(dd))


class PlanStepFileOpsTest(unittest.TestCase):
    def test_collects_ops_in_dd_order_skipping_dsn_less_dds(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//IN    DD   DSN=HLQ.IN,DISP=SHR\n",
            "//DUM   DD   DUMMY\n",
            "//OUT   DD   DSN=HLQ.OUT,DISP=(NEW,CATLG)\n",
        ]
        step = _model(lines).steps[0]
        ops = plan_step_file_ops(step)

        self.assertEqual([op.dd_name for op in ops], ["IN", "OUT"])


if __name__ == "__main__":
    unittest.main()
