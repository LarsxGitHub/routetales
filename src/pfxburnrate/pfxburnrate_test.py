import unittest

from pfxburnrate import *
import datetime
from pprint import pprint

class TestBurnRateCalculator(unittest.TestCase):
  def setup(self) -> List[Iterable[str]]:
    return [
      {1: ["a", "b", "c"]},
      {1: ["b", "d", "f"]},
      {1: ["b", "e", "h"]},
      {1: ["b", "f"]}]


  def test_zero_error(self):
    with self.assertRaises(ValueError) as context:
      BurnRateCalculator(0)

  def test_not_full(self):
    brc = BurnRateCalculator(5)
    for snap in self.setup():
      self.assertIsNone(brc.advance(snap))

  def test_barely_filled(self):
    want = {1: BurnRateResult(4, 2, 3, 3, 7, "1")}
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

    want = {1:BurnRateResult(3, 3, 3, 3, 7, "1")}
    got = brc.advance(snaps[2])
    self.assertEqual(got, want)

    want = {1:BurnRateResult(3, 2, 3, 3, 5, "1")}
    got = brc.advance(snaps[3])

    self.assertEqual(got, want)

  def test_multi(self):
    snaps = [
      {1: ["a", "b", "c"]},
      {
        1: ["b", "d", "f"],
        2: ["x", "y", "z"],
      },
      {
        1: ["b", "e", "h"],
        2: ["w", "x"],
      },
      {
        1: ["b", "f"],
        3: ["c"],
      }]

    brc = BurnRateCalculator(3)
    for snap in snaps[:2]:
      self.assertIsNone(brc.advance(snap))

    want = {
      1: BurnRateResult(3, 3, 3, 3, 7, "1"),
      2: BurnRateResult(3, 0, 2, 3, 4, "2"),
    }
    got = brc.advance(snaps[2])
    self.assertEqual(got, want)

    want = {
      1: BurnRateResult(3, 2, 3, 3, 5, "1"),
      2: BurnRateResult(3, 0, 2, 3, 4, "2"),
      3: BurnRateResult(3, 0, 0, 1, 1, "3"),
    }
    got = brc.advance(snaps[3])
    self.assertEqual(got, want)

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
