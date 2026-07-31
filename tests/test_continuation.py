import unittest

from jcl_parser import merge_continuations, parse_jcl


class MergeContinuationsTest(unittest.TestCase):
    def test_trailing_comma_merges_next_line(self) -> None:
        lines = [
            "//DD1 DD DSN=TEST.FILE,\n",
            "//    DISP=SHR\n",
        ]
        self.assertEqual(merge_continuations(lines), ["//DD1 DD DSN=TEST.FILE,DISP=SHR"])

    def test_unclosed_paren_merges_next_line(self) -> None:
        lines = [
            "//DD2 DD DSN=MY.FILE,DISP=(NEW,\n",
            "//    CATLG,DELETE)\n",
        ]
        self.assertEqual(
            merge_continuations(lines),
            ["//DD2 DD DSN=MY.FILE,DISP=(NEW,CATLG,DELETE)"],
        )

    def test_chained_continuations(self) -> None:
        lines = [
            "//DD3 DD DSN=MY.FILE,\n",
            "//    DISP=(NEW,\n",
            "//    CATLG,DELETE)\n",
        ]
        self.assertEqual(
            merge_continuations(lines),
            ["//DD3 DD DSN=MY.FILE,DISP=(NEW,CATLG,DELETE)"],
        )

    def test_comment_does_not_merge(self) -> None:
        lines = [
            "//STEP1 EXEC PGM=IEFBR14\n",
            "//* comment\n",
            "//STEP2 EXEC PGM=OTHER\n",
        ]
        self.assertEqual(
            merge_continuations(lines),
            ["//STEP1 EXEC PGM=IEFBR14", "//* comment", "//STEP2 EXEC PGM=OTHER"],
        )


class ParseJclContinuationTest(unittest.TestCase):
    def test_dd_params_merged_across_lines(self) -> None:
        lines = [
            "//DD1 DD DSN=TEST.FILE,\n",
            "//    DISP=SHR\n",
        ]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"], {"DSN": "TEST.FILE", "DISP": "SHR"})

    def test_unclosed_paren_across_lines(self) -> None:
        lines = [
            "//DD2 DD DSN=MY.FILE,DISP=(NEW,\n",
            "//    CATLG,DELETE)\n",
        ]
        parsed = parse_jcl(lines)
        self.assertEqual(parsed[0]["params"]["DISP"], ["NEW", "CATLG", "DELETE"])


if __name__ == "__main__":
    unittest.main()
