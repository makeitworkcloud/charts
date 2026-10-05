"""Pure kernel-lifecycle state machine used by the client cancellation path.

Events are fed with a monotonic timestamp; deadlines are measured from
construction. The machine is deliberately strict: any unexpected event is an
error rather than a silent skip, and kernel death without a prior kill request
is a failure, not a success.
"""


class LifecycleError(Exception):
    pass


class KernelLifecycle:
    STARTING = "STARTING"
    READY = "READY"
    EXECUTING = "EXECUTING"
    KILL_PENDING = "KILL_PENDING"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"

    _TRANSITIONS = {
        ("STARTING", "INFO_READY"): "READY",
        ("READY", "EXECUTE_BEGIN"): "EXECUTING",
        ("EXECUTING", "EXECUTE_IDLE"): "READY",
        ("STARTING", "KILL_REQUEST"): "KILL_PENDING",
        ("READY", "KILL_REQUEST"): "KILL_PENDING",
        ("EXECUTING", "KILL_REQUEST"): "KILL_PENDING",
        ("KILL_PENDING", "KERNEL_DEAD"): "TERMINATED",
        ("STARTING", "KERNEL_DEAD"): "FAILED",
        ("READY", "KERNEL_DEAD"): "FAILED",
        ("EXECUTING", "KERNEL_DEAD"): "FAILED",
    }

    def __init__(self, start_deadline=120.0, execute_deadline=300.0, kill_deadline=60.0):
        self.start_deadline = float(start_deadline)
        self.execute_deadline = float(execute_deadline)
        self.kill_deadline = float(kill_deadline)
        self.state = self.STARTING
        self.kill_requested = False
        self.failure_reason = None
        self._kill_at = None

    def _deadline_for_state(self):
        if self.state == self.STARTING:
            return self.start_deadline
        if self.state in (self.READY, self.EXECUTING):
            return self.execute_deadline
        return None

    def feed(self, event, now=0.0):
        if self.state in (self.TERMINATED, self.FAILED):
            raise LifecycleError("event %s after terminal state %s" % (event, self.state))
        if self.state == self.KILL_PENDING and now - self._kill_at > self.kill_deadline:
            self.state = self.FAILED
            self.failure_reason = "kill deadline exceeded"
            return "failed"
        deadline = self._deadline_for_state()
        if deadline is not None and now > deadline:
            self.state = self.FAILED
            self.failure_reason = "deadline exceeded in %s" % self.state
            return "failed"
        key = (self.state, event)
        if key not in self._TRANSITIONS:
            raise LifecycleError("illegal event %s in state %s" % (event, self.state))
        self.state = self._TRANSITIONS[key]
        if event == "KILL_REQUEST":
            self.kill_requested = True
            self._kill_at = now
        if self.state == self.TERMINATED:
            return "succeed" if self.kill_requested else "failed"
        if self.state == self.FAILED:
            self.failure_reason = "kernel died unexpectedly"
            return "failed"
        if self.state == self.KILL_PENDING:
            return "kill"
        return "wait"
