"""Resource-budget regressions independent of the host operating system."""
import ctypes as c
import unittest

from thm.runtime.fabric.resources import ChildBudget


class Basic(c.Structure):
    _fields_ = [('job_time', c.c_longlong)]


class Extended(c.Structure):
    _fields_ = [('basic', Basic)]


class FakeKernel:
    def __init__(self):
        self.job_times = []

    def QueryInformationJobObject(self, job, info_class, buffer, size, returned):
        return True

    def SetInformationJobObject(self, job, info_class, buffer, size):
        value = c.cast(buffer, c.POINTER(Extended)).contents.basic.job_time
        self.job_times.append(value)
        return True


class ResourceBudgetTests(unittest.TestCase):
    def test_windows_job_renewal_uses_cumulative_cpu_ceiling(self):
        budget = ChildBudget.__new__(ChildBudget)
        budget.last = {'cpu_seconds': 2.0, 'bytes_read': 3, 'bytes_written': 4}
        budget.job = object()
        budget.kernel = FakeKernel()
        budget.extended = Extended

        budget.renew(cpu=5.0, io=10)

        self.assertEqual(budget.cpu, 7.0)
        self.assertEqual(budget.io, 17)
        self.assertEqual(budget.kernel.job_times, [70_000_000])


if __name__ == '__main__':
    unittest.main()
