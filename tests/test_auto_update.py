import os
import shutil
import subprocess
import tempfile
import time
import unittest

from scripts import auto_update


def _git(cwd: str, *args: str, env=None) -> str:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    res = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return res.stdout.strip()


class TestAutoUpdateGitSync(unittest.TestCase):
    def setUp(self):
        self.tmp_root = tempfile.mkdtemp(prefix="gf_autoupdate_test_")
        self.bare_dir = os.path.join(self.tmp_root, "origin.git")
        self.peer_dir = os.path.join(self.tmp_root, "peer")
        self.local_dir = os.path.join(self.tmp_root, "local")
        self.backups_dir = os.path.join(self.local_dir, "backups")
        self.log_file = os.path.join(self.tmp_root, "auto_update.log")

        _git(self.tmp_root, "init", "--bare", "--initial-branch=main", self.bare_dir)
        _git(self.tmp_root, "clone", self.bare_dir, self.peer_dir)
        self._configure_git_user(self.peer_dir)

        with open(os.path.join(self.peer_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write("VERSION = 1\n")
        with open(os.path.join(self.peer_dir, "other.py"), "w", encoding="utf-8") as f:
            f.write("OTHER = 'init'\n")

        _git(self.peer_dir, "add", ".")
        base_env = self._commit_date_env(1700000000)
        _git(self.peer_dir, "commit", "-m", "initial", env=base_env)
        _git(self.peer_dir, "push", "-u", "origin", "main")

        _git(self.tmp_root, "clone", self.bare_dir, self.local_dir)
        self._configure_git_user(self.local_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)

    @staticmethod
    def _configure_git_user(repo_dir: str):
        _git(repo_dir, "config", "user.name", "TestUser")
        _git(repo_dir, "config", "user.email", "test@example.com")

    @staticmethod
    def _commit_date_env(ts: int) -> dict:
        iso = f"{ts} +0000"
        return {"GIT_AUTHOR_DATE": iso, "GIT_COMMITTER_DATE": iso}

    def test_pull_when_clean_and_remote_ahead(self):
        with open(os.path.join(self.peer_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write("VERSION = 2\n")
        _git(self.peer_dir, "commit", "-am", "remote v2", env=self._commit_date_env(1700000100))
        _git(self.peer_dir, "push", "origin", "main")

        self.assertTrue(auto_update.fetch_remote(self.local_dir, max_attempts=1, log_file=self.log_file))
        res = auto_update.sync_repository(self.local_dir, log_file=self.log_file, backups_dir=self.backups_dir)
        self.assertEqual(res["action"], "pulled_remote")
        self.assertTrue(res["changed"])
        with open(os.path.join(self.local_dir, "app.py"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "VERSION = 2\n")

    def test_merge_non_conflicting_when_remote_is_newer(self):
        local_other = os.path.join(self.local_dir, "other.py")
        with open(local_other, "w", encoding="utf-8") as f:
            f.write("OTHER = 'local_edit'\n")
        os.utime(local_other, (1700000050, 1700000050))

        with open(os.path.join(self.peer_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write("VERSION = 2\n")
        _git(self.peer_dir, "commit", "-am", "remote v2", env=self._commit_date_env(1700000200))
        _git(self.peer_dir, "push", "origin", "main")

        auto_update.fetch_remote(self.local_dir, max_attempts=1, log_file=self.log_file)
        res = auto_update.sync_repository(self.local_dir, log_file=self.log_file, backups_dir=self.backups_dir)
        self.assertEqual(res["action"], "merged_prefer_remote")
        with open(os.path.join(self.local_dir, "app.py"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "VERSION = 2\n")
        with open(local_other, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "OTHER = 'local_edit'\n")

    def test_conflict_remote_wins_when_remote_is_newer_and_creates_backup(self):
        local_app = os.path.join(self.local_dir, "app.py")
        with open(local_app, "w", encoding="utf-8") as f:
            f.write("VERSION = 999\n")
        os.utime(local_app, (1700000050, 1700000050))

        with open(os.path.join(self.peer_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write("VERSION = 3\n")
        _git(self.peer_dir, "commit", "-am", "remote v3", env=self._commit_date_env(1700000300))
        _git(self.peer_dir, "push", "origin", "main")

        auto_update.fetch_remote(self.local_dir, max_attempts=1, log_file=self.log_file)
        res = auto_update.sync_repository(self.local_dir, log_file=self.log_file, backups_dir=self.backups_dir)
        self.assertEqual(res["action"], "merged_prefer_remote")
        with open(local_app, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "VERSION = 3\n")
        self.assertTrue(os.path.isdir(self.backups_dir))
        self.assertTrue(any(name.endswith(".patch") for name in os.listdir(self.backups_dir)))

    def test_conflict_local_wins_and_pushes_when_local_is_newer(self):
        with open(os.path.join(self.peer_dir, "app.py"), "w", encoding="utf-8") as f:
            f.write("VERSION = 4\n")
        with open(os.path.join(self.peer_dir, "other.py"), "w", encoding="utf-8") as f:
            f.write("OTHER = 'remote_non_conflict'\n")
        _git(self.peer_dir, "commit", "-am", "remote v4", env=self._commit_date_env(1700000100))
        _git(self.peer_dir, "push", "origin", "main")

        local_app = os.path.join(self.local_dir, "app.py")
        with open(local_app, "w", encoding="utf-8") as f:
            f.write("VERSION = 500\n")
        future_ts = time.time() + 10
        os.utime(local_app, (future_ts, future_ts))

        auto_update.fetch_remote(self.local_dir, max_attempts=1, log_file=self.log_file)
        res = auto_update.sync_repository(self.local_dir, log_file=self.log_file, backups_dir=self.backups_dir)
        self.assertEqual(res["action"], "pushed_local")

        # Verificar que el remoto recibió los cambios locales ganadores y fusionó los no conflictivos
        _git(self.peer_dir, "pull", "origin", "main")
        with open(os.path.join(self.peer_dir, "app.py"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "VERSION = 500\n")
        with open(os.path.join(self.peer_dir, "other.py"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "OTHER = 'remote_non_conflict'\n")

    def test_ignores_personal_and_scratch_files(self):
        os.makedirs(os.path.join(self.local_dir, "scratch"), exist_ok=True)
        with open(os.path.join(self.local_dir, "scratch", "temp_test.py"), "w", encoding="utf-8") as f:
            f.write("print('tmp')\n")
        with open(os.path.join(self.local_dir, "games.json"), "w", encoding="utf-8") as f:
            f.write('[{"name": "SecretGame"}]\n')

        dirty = auto_update.get_dirty_entries(self.local_dir)
        self.assertEqual(dirty, [])


if __name__ == "__main__":
    unittest.main()
