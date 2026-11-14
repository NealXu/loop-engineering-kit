from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def assert_install_upgrade(self, command):
        def assert_installed_doctor(skill_dir):
            p = subprocess.run([
                sys.executable, str(skill_dir / "loop_engineering" / "cli.py"),
                "doctor", "--mode", "installed", "--root", str(skill_dir),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn(
                "packs/software-development/verification-skill.md: present",
                p.stdout)

        with tempfile.TemporaryDirectory() as t:
            target = Path(t)
            legacy = target / ".codex" / "agents" / "implementer.toml"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("legacy\n", encoding="utf-8")

            first = subprocess.run(command(target), text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            skill = target / ".agents" / "skills" / "loop-engineering" / "SKILL.md"
            self.assertTrue(skill.exists())
            self.assertTrue((target / ".claude" / "skills" / "loop-engineering"
                             / "core" / "protocol.md").exists())
            self.assertTrue((target / ".claude" / "skills" / "loop-engineering"
                             / "loop_engineering" / "cli.py").exists())
            self.assertTrue((target / ".agents" / "skills" / "loop-engineering"
                             / "loop_engineering" / "cli.py").exists())
            self.assertTrue((target / ".agents" / "skills" / "loop-engineering"
                             / "packs" / "software-development"
                             / "verification-skill.md").exists())
            self.assertTrue((target / ".claude" / "skills" / "loop-engineering"
                             / "packs" / "software-development"
                             / "verification-skill.md").exists())
            assert_installed_doctor(
                target / ".agents" / "skills" / "loop-engineering")
            assert_installed_doctor(
                target / ".claude" / "skills" / "loop-engineering")
            self.assertTrue(legacy.exists())

            marker = "local marker"
            skill.write_text(marker, encoding="utf-8")
            skipped = subprocess.run(command(target), text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(skipped.returncode, 0, skipped.stdout + skipped.stderr)
            self.assertEqual(skill.read_text(encoding="utf-8"), marker)

            upgraded = subprocess.run(command(target, "--upgrade"), text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
            self.assertNotEqual(skill.read_text(encoding="utf-8"), marker)
            assert_installed_doctor(skill.parent)
            self.assertTrue(list(skill.parent.glob("SKILL.md.bak-*")))
            self.assertFalse(legacy.exists())
            self.assertTrue(list(legacy.parent.glob("implementer.toml.bak-*")))

    @unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell unavailable")
    def test_powershell_install_upgrade(self):
        powershell = shutil.which("powershell.exe")
        script = ROOT / "scripts" / "install.ps1"

        def command(target, *extra):
            return [
                powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-Target", "Both", "-Scope", "Project",
                "-ProjectRoot", str(target), *extra,
            ]

        self.assert_install_upgrade(command)

    @unittest.skipUnless(shutil.which("bash"), "bash unavailable")
    def test_bash_install_upgrade(self):
        bash = shutil.which("bash")
        script = ROOT / "scripts" / "install.sh"

        def as_bash(path):
            if sys.platform != "win32":
                return path.as_posix()
            convert = (
                'if command -v wslpath >/dev/null; then wslpath -u -- {path}; '
                'elif command -v cygpath >/dev/null; then cygpath -u {path}; '
                'else printf "%s\\n" {path}; fi'
            )
            command = convert.format(path=shlex.quote(path.as_posix()))
            p = subprocess.run([bash, "-lc", command],
                               text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
            self.assertEqual(p.returncode, 0, p.stderr)
            return p.stdout.strip()

        def command(target, *extra):
            argv = [
                "/bin/bash", as_bash(script), "--target", "both",
                "--scope", "project", "--project-root", as_bash(target), *extra,
            ]
            return [bash, "-lc", " ".join(map(shlex.quote, argv))]

        self.assert_install_upgrade(command)


if __name__ == "__main__":
    unittest.main()
