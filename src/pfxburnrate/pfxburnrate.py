from typing import Iterable, Optional, DefaultDict, List, Dict

from dataclasses import dataclass, field
from collections import defaultdict

import datetime

@dataclass
class BurnRateResult:
  k: int
  pfx_cnt_min: int
  pfx_cnt_mean: int
  pfx_cnt_max: int
  pfx_cnt_uniq: int
  label: str = ""



class BurnRateCalculator():
  # Prefix counter across current snapshots for as.
  _pfx_counter: Dict[int, DefaultDict[str, int]]
  # Ringbuffers for current snapshots.
  _snapshots:  DefaultDict[int, List[Iterable[str]]]
  # Number of snapshots to consider.
  k: int
  # Number of snapshots added in total
  _total: int

  def __init__(self, k: int):
    if k == 0:
      raise ValueError("The number of snapshots, k, must be larger than 0.")
    self.k = k
    self._snapshots = defaultdict(lambda: [[] for x in range(k)])
    self._pfx_counter = dict()
    self._total = 0

  def advance(self, data: Dict[int, Iterable[str]]) -> Optional[Dict[int, BurnRateResult]]:
    # count the current snapshot and decount the last one, if neccessary
    self._count_snapshot(data)
    if self._total >= self.k:
      self._decount_snapshot(self._snapshots[self._total % self.k])
    self._snapshots[self._total % self.k] = data
    self._total += 1

    # Not full yet, return None
    if self._total < self.k:
      return None

    res = dict()
    for asn in self._pfx_counter:
      res[asn] = self._calc_burn_rate_result(asn)
    return res

  def _calc_burn_rate_result(self, asn:int):
    # Calc min, max, and mean number of pfx per snapshot.
    cnt_min = min([len(snap[asn]) if asn in snap else 0 for snap in self._snapshots.values()])
    cnt_max = max([len(snap[asn]) if asn in snap else 0 for snap in self._snapshots.values()])
    cnt_cs = sum([len(snap[asn]) if asn in snap else 0 for snap in self._snapshots.values()])

    cnt_mean = int(round(cnt_cs/self.k))
    cnt_uniq = len(self._pfx_counter[asn])

    return BurnRateResult(self.k, cnt_min, cnt_mean, cnt_max, cnt_uniq, label = str(asn))

  def _count_snapshot(self, data: Dict[int, Iterable[str]]):
    for asn in data:
      if asn not in self._pfx_counter:
        self._pfx_counter[asn] = defaultdict(int)
      for pfx in data[asn]:
        self._pfx_counter[asn][pfx] += 1

  # Decounts a snapshot from the prefix counter. 
  def _decount_snapshot(self, data: Dict[int, Iterable[str]]):
    for asn in data:
      if not asn in self._pfx_counter:
        continue 

      pfx_to_delete = []
      for pfx in data[asn]:
        self._pfx_counter[asn][pfx] -= 1
        if self._pfx_counter[asn][pfx] == 0:
          pfx_to_delete.append(pfx)

      for pfx in pfx_to_delete:
        del self._pfx_counter[asn][pfx]
      if len(self._pfx_counter[asn]) == 0:
        del self._pfx_counter[asn]


def date_iter(start_date: datetime.date, end_date: datetime.date):
    for n in range(int((end_date - start_date).days)+1):
        yield start_date + datetime.timedelta(n)
