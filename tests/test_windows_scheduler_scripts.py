from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]


class WindowsSchedulerScriptTests(unittest.TestCase):
    def test_launcher_preserves_exit_code_and_uses_orchestrator(self):
        text = (ROOT / "scripts/windows/run_daily_order_collection.ps1").read_text(encoding="utf-8")
        for fragment in ("PYTHONPATH", "hmr_order_collection.orchestrator", "--config", "$LASTEXITCODE", "exit $exitCode", "LogDirectory"):
            self.assertIn(fragment, text)
        self.assertNotIn("SMTP_PASSWORD", text)

    def test_installer_is_server_safe_and_supports_validation_only(self):
        text = (ROOT / "scripts/windows/install_daily_order_collection_task.ps1").read_text(encoding="utf-8")
        for fragment in ("ValidateOnly", "14:00", "New-ScheduledTaskTrigger", "New-ScheduledTaskPrincipal", "SYSTEM", "IgnoreNew", "Register-ScheduledTask"):
            self.assertIn(fragment, text)


if __name__ == "__main__": unittest.main()
