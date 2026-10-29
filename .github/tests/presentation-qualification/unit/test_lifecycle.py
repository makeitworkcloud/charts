import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.lifecycle import KernelLifecycle, LifecycleError  # noqa: E402


class HappyPaths(unittest.TestCase):
    def test_full_session(self):
        machine = KernelLifecycle(start_deadline=100, execute_deadline=300, kill_deadline=60)
        self.assertEqual(machine.feed("INFO_READY", 5), "wait")
        self.assertEqual(machine.state, KernelLifecycle.READY)
        self.assertEqual(machine.feed("EXECUTE_BEGIN", 10), "wait")
        self.assertEqual(machine.feed("EXECUTE_IDLE", 120), "wait")
        self.assertEqual(machine.feed("KILL_REQUEST", 130), "kill")
        self.assertEqual(machine.feed("KERNEL_DEAD", 140), "succeed")
        self.assertEqual(machine.state, KernelLifecycle.TERMINATED)
        self.assertTrue(machine.kill_requested)
        self.assertIsNone(machine.failure_reason)

    def test_kill_before_ready(self):
        machine = KernelLifecycle()
        self.assertEqual(machine.feed("KILL_REQUEST", 3), "kill")
        self.assertEqual(machine.feed("KERNEL_DEAD", 4), "succeed")

    def test_execute_kill_midflight(self):
        machine = KernelLifecycle()
        machine.feed("INFO_READY", 1)
        machine.feed("EXECUTE_BEGIN", 2)
        self.assertEqual(machine.feed("KILL_REQUEST", 50), "kill")
        self.assertEqual(machine.feed("KERNEL_DEAD", 51), "succeed")


class FailurePaths(unittest.TestCase):
    def test_kernel_death_without_kill_is_failure(self):
        machine = KernelLifecycle()
        machine.feed("INFO_READY", 1)
        self.assertEqual(machine.feed("KERNEL_DEAD", 2), "failed")
        self.assertEqual(machine.state, KernelLifecycle.FAILED)
        self.assertIsNotNone(machine.failure_reason)

    def test_death_while_starting_is_failure(self):
        machine = KernelLifecycle()
        self.assertEqual(machine.feed("KERNEL_DEAD", 1), "failed")

    def test_start_deadline(self):
        machine = KernelLifecycle(start_deadline=100)
        self.assertEqual(machine.feed("INFO_READY", 150), "failed")
        self.assertIn("deadline", machine.failure_reason)

    def test_execute_deadline(self):
        machine = KernelLifecycle(execute_deadline=300)
        machine.feed("INFO_READY", 10)
        machine.feed("EXECUTE_BEGIN", 20)
        self.assertEqual(machine.feed("EXECUTE_IDLE", 400), "failed")

    def test_kill_deadline(self):
        machine = KernelLifecycle(kill_deadline=60)
        machine.feed("INFO_READY", 1)
        machine.feed("KILL_REQUEST", 10)
        self.assertEqual(machine.feed("KERNEL_DEAD", 100), "failed")

    def test_terminated_kernel_without_kill_is_failure(self):
        machine = KernelLifecycle()
        machine.feed("KILL_REQUEST", 1)
        machine.feed("KERNEL_DEAD", 2)
        self.assertEqual(machine.kill_requested, True)

    def test_unexpected_death_marks_not_kill_requested(self):
        machine = KernelLifecycle()
        machine.feed("INFO_READY", 1)
        machine.feed("KERNEL_DEAD", 2)
        self.assertFalse(machine.kill_requested)


class Strictness(unittest.TestCase):
    def test_illegal_event(self):
        machine = KernelLifecycle()
        with self.assertRaises(LifecycleError):
            machine.feed("EXECUTE_IDLE", 1)

    def test_event_after_terminal(self):
        machine = KernelLifecycle()
        machine.feed("KILL_REQUEST", 1)
        machine.feed("KERNEL_DEAD", 2)
        with self.assertRaises(LifecycleError):
            machine.feed("INFO_READY", 3)
        with self.assertRaises(LifecycleError):
            machine.feed("KERNEL_DEAD", 4)

    def test_double_kill_request(self):
        machine = KernelLifecycle()
        machine.feed("INFO_READY", 1)
        machine.feed("KILL_REQUEST", 2)
        with self.assertRaises(LifecycleError):
            machine.feed("KILL_REQUEST", 3)

    def test_reexecute_after_idle(self):
        machine = KernelLifecycle()
        machine.feed("INFO_READY", 1)
        machine.feed("EXECUTE_BEGIN", 2)
        machine.feed("EXECUTE_IDLE", 3)
        self.assertEqual(machine.feed("EXECUTE_BEGIN", 4), "wait")


if __name__ == "__main__":
    unittest.main()
