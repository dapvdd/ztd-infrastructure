"""F-14/F-15: credential entropy documentation and automation-safe hardening."""

import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# F-13: isolated runs (pytest apps/api/tests/test_hardening_contracts.py from
# the repo root) have no sys.path entry for apps/api, so `import src...`
# fails. Other suite files only make it work as a side effect of collection
# order; make this file self-sufficient.
_API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)



class TestCredentialEntropyDocs:
    def test_min_entropy_constant_defined(self):
        from src.provisioning.auth import MIN_CREDENTIAL_ENTROPY_BITS

        assert MIN_CREDENTIAL_ENTROPY_BITS >= 128

    def test_token_guard_uses_constant(self):
        import inspect

        from src.provisioning import auth

        source = inspect.getsource(auth.token_guard)
        assert "MIN_CREDENTIAL_ENTROPY_BITS" in source

    def test_credential_hash_assumption_documented(self):
        import inspect

        from src.provisioning import auth

        doc = inspect.getdoc(auth.credential_hash)
        module_doc = (auth.__doc__ or "") + "\n" + inspect.getsource(auth)
        assert doc and len(doc) > 20
        # The review note on hashing assumptions must exist near the function.
        assert "SHA-256" in module_doc or "sha256" in module_doc
        assert "KDF" in module_doc

    def test_credential_hash_backward_compatible(self):
        """Existing credentials must keep verifying (no algorithm change)."""
        import hashlib

        from src.provisioning.auth import credential_hash

        assert credential_hash("test-password") == hashlib.sha256(
            b"test-password"
        ).hexdigest()


class TestHardenNginxNonInteractive:
    @pytest.fixture()
    def script(self):
        path = os.path.join(REPO, "scripts", "harden-nginx.sh")
        if not os.path.isfile(path):
            pytest.skip("harden-nginx.sh not present")
        return path

    def _run(self, bash, script, cwd, env_extra, extra_path=None):
        env = os.environ.copy()
        env.update(env_extra)
        if extra_path:
            env["PATH"] = extra_path + os.pathsep + env["PATH"]
        return subprocess.run(
            [bash, script],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )

    def _bash(self):
        # On Windows, PATH can expose the WSL stub at
        # %LOCALAPPDATA%\Microsoft\WindowsApps\bash.EXE, which exits 1 with
        # "no installed distributions" instead of running POSIX scripts.
        # Prefer a real Git-for-Windows bash; skip WSL stubs (normcase:
        # Windows paths are case-insensitive).
        wsl_stub = os.path.normcase(
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\bash.exe")
        )
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            shutil.which("bash"),
        ):
            if candidate and os.path.isfile(candidate) \
                    and os.path.normcase(os.path.abspath(candidate)) != wsl_stub:
                return candidate
        return None

    @staticmethod
    def _scratch(tmp_path):
        """Minimal repo shape so the script passes its layout guard and
        reaches the password guard (which is the behavior under test)."""
        (tmp_path / "nginx").mkdir(exist_ok=True)
        (tmp_path / "nginx" / "default.conf").write_text("# scratch\n")
        (tmp_path / "docker-compose.yml").write_text("services: {}\n")
        return str(tmp_path)

    def _gitbin(self):
        """Git for Windows provides openssl via its usr/bin."""
        candidate = r"C:\Program Files\Git\usr\bin"
        return candidate if os.path.isdir(candidate) else None

    def test_noninteractive_without_admin_pass_exits_2(self, script, tmp_path):
        bash = self._bash()
        if not bash:
            pytest.skip("bash not available on this platform")
        cwd = self._scratch(tmp_path)
        env_extra = {"NONINTERACTIVE": "1"}
        gitbin = self._gitbin()
        proc = self._run(bash, script, cwd, env_extra, extra_path=gitbin)
        assert proc.returncode == 2, (proc.stdout, proc.stderr)
        assert "ADMIN_PASS" in (proc.stderr + proc.stdout)
        # No files may have been touched before the password guard.
        assert (tmp_path / "nginx" / "default.conf").read_text() == "# scratch\n"

    def test_interactive_mode_untouched_with_env_pass(self, script, tmp_path):
        bash = self._bash()
        if not bash:
            pytest.skip("bash not available on this platform")
        cwd = self._scratch(tmp_path)
        env_extra = {"ADMIN_PASS": "x" * 12, "DRY_RUN": "1"}
        gitbin = self._gitbin()
        proc = self._run(bash, script, cwd, env_extra, extra_path=gitbin)
        # DRY_RUN in scratch env: script completes file edits and exits 0.
        # (docker absent paths are skipped by DRY_RUN.) Accept 0 or 1 for
        # environment differences, but never a hang or exit 2.
        assert proc.returncode in (0, 1), (proc.stdout, proc.stderr)
