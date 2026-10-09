import unittest
from unittest.mock import patch
from scripts.resume_fresh_collection import SharedRequestInterval


class CollectionIntervalTests(unittest.TestCase):
    def test_early_sleep_return_is_rechecked(self):
        clock=[0.0]
        def sleep(seconds): clock[0]+=max(seconds-.013,.001)
        with patch('scripts.resume_fresh_collection.time.perf_counter',side_effect=lambda:clock[0]), patch('scripts.resume_fresh_collection.time.sleep',side_effect=sleep):
            limiter=SharedRequestInterval(1.2)
            for _ in range(4): limiter.before_request()
        intervals=[b-a for a,b in zip([0.0,*limiter.starts[:-1]],limiter.starts)]
        self.assertTrue(all(t>=1.2 for t in intervals))

    def test_configuration_cannot_relax_interval(self):
        with self.assertRaises(ValueError): SharedRequestInterval(1.19)


if __name__=='__main__':unittest.main()
