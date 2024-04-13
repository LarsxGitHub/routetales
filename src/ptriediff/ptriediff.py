from typing import Tuple, DefaultDict
from enum import Enum

import bz2
import ipaddress

import logging

from pytricia import PyTricia
from dataclasses import dataclass, InitVar
from collections import defaultdict

logger = logging.getLogger(__name__)


# ----------------- DataClasses to track Prefix-level Diff results -----------------

class DiffType(Enum):
  GAIN = 1
  LOSS = 2
  MAIN = 3

@dataclass
class ClassDiff:
  # number of prefixes newly gained in this Class
  gain: InitVar[int] = 0
  # number of prefixes lossed in this Class
  loss: InitVar[int] = 0
  # number of prefixes maintained in this Class
  main: InitVar[int] = 0

  def count_change(self, t: DiffType):
    if t == DiffType.GAIN:
        self.gain += 1
    elif t == DiffType.LOSS:
        self.loss += 1
    elif t == DiffType.MAIN:
        self.main += 1
    else:
      raise ValueError("No counting option associated with unknown DiffType %d.")

@dataclass
class ClassTracker:
  # pfx has no direct MSPs.
  has_no_direct_msp_coverage: InitVar[ClassDiff] = ClassDiff()
  # pfx has one direct MSPs.
  has_partial_direct_msp_coverage: InitVar[ClassDiff] = ClassDiff()
  # pfx has two direct MSPs.
  has_full_direct_msp_coverage: InitVar[ClassDiff] = ClassDiff()

  # pfx has no (in)direct MSPs.
  has_no_msp_coverage: InitVar[ClassDiff] = ClassDiff()
  # pfx has parts of its address space covered by (in)direct MSPs.
  has_partial_msp_coverage: InitVar[ClassDiff] = ClassDiff()
  # pfx has its entire address space covered by (in)direct MSPs.
  has_full_msp_coverage: InitVar[ClassDiff] = ClassDiff()

  # pfx has sibling
  has_sibling: InitVar[ClassDiff] = ClassDiff()
  # pfx has direct less-specific
  has_direct_less_specific: InitVar[ClassDiff] = ClassDiff()
  # pfx has (in)direct less-specific
  has_direct_less_specific: InitVar[ClassDiff] = ClassDiff()

@dataclass
class PfxFowardDiff:
  # count of prefixes in older snapshot.
  cnt_pfx_old: InitVar[int] = 0
  # count of prefixes in newer snapshot.
  cnt_pfx_new: InitVar[int] = 0

  # the number of pfx only in older, newer, and both
  cnt_pfx: InitVar[ClassDiff] = ClassDiff()
  # Classtracker values by CIDR size
  classtracker_by_cidr: InitVar[DefaultDict[int, ClassTracker]] = defaultdict(ClassTracker)
  # Classtracker for all prefixes
  class_totals: InitVar[ClassTracker] = ClassTracker()

# ----------------- Helper functions -----------------

def matches_to_difftype(old_match: bool, new_match: bool) -> DiffType:
  """Helper function to turn the characteristic matches into a DiffType.

  Args:
      old_match (bool): whether the characteristic matched for the older snapshot.
      new_match (bool): whether the characteristic matched for the newer snapshot.

  Returns:
      DiffType: The resulting Diff type.
  """
  if old_match == new_match:
    return DiffType.MAIN
  if old_match:
    return DiffType.LOSS
  return DiffType.GAIN

def count_direct_msps(pyt: PyTricia, pfx: ipaddress.ip_network) -> int:
  cnt = 0
  direct_msps = pfx.subnets(prefixlen_diff=1)
  for msp in direct_msps:
    if pyt.has_key(msp):
      cnt += 1
  return cnt 

def count_msp_covered_addresses(pyt: PyTricia, pfx: ipaddress.ip_network) -> int:
  # Pytricia's children() and parent() methods return strings instead of network types ...
  pfx_str = str(pfx)
  maxcidr = 32 if pfx.version == 4 else 128

  cnt = 0
  for msp in pyt.children(pfx):
    # ignore pfx itself and msps of msps to avoid overcounting.
    if pyt.parent(msp) != pfx_str:
      continue 
    # Calc the addresses in the prefix. 
    cnt += (2**(maxcidr - int(msp.rsplit("/", 1)[1])))
  return cnt 

# ----------------- Functions to Compare Pyts at prefix -----------------

def has_no_direct_msp_coverage(old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network) -> DiffType:
  return matches_to_difftype(
    count_direct_msps(old, pfx) == 0,
    count_direct_msps(new, pfx) == 0,
  )


def has_partial_direct_msp_coverage(old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network) -> DiffType:
  return matches_to_difftype(
    count_direct_msps(old, pfx) == 1,
    count_direct_msps(new, pfx) == 1,
)

def has_full_direct_msp_coverage(old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network) -> DiffType:
  return matches_to_difftype(
    count_direct_msps(old, pfx) == 2,
    count_direct_msps(new, pfx) == 2,
)

