import unittest

from jcl_dsn_path import dsn_to_path


class DsnToPathTest(unittest.TestCase):
    def test_qualifiers_become_directories(self) -> None:
        self.assertEqual(dsn_to_path("HLQ.MID.LOW"), "data/HLQ/MID/LOW")

    def test_custom_base_dir(self) -> None:
        self.assertEqual(dsn_to_path("HLQ.FILE", base_dir="/mnt/mvs"), "/mnt/mvs/HLQ/FILE")

    def test_pds_member_becomes_extra_segment(self) -> None:
        self.assertEqual(dsn_to_path("HLQ.PDS(MEMBER)"), "data/HLQ/PDS/MEMBER")

    def test_gdg_relative_generation_becomes_extra_segment(self) -> None:
        self.assertEqual(dsn_to_path("HLQ.GDG(+1)"), "data/HLQ/GDG/+1")


if __name__ == "__main__":
    unittest.main()
