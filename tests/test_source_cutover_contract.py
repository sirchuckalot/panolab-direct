"""Offline guardrails for the one-time owner-user source migration cutover."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"host/apply-source-migration.sh"

class GuardedMigrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=SCRIPT.read_text()

    def test_stops_on_dirty_or_divergent_laptop_checkout(self):
        for fragment in ("EXPECTED_BASE=fa33395bb907186e1d6f16fcf632fcee5786eb9a",
                         "git -C \"$ROOT\" status --porcelain",
                         "git -C \"$ROOT\" ls-remote origin refs/heads/development",
                         "git -C \"$ROOT\" merge --ff-only",
                         "backup-source-before-"):
            self.assertIn(fragment,self.source)

    def test_rootless_rebuild_limited_to_panolab_services(self):
        for fragment in ('"name=rootless"', 'projects/rescue/build.sh',
                         'python3 shared/source_registry.py verify',
                         'up -d --no-deps --no-build --force-recreate repo-git docker-broker',
                         '--upgrade-dev', 'MIGRATION_LOCAL_PASS'):
            self.assertIn(fragment,self.source)
        for forbidden in ('sudo ','docker system prune','git reset --hard','git push --force','--privileged'):
            self.assertNotIn(forbidden,self.source)

    def test_laptop_cutover_does_not_publish_or_program_hardware(self):
        self.assertIn('GitHub has NOT been pushed',self.source)
        self.assertIn('Do not push.',self.source)
        self.assertNotIn('git push origin',self.source)
        self.assertNotIn('openocd -f',self.source)
        self.assertIn('cmp -s "$SCRIPT"',self.source)

if __name__=="__main__":
    unittest.main()
