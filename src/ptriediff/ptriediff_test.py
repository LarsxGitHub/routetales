import unittest

from ptriediff import *
from typing import List

import ipaddress

from pytricia import PyTricia

def pyt_from_pfxs_v4(pfxs: List[str]) -> PyTricia:
    pyt = PyTricia()
    for pfx_raw in pfxs:
        pyt.insert(ipaddress.IPv4Network(pfx_raw), "")
    return pyt 

class TestClassDiffCountChange(unittest.TestCase):

    def test_gain(self):
        cd = ClassDiff(0, 0, 0)
        cd.count_change(DiffType.GAIN)
        self.assertEqual(cd, ClassDiff(1, 0, 0))

    def test_loss(self):
        cd = ClassDiff(0, 0, 0)
        cd.count_change(DiffType.LOSS)
        self.assertEqual(cd, ClassDiff(0, 1, 0))

    def test_main(self):
        cd = ClassDiff(0, 0, 0)
        cd.count_change(DiffType.MAIN)
        self.assertEqual(cd, ClassDiff(0, 0, 1))

    def test_err(self):
        cd = ClassDiff(0, 0, 0)
        with self.assertRaises(ValueError):
            cd.count_change(10000)

class TestMatchesToDiffType(unittest.TestCase):

    def test_gain(self):
        res = matches_to_difftype(False, True)
        self.assertEqual(res, DiffType.GAIN)

    def test_loss(self):
        res = matches_to_difftype(True, False)
        self.assertEqual(res, DiffType.LOSS)

    def test_main(self):
        res = matches_to_difftype(True, True)
        self.assertEqual(res, DiffType.MAIN)
        res = matches_to_difftype(False, False)
        self.assertEqual(res, DiffType.MAIN)

class TestHasNoDirectMspCoverage(unittest.TestCase):
    def setup(self) -> Tuple[PyTricia, PyTricia, ipaddress.IPv4Network]:
        pfxs = ["192.0.2.0/24", "192.0.2.0/25"]
        return (
            pyt_from_pfxs_v4(pfxs), 
            pyt_from_pfxs_v4(pfxs), 
            ipaddress.IPv4Network("192.0.2.0/24")
        )

    def test_gain(self):
        old, new, pfx = self.setup()
        del new[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_no_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.GAIN)

    def test_loss(self):
        old, new, pfx = self.setup()
        del old[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_no_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.LOSS)

    def test_main_neither(self):
        old, new, pfx = self.setup()
        res = has_no_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.MAIN)

    def test_main_both(self):
        old, new, pfx = self.setup()
        del new[ipaddress.IPv4Network("192.0.2.0/25")]
        del old[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_no_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.MAIN)

class TestHasPartialDirectMspCoverage(unittest.TestCase):
    def setup(self) -> Tuple[PyTricia, PyTricia, ipaddress.IPv4Network]:
        pfxs = ["192.0.2.0/24", "192.0.2.0/25"]
        return (
            pyt_from_pfxs_v4(pfxs), 
            pyt_from_pfxs_v4(pfxs), 
            ipaddress.IPv4Network("192.0.2.0/24")
        )

    def test_gain(self):
        old, new, pfx = self.setup()
        del old[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_partial_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.GAIN)

    def test_loss(self):
        old, new, pfx = self.setup()
        del new[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_partial_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.LOSS)

    def test_main_neither(self):
        old, new, pfx = self.setup()
        del new[ipaddress.IPv4Network("192.0.2.0/25")]
        del old[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_partial_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.MAIN)

    def test_main_both(self):
        old, new, pfx = self.setup()
        res = has_partial_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.MAIN)

class TestHasFullDirectMspCoverage(unittest.TestCase):
    def setup(self) -> Tuple[PyTricia, PyTricia, ipaddress.IPv4Network]:
        pfxs = ["192.0.2.0/24", "192.0.2.0/25", "192.0.2.128/25"]
        return (
            pyt_from_pfxs_v4(pfxs), 
            pyt_from_pfxs_v4(pfxs), 
            ipaddress.IPv4Network("192.0.2.0/24")
        )

    def test_gain(self):
        old, new, pfx = self.setup()
        del old[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_full_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.GAIN)

    def test_loss(self):
        old, new, pfx = self.setup()
        del new[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_full_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.LOSS)

    def test_main_neither(self):
        old, new, pfx = self.setup()
        del new[ipaddress.IPv4Network("192.0.2.0/25")]
        del old[ipaddress.IPv4Network("192.0.2.0/25")]
        res = has_full_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.MAIN)

    def test_main_both(self):
        old, new, pfx = self.setup()
        res = has_full_direct_msp_coverage(old, new, pfx)
        self.assertEqual(res, DiffType.MAIN)

class TestCountMspCoveredAddresses(unittest.TestCase):
    def test_full_cover(self):
        pyt = pyt_from_pfxs_v4(["192.0.2.0/24", "192.0.2.0/25", "192.0.2.128/25"])
        pfx = ipaddress.IPv4Network("192.0.2.0/24")
        res = count_msp_covered_addresses(pyt, pfx)
        self.assertEqual(res, 256)

    def test_half_cover(self):
        pyt = pyt_from_pfxs_v4(["192.0.2.0/24", "192.0.2.0/25"])
        pfx = ipaddress.IPv4Network("192.0.2.0/24")
        res = count_msp_covered_addresses(pyt, pfx)
        self.assertEqual(res, 128)

    def test_075_cover(self):
        pyt = pyt_from_pfxs_v4(["192.0.2.0/24", "192.0.2.0/25", "192.0.2.128/26"])
        pfx = ipaddress.IPv4Network("192.0.2.0/24")
        res = count_msp_covered_addresses(pyt, pfx)
        self.assertEqual(res, 192)

    def test_no_cover(self):
        pyt = pyt_from_pfxs_v4(["192.0.2.0/24", "198.51.100.0/25"])
        pfx = ipaddress.IPv4Network("192.0.2.0/24")
        res = count_msp_covered_addresses(pyt, pfx)
        self.assertEqual(res, 0)







if __name__ == '__main__':
    unittest.main()