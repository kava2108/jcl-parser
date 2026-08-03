import unittest

from jcl_models import to_model
from jcl_parser import build_ast, parse_jcl
from jcl_to_gha import to_github_actions


def _model(lines):
    return to_model(build_ast(parse_jcl(lines)))


class ToGithubActionsFileOpsTest(unittest.TestCase):
    def test_env_uses_resolved_path_not_raw_dsn(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//OUT   DD   DSN=HLQ.OUT,DISP=(NEW,CATLG,DELETE)\n",
        ]
        yaml_text = to_github_actions(_model(lines))

        self.assertIn("DD_OUT: data/HLQ/OUT", yaml_text)
        self.assertIn("# DISP=(NEW,CATLG,DELETE)", yaml_text)

    def test_new_dd_emits_prepare_step_with_mkdir(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//OUT   DD   DSN=HLQ.OUT,DISP=(NEW,CATLG)\n",
        ]
        yaml_text = to_github_actions(_model(lines))

        self.assertIn("- name: Prepare datasets", yaml_text)
        self.assertIn("mkdir -p 'data/HLQ'", yaml_text)

    def test_delete_on_normal_completion_emits_finalize_step_with_rm(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//TMP   DD   DSN=HLQ.TMP,DISP=(NEW,DELETE)\n",
        ]
        yaml_text = to_github_actions(_model(lines))

        self.assertIn("- name: Finalize datasets", yaml_text)
        self.assertIn("rm -f 'data/HLQ/TMP'", yaml_text)

    def test_custom_base_dir_propagates_to_paths(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=PROG1\n",
            "//IN    DD   DSN=HLQ.IN,DISP=SHR\n",
        ]
        yaml_text = to_github_actions(_model(lines), base_dir="/mnt/mvs")

        self.assertIn("DD_IN: /mnt/mvs/HLQ/IN", yaml_text)

    def test_step_without_dsn_dds_has_no_env_or_file_op_steps(self) -> None:
        lines = [
            "//JOB1  JOB  CLASS=A\n",
            "//STEP1 EXEC PGM=IEFBR14\n",
        ]
        yaml_text = to_github_actions(_model(lines))

        self.assertNotIn("env:", yaml_text)
        self.assertNotIn("Prepare datasets", yaml_text)
        self.assertNotIn("Finalize datasets", yaml_text)


if __name__ == "__main__":
    unittest.main()
