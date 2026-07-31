import unittest

from jcl_dsn import build_dsn_graph, collect_dsn_usages
from jcl_models import to_model
from jcl_parser import build_ast, parse_jcl


def _model(lines):
    return to_model(build_ast(parse_jcl(lines)))


class CollectDsnUsagesTest(unittest.TestCase):
    def test_scalar_and_tuple_disp(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//IN1   DD   DSN=A.FILE,DISP=SHR\n",
            "//STEP2 EXEC PGM=PROG2\n",
            "//OUT1  DD   DSN=B.FILE,DISP=(NEW,CATLG,DELETE)\n",
        ]
        usages = collect_dsn_usages(_model(lines))
        self.assertEqual(len(usages), 2)

        first = usages[0]
        self.assertEqual(first.dsn, "A.FILE")
        self.assertEqual(first.step_name, "STEP1")
        self.assertEqual(first.disp_status, "SHR")
        self.assertIsNone(first.disp_normal)
        self.assertEqual(first.order, 0)

        second = usages[1]
        self.assertEqual(second.dsn, "B.FILE")
        self.assertEqual(second.disp_status, "NEW")
        self.assertEqual(second.disp_normal, "CATLG")
        self.assertEqual(second.disp_abnormal, "DELETE")
        self.assertEqual(second.order, 1)

    def test_dummy_and_no_dsn_dd_excluded(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//DUM   DD   DUMMY\n",
            "//SYSIN DD   *\n",
            "some data\n",
            "/*\n",
        ]
        usages = collect_dsn_usages(_model(lines))
        self.assertEqual(usages, [])

    def test_gdg_relative_generation_normalized(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//GEN   DD   DSN=HLQ.GDG(+1),DISP=(NEW,CATLG)\n",
        ]
        usages = collect_dsn_usages(_model(lines))
        self.assertEqual(usages[0].dsn, "HLQ.GDG")


class BuildDsnGraphTest(unittest.TestCase):
    def test_groups_usages_by_dsn_in_order(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//OUT   DD   DSN=SHARED.FILE,DISP=(NEW,CATLG)\n",
            "//STEP2 EXEC PGM=PROG2\n",
            "//IN    DD   DSN=SHARED.FILE,DISP=SHR\n",
        ]
        usages = collect_dsn_usages(_model(lines))
        graph = build_dsn_graph(usages)

        self.assertEqual(list(graph.keys()), ["SHARED.FILE"])
        timeline = graph["SHARED.FILE"]
        self.assertEqual([u.step_name for u in timeline], ["STEP1", "STEP2"])
        self.assertEqual([u.disp_status for u in timeline], ["NEW", "SHR"])


if __name__ == "__main__":
    unittest.main()
