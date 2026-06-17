import unittest

from jcl_parser import parse_jcl


class ParseJclTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
