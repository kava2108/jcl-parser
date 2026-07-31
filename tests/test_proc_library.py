import os
import tempfile
import unittest

from jcl_analyze import analyze_file
from jcl_parser import build_ast
from jcl_proc import expand_procs, load_proc_library


class LoadProcLibraryTest(unittest.TestCase):
    def test_member_with_explicit_proc_pend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "PROCA"), "w", encoding="utf-8") as handle:
                handle.write(
                    "//PROCA   PROC PARM1=,LIB=DEFAULT.LIB\n"
                    "//STEP05  EXEC PGM=&PARM1\n"
                    "//DD1     DD   DSN=&LIB..DATA,DISP=SHR\n"
                    "//        PEND\n"
                )
            library = load_proc_library([tmp])

        self.assertIn("PROCA", library)
        proc_def = library["PROCA"]
        self.assertEqual(proc_def.params["LIB"], "DEFAULT.LIB")
        self.assertEqual(len(proc_def.statements), 2)

    def test_member_without_proc_pend_uses_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "procb"), "w", encoding="utf-8") as handle:
                handle.write(
                    "//S1 EXEC PGM=PROG1\n"
                    "//DD1 DD DSN=A.FILE,DISP=SHR\n"
                )
            library = load_proc_library([tmp])

        self.assertIn("PROCB", library)
        self.assertEqual(library["PROCB"].params, {})
        self.assertEqual(len(library["PROCB"].statements), 2)

    def test_search_order_first_directory_wins(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            with open(os.path.join(first, "PROCC"), "w", encoding="utf-8") as handle:
                handle.write("//S1 EXEC PGM=FROM_FIRST\n")
            with open(os.path.join(second, "PROCC"), "w", encoding="utf-8") as handle:
                handle.write("//S1 EXEC PGM=FROM_SECOND\n")

            library = load_proc_library([first, second])

        pgm = library["PROCC"].statements[0]["params"]["PGM"]
        self.assertEqual(pgm, "FROM_FIRST")

    def test_missing_directory_is_ignored(self) -> None:
        library = load_proc_library(["/no/such/directory"])
        self.assertEqual(library, {})


class ExternalProcExpansionTest(unittest.TestCase):
    def test_expand_procs_uses_external_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "PROCA"), "w", encoding="utf-8") as handle:
                handle.write(
                    "//PROCA   PROC PARM1=,LIB=DEFAULT.LIB\n"
                    "//STEP05  EXEC PGM=&PARM1\n"
                    "//DD1     DD   DSN=&LIB..DATA,DISP=SHR\n"
                    "//        PEND\n"
                )
            external = load_proc_library([tmp])

        statements = [
            {"type": "JOB", "name": "JOB1", "params": {}},
            {"type": "EXEC", "name": "RUN1", "params": {"_POSITIONAL": "PROCA", "PARM1": "MYPROG"}},
        ]
        expanded, warnings = expand_procs(statements, external)
        self.assertEqual(warnings, [])

        ast = build_ast(expanded)
        self.assertEqual(ast["steps"][0]["name"], "RUN1.STEP05")
        self.assertEqual(ast["steps"][0]["params"]["PGM"], "MYPROG")

    def test_analyze_file_merges_inline_and_external(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "EXTPROC"), "w", encoding="utf-8") as handle:
                handle.write("//S1 EXEC PGM=EXTERNAL_PGM\n")
            external = load_proc_library([tmp])

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".jcl", delete=False, encoding="utf-8"
            ) as jcl_file:
                jcl_file.write(
                    "//JOB1  JOB  CLASS=A\n"
                    "//CALL1 EXEC EXTPROC\n"
                )
                jcl_path = jcl_file.name

        try:
            scenario_models, warnings = analyze_file(jcl_path, external)
        finally:
            os.remove(jcl_path)

        self.assertEqual(warnings, [])
        self.assertEqual(len(scenario_models), 1)
        label, model = scenario_models[0]
        self.assertEqual(label, "default")
        self.assertEqual(model.steps[0].name, "CALL1.S1")
        self.assertEqual(model.steps[0].params["PGM"], "EXTERNAL_PGM")


if __name__ == "__main__":
    unittest.main()
