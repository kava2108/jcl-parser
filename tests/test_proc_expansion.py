import unittest

from jcl_parser import build_ast, parse_jcl
from jcl_proc import expand_procs, extract_procs


def _expand(lines):
    remaining, proc_defs = extract_procs(parse_jcl(lines))
    return expand_procs(remaining, proc_defs)


class ProcDefaultAndOverrideTest(unittest.TestCase):
    def test_default_and_dd_override(self) -> None:
        lines = [
            "//JOB1    JOB  CLASS=A\n",
            "//PROCA   PROC PARM1=,LIB=DEFAULT.LIB\n",
            "//STEP05  EXEC PGM=&PARM1\n",
            "//DD1     DD   DSN=&LIB..DATA,DISP=SHR\n",
            "//        PEND\n",
            "//RUN1    EXEC PROCA,PARM1=MYPROG\n",
            "//RUN1.DD1 DD  DSN=OVERRIDE.DATA,DISP=OLD\n",
        ]
        expanded, warnings = _expand(lines)
        self.assertEqual(warnings, [])

        ast = build_ast(expanded)
        self.assertEqual(len(ast["steps"]), 1)
        step = ast["steps"][0]
        self.assertEqual(step["name"], "RUN1.STEP05")
        self.assertEqual(step["params"]["PGM"], "MYPROG")

        dd = step["dds"][0]
        self.assertEqual(dd["name"], "DD1")
        self.assertEqual(dd["params"]["DSN"], "OVERRIDE.DATA")
        self.assertEqual(dd["params"]["DISP"], "OLD")

    def test_proc_default_used_without_override(self) -> None:
        lines = [
            "//JOB1    JOB  CLASS=A\n",
            "//PROCA   PROC PARM1=,LIB=DEFAULT.LIB\n",
            "//STEP05  EXEC PGM=&PARM1\n",
            "//DD1     DD   DSN=&LIB..DATA,DISP=SHR\n",
            "//        PEND\n",
            "//RUN1    EXEC PROCA,PARM1=MYPROG\n",
        ]
        expanded, warnings = _expand(lines)
        self.assertEqual(warnings, [])
        ast = build_ast(expanded)
        dd = ast["steps"][0]["dds"][0]
        self.assertEqual(dd["params"]["DSN"], "DEFAULT.LIB.DATA")
        self.assertEqual(dd["params"]["DISP"], "SHR")


class ProcMultiStepTest(unittest.TestCase):
    def test_qualified_dd_override_on_multi_step_proc(self) -> None:
        lines = [
            "//JOB1     JOB  CLASS=A\n",
            "//PROCB    PROC\n",
            "//S1       EXEC PGM=PROG1\n",
            "//IN1      DD   DSN=A.FILE,DISP=SHR\n",
            "//S2       EXEC PGM=PROG2\n",
            "//OUT1     DD   DSN=B.FILE,DISP=(NEW,CATLG)\n",
            "//         PEND\n",
            "//CALL1    EXEC PROCB\n",
            "//CALL1.S2.OUT1 DD DSN=OVERRIDE.FILE,DISP=(NEW,KEEP)\n",
        ]
        expanded, warnings = _expand(lines)
        self.assertEqual(warnings, [])

        ast = build_ast(expanded)
        step_names = [s["name"] for s in ast["steps"]]
        self.assertEqual(step_names, ["CALL1.S1", "CALL1.S2"])

        in1 = ast["steps"][0]["dds"][0]
        self.assertEqual(in1["params"]["DSN"], "A.FILE")

        out1 = ast["steps"][1]["dds"][0]
        self.assertEqual(out1["params"]["DSN"], "OVERRIDE.FILE")
        self.assertEqual(out1["params"]["DISP"], ["NEW", "KEEP"])


class ProcSymbolTest(unittest.TestCase):
    def test_set_statement_feeds_global_symtab(self) -> None:
        lines = [
            "//JOB1   JOB  CLASS=A\n",
            "//        SET  ENV=PROD\n",
            "//PROCD  PROC\n",
            "//S1     EXEC PGM=RUN&ENV\n",
            "//        PEND\n",
            "//CALL4  EXEC PROCD\n",
        ]
        expanded, warnings = _expand(lines)
        self.assertEqual(warnings, [])
        ast = build_ast(expanded)
        self.assertEqual(ast["steps"][0]["params"]["PGM"], "RUNPROD")

    def test_unresolved_symbol_is_reported(self) -> None:
        lines = [
            "//JOB1   JOB  CLASS=A\n",
            "//PROCC  PROC\n",
            "//S1     EXEC PGM=&MISSING\n",
            "//        PEND\n",
            "//CALL2  EXEC PROCC\n",
        ]
        expanded, warnings = _expand(lines)
        self.assertEqual(len(warnings), 1)
        self.assertIn("MISSING", warnings[0])
        ast = build_ast(expanded)
        self.assertEqual(ast["steps"][0]["params"]["PGM"], "&MISSING")


class UnresolvedProcReferenceTest(unittest.TestCase):
    def test_unknown_proc_reference_passes_through_with_warning(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//CALL3 EXEC PROCNOTDEFINED\n",
        ]
        expanded, warnings = _expand(lines)
        self.assertEqual(len(warnings), 1)
        self.assertIn("PROCNOTDEFINED", warnings[0])
        self.assertEqual(expanded[-1]["name"], "CALL3")


if __name__ == "__main__":
    unittest.main()
