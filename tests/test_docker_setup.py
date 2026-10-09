import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docker_setup", REPO / "scripts/docker_setup.py")
docker_setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker_setup)


class DockerConfigTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(["bash", str(REPO / "docker-setup.sh"), *args],
                              text=True, capture_output=True)

    def test_merge_preserves_gpu_storage_network_and_proxy_settings(self):
        existing = {"data-root": "/data/docker", "runtimes": {"nvidia": {"path": "custom-runtime"}},
                    "proxies": {"https-proxy": "http://localhost:3128"}, "bip": "172.20.0.1/16"}
        merged = docker_setup.merge_daemon(existing, ["https://registry.example.com"])
        self.assertEqual(merged["runtimes"], existing["runtimes"])
        self.assertEqual(merged["proxies"], existing["proxies"])
        self.assertEqual(merged["data-root"], "/data/docker")
        self.assertEqual(merged["bip"], existing["bip"])
        self.assertNotIn("registry-mirrors", existing)
        self.assertEqual(docker_setup.merge_daemon(merged, merged["registry-mirrors"]), merged)

    def test_rejects_invalid_config_instead_of_discarding_it(self):
        with self.assertRaises(ValueError):
            docker_setup.merge_daemon([], [])
        for url in ["http://registry.example.com", "https://user:secret@example.com",
                    "https://example.com?token=secret", "https://example.com\nSigned-By: bad"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                docker_setup.validate_url(url)

    def test_platform_comes_from_target_os_not_source_server(self):
        self.assertEqual(docker_setup.platform_info('ID=ubuntu\nVERSION_CODENAME="jammy"\n'),
                         ("ubuntu", "jammy"))
        self.assertEqual(docker_setup.platform_info('ID=debian\nVERSION_CODENAME=trixie\n'),
                         ("debian", "trixie"))
        with self.assertRaises(ValueError):
            docker_setup.platform_info('ID=fedora\nVERSION_ID=42\n')

    def test_backup_is_private_and_identical_file_is_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "daemon.json"
            target.write_text('{"data-root":"/data"}\n')
            writer = docker_setup.ConfigWriter(root / "backups")
            self.assertTrue(writer.write(target, b'{"registry-mirrors":[]}\n', 0o600))
            backups = list((root / "backups").glob("*/daemon.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), '{"data-root":"/data"}\n')
            self.assertEqual(backups[0].parent.stat().st_mode & 0o777, 0o700)
            before = target.stat().st_mtime_ns
            self.assertFalse(writer.write(target, target.read_bytes(), 0o600))
            self.assertEqual(before, target.stat().st_mtime_ns)

    def test_configure_only_repeats_without_backup_or_service_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "etc/docker/daemon.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({"data-root": "/data/docker", "runtimes": {"custom": {"path": "runc"}}}))
            result = self.invoke("--configure-only", "--root", directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = json.loads(target.read_text())
            self.assertEqual(config["data-root"], "/data/docker")
            self.assertIn("custom", config["runtimes"])
            before = target.stat().st_mtime_ns
            result = self.invoke("--configure-only", "--root", directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(target.stat().st_mtime_ns, before)
            self.assertEqual(len(list((Path(directory) / "var/backups/terminal-setup/docker").iterdir())), 1)

    def test_dry_run_does_not_write_or_require_root_or_gpu(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke("--configure-only", "--gpu", "--dry-run", "--root", directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertIn("NVIDIA", result.stdout)

    def test_corrupt_existing_config_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "etc/docker/daemon.json"
            target.parent.mkdir(parents=True)
            target.write_text("{corrupt}")
            result = self.invoke("--configure-only", "--root", directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Expecting property name", result.stderr)
            self.assertEqual(target.read_text(), "{corrupt}")
            self.assertFalse((Path(directory) / "var").exists())

    def test_install_cannot_run_against_test_root(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke("--root", directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--root requires --configure-only", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_preview_does_not_read_protected_daemon_config(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "etc/docker/daemon.json"
            target.parent.mkdir(parents=True)
            target.write_text("{unreadable even if malformed}")
            target.chmod(0)
            try:
                result = self.invoke("--configure-only", "--dry-run", "--root", directory)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            finally:
                target.chmod(0o600)

    def test_unrelated_apt_source_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "docker.list").write_text("deb https://packages.example.com stable main\n")
            with self.assertRaises(ValueError):
                docker_setup.check_sources(False, Path(directory))

    def test_existing_workloads_require_explicit_restart(self):
        with patch.object(docker_setup, "service_active", return_value=True), \
                patch.object(docker_setup, "run", return_value="container-id\n"):
            with self.assertRaisesRegex(ValueError, "--restart"):
                docker_setup.check_workloads(False)
            docker_setup.check_workloads(True)

    def test_failed_restart_restores_previous_daemon_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "daemon.json"
            target.write_bytes(b'{"registry-mirrors": ["https://new.example.com"]}\n')
            previous = b'{"data-root":"/data/original"}\n'
            writer = docker_setup.ConfigWriter(Path(directory) / "backups")
            failure = subprocess.CalledProcessError(1, ["systemctl", "restart", "docker"])
            with patch.object(docker_setup, "run", side_effect=["", failure, ""]):
                with self.assertRaises(subprocess.CalledProcessError):
                    docker_setup.activate_service(target, True, previous, writer)
            self.assertEqual(target.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
