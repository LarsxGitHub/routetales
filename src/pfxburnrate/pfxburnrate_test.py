import unittest

from pfxburnrate import *
import datetime

class TestBurnRateCalculator(unittest.TestCase):
  def setup(self) -> List[Iterable[str]]:
    return [["a", "b", "c"],
            ["b", "d", "f"],
            ["b", "e", "h"],
            ["b", "f"]]

  def test_zero_error(self):
    with self.assertRaises(ValueError) as context:
      BurnRateCalculator(0)

  def test_not_full(self):
    brc = BurnRateCalculator(5)
    for snap in self.setup():
      self.assertIsNone(brc.advance(snap))

  def test_barely_filled(self):
    want = BurnRateResult(4, 2, 3, 3, 7)
    brc = BurnRateCalculator(4)
    snaps = self.setup()
    for snap in snaps[:3]:
      self.assertIsNone(brc.advance(snap))
    self.assertEqual(brc.advance(snaps[-1]), want)

  def test_rollover(self):
    brc = BurnRateCalculator(3)
    snaps = self.setup()
    for snap in snaps[:2]:
      self.assertIsNone(brc.advance(snap))

    self.assertEqual(brc.advance(snaps[2]), BurnRateResult(3, 3, 3, 3, 7))
    self.assertEqual(brc.advance(snaps[3]), BurnRateResult(3, 2, 3, 3, 5))


class TestDateIter(unittest.TestCase):
  def test_single_day(self):
    d = datetime.date(2013, 1, 1)
    self.assertEqual(list(date_iter(d, d)),[d])

  def test_range_simple(self):
    d1 = datetime.date(2013, 1, 1)
    d2 = datetime.date(2013, 1, 2)
    d3 = datetime.date(2013, 1, 3)
    self.assertEqual(list(date_iter(d1, d3)),[d1, d2, d3])

  def test_range_complex(self):
    d1 = datetime.date(2013, 1, 1)
    d2 = datetime.date(2013, 2, 3)
    self.assertEqual(len(list(date_iter(d1, d2))), 34)

if __name__ == "__main__":
  unittest.main()
