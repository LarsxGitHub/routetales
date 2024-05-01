from typing import Iterable, Optional, DefaultDict, List

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
  # Prefix counter across current snapshots.
  _pfx_counter: DefaultDict[str, int] 
  # Ringbuffer for current snapshots.
  _snapshots: List[Iterable[str]]
  # Current index within ringbuffer.
  _idx: int = 0
  # Number of snapshots to consider.
  k: int

  def __init__(self, k: int):
    if k == 0:
      raise ValueError("The number of snapshots, k, must be larger than 0.")
    self.k = k
    self._snapshots = []
    self._pfx_counter = defaultdict(int)

  def advance(self, data: Iterable[str]) -> Optional[BurnRateResult]:
    # Maintain ringbuffer.
    if len(self._snapshots) < self.k:
      # Not full yet.
      self._snapshots.append(data)
      self._count_snapshot(data)

    else:
      # Decount old pfxs, count new ones, replace snapshot.
      self._decount_snapshot(self._snapshots[self._idx])
      self._count_snapshot(data)
      self._snapshots[self._idx] = data
      self._idx = (self._idx + 1) % self.k

    # Not full yet, return None
    if len(self._snapshots) != self.k:
      return None

    # Calc min, max, and mean number of pfx per snapshot.
    cnt_min, cnt_max, cnt_cs = len(self._snapshots[0]), 0, 0
    for snap in self._snapshots:
      n = len(snap)
      cnt_max = max(cnt_max, n)
      cnt_min = min(cnt_min, n)
      cnt_cs += n
    cnt_mean = int(round(cnt_cs/self.k))
    cnt_uniq = len(self._pfx_counter)

    return BurnRateResult(self.k, cnt_min, cnt_mean, cnt_max, cnt_uniq)


  def _count_snapshot(self, data: Iterable[str]):
    for pfx in data:
      self._pfx_counter[pfx] += 1

  # Decounts a snapshot from the prefix counter. 
  def _decount_snapshot(self, data: Iterable[str]):
    pfx_to_delete = []
    for pfx in data:
      self._pfx_counter[pfx] -= 1
      if self._pfx_counter[pfx] == 0:
        pfx_to_delete.append(pfx)

    for pfx in pfx_to_delete:
      del self._pfx_counter[pfx]


def date_iter(start_date: datetime.date, end_date: datetime.date):
    for n in range(int((end_date - start_date).days)+1):
        yield start_date + datetime.timedelta(n)