def has_address_msp_coverage(old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network) -> Tuple[DiffType, DiffType, DiffType]:
  pass


@dataclass
class AsLevelFowardDiff:
  # ASes that started/stopped announcing at least one prefix.
  cnt_as_pfx_gain: int
  cnt_as_pfx_loss: int
  cnt_as_pfx_same: int


def forward_diff_pyts(old: PyTricia, new: PyTricia) -> PfxFowardDiff:
  pass 

@dataclass
class PytMeta:
  # origin ASN of a prefix.
  origin_asn: int
  # number of RC peer ASNs observing pfx.
  vis_asn: int
  # number of RC peer nexthop addresses observing pfx.
  vis_nhop: int


@dataclass
class Snapshot:
  # The populated Trie
  pyt: PyTricia
  # IP version, either 4 or 6
  version: int
  # max number of RC peer ASNs observing single pfx.
  max_vis_asn: int
  # max number of RC peer nexthop addresses observing single pfx.
  max_vis_nhop: int

  def remove_low_vis_pfxs(self, vis_frac: float) -> int:
    """Removes low visibility prefixes from this Snapshot.

    Args:
      vis_frac (float): the fraction of RC peer ASNs and nexthop
        addresses required for the prefix to remain in the trie
        after the removal. If either ASN or nexthop count are not
        met, the prefix is removed.

    Returns:
      int: The number of removed prefixes.

    Raises:
      ValueError: If vis_frac is not within [0|1) interval.
    """
    if not (0.0 <= vis_frac < 1.0):
      raise ValueError("vis_frac must be in interval [0|1), yet is: %f", vis_frac)

    # Calculate thresholds.
    thresh_asn = int(self.max_vis_asn * vis_frac)
    thresh_nhop = int(self.max_vis_nhop * vis_frac)

    # Collect pfxs to remove. 
    to_remove = []
    for pfx in self.pyt:
      meta = self.pyt.get(pfx)
      if meta.vis_asn >= thresh_asn and meta.vis_nhop >= thresh_nhop:
        continue
      to_remove.append(pfx)

    # Remove pfxs from trie.
    for pfx in to_remove:
      del self.pyt[pfx]

    # return number of removed prefixes.
    return len(to_remove)

def load_pfx_tries(fn: str) -> Tuple[Snapshot, Snapshot]:
  pyt4, pyt6 = PyTricia(32), PyTricia(128)
  max_vis_asn_v4, max_vis_asn_v6, max_vis_nhop_v4, max_vis_nhop_v6 = 0, 0, 0, 0
  with bz2.open(fn, "rt") as fh:
    for i, line in enumerate(fh):
      # skip over comments.
      if line.startswith("#"):
        continue

      # remove white spaces and newlines.
      line = line.rstrip()

      # parse column format
      pfx_raw, *vals = line.split(",")
      if not pfx_raw or len(vals) != 3:
        logger.error(
          "Insufficient number of columns in line %d:%s.",
          i,
          line,
        )
        continue

      # type checks for values.
      try:
        asn, vis_asn, vis_nhop = [int(x) for x in vals]
      except ValueError as e:
        logger.error(
          "Received error '%s' while parsing values in line %d:%s.",
          e.String(),
          i,
          line,
        )
        continue

      # type checks for pfx.
      try:
        pfx = ipaddress.ip_network(pfx_raw)
      except ValueError as e:
        logger.error(
          "Received error '%s' while parsing prefix in line %d:%s.",
          e.String(),
          i,
          line,
        )
        continue

      # add details to pytricia.
      details = PytMeta(asn, vis_asn, vis_nhop)
      pyt = pyt4 if pfx.version == 4 else pyt6

      # if moas, keep the more visible prefix.
      if pyt.has_key(pfx) and pyt.get(pfx).vis_asn > details.vis_asn:
        continue
      pyt.insert(pfx, details)

      # update max observability values.
      if pfx.version == 4:
        max_vis_asn_v4 = max(max_vis_asn_v4, vis_asn)
        max_vis_nhop_v4 = max(max_vis_nhop_v4, vis_nhop)
      else:
        max_vis_asn_v6 = max(max_vis_asn_v6, vis_asn)
        max_vis_nhop_v6 = max(max_vis_nhop_v6, vis_nhop)

  return (
    Snapshot(pyt4, 4, max_vis_asn_v4, max_vis_nhop_v4),
    Snapshot(pyt6, 6, max_vis_asn_v6, max_vis_nhop_v6),
  )


if __name__ == "__main__":
  fn = "../../../pfx2origin/output/2013-01/pfx2as_2013-01-01.bz2"
  (snap4, snap6) = load_pfx_tries(fn)
  cnt = len(snap4.pyt)
  rcnt = snap4.remove_low_vis_pfxs(0.67)
  print(f"removed {rcnt} of initially {cnt} IPv4 prefixes.")
  cnt = len(snap6.pyt)
  rcnt = snap6.remove_low_vis_pfxs(0.67)
  print(f"removed {rcnt} of initially {cnt} IPv6 prefixes.")


