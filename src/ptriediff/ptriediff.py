from typing import Tuple, DefaultDict
from enum import Enum

import bz2
import ipaddress

import logging

from pytricia import PyTricia
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s|%(levelname)s: %(message)s', filename='last_run.log', filemode='w', level=logging.DEBUG)


# ----------------- DataClasses to track Prefix-level Diff results -----------------


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

  def as_level_split(self) -> DefaultDict[int, PyTricia]:
    split = defaultdict(lambda: PyTricia() if self.version == 4 else PyTricia(128))
    for pfx in self.pyt:
      split[self.pyt.get(pfx).origin_asn].insert(pfx, "")
    return split

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
      raise ValueError(
        "vis_frac must be in interval [0|1), yet is: %f", vis_frac
      )

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

class DiffType(Enum):
  GAIN = 1
  LOSS = 2
  MAIN = 3


@dataclass
class ClassDiff:
  # number of prefixes newly gained in this Class
  gain: int = 0
  # number of prefixes lossed in this Class
  loss: int = 0
  # number of prefixes maintained in this Class
  main: int = 0

  def count_change(self, t: DiffType):
    if t == DiffType.GAIN:
      self.gain += 1
    elif t == DiffType.LOSS:
      self.loss += 1
    elif t == DiffType.MAIN:
      self.main += 1
    else:
      raise ValueError(
        "No counting option associated with unknown DiffType %d."
      )

  def add_diff(self, d: 'ClassDiff'):
    self.gain += d.gain
    self.main += d.main
    self.loss += d.loss

@dataclass
class ClassTracker:
  cnt_pfx: ClassDiff = field(default_factory=ClassDiff)
  # pfx has no direct MSPs.
  has_no_direct_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # pfx has one direct MSPs.
  has_partial_direct_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # pfx has two direct MSPs.
  has_full_direct_msp_coverage: ClassDiff = field(default_factory=ClassDiff)

  # pfx has no (in)direct MSPs.
  has_no_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # pfx has parts of its address space covered by (in)direct MSPs.
  has_partial_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # pfx has its entire address space covered by (in)direct MSPs.
  has_full_msp_coverage: ClassDiff = field(default_factory=ClassDiff)

  # pfx has sibling
  has_sibling: ClassDiff = field(default_factory=ClassDiff)
  # pfx has direct less-specific
  has_direct_less_specific: ClassDiff = field(default_factory=ClassDiff)
  # pfx has (in)direct less-specific
  has_less_specific: ClassDiff = field(default_factory=ClassDiff)



@dataclass
class PfxFowardDiff:
  # count of prefixes in older snapshot.
  cnt_pfx_old: int = 0
  # count of prefixes in newer snapshot.
  cnt_pfx_new: int = 0

  # Classtracker values by CIDR size
  classtracker_by_cidr: DefaultDict[int, ClassTracker] = field(default_factory=lambda: defaultdict(
    ClassTracker
  ))
  # Classtracker for all prefixes
  class_totals: ClassTracker = field(default_factory=ClassTracker)


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


def count_msp_covered_addresses(
  pyt: PyTricia, pfx: ipaddress.ip_network
) -> int:
  # Pytricia's children() and parent() methods return strings instead of network types ...
  pfx_str = str(pfx)
  maxcidr = 32 if pfx.version == 4 else 128

  cnt = 0
  for msp in pyt.children(pfx):
    # ignore pfx itself and msps of msps to avoid overcounting.
    if pyt.parent(msp) != pfx_str:
      continue
    # Calc the addresses in the prefix.
    cnt += 2 ** (maxcidr - int(msp.rsplit("/", 1)[1]))
  return cnt


def has_sibling_in_pyt(pyt: PyTricia, pfx: ipaddress.ip_network) -> bool:
  # turn address into an integer
  base = int(pfx.network_address)

  # flip the bit at the right position
  cidr_max = 32 if pfx.version == 4 else 128
  sib_base = base ^ (2 ** (cidr_max - pfx.prefixlen))

  # turn back into a prefix and check if it exists.
  sib = ipaddress.ip_network((sib_base, pfx.prefixlen))
  return pyt.has_key(sib)


def has_direct_less_specific_in_pyt(
  pyt: PyTricia, pfx: ipaddress.ip_network
) -> bool:

  par = pyt.parent(pfx)
  if par:
    return pfx.prefixlen - int(par.rsplit("/", 1)[1]) == 1
  return False


# ----------------- Functions to Compare Pyts at prefix -----------------


def has_no_direct_msp_coverage(
  old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network
) -> DiffType:
  return matches_to_difftype(
    count_direct_msps(old, pfx) == 0, count_direct_msps(new, pfx) == 0
  )


def has_partial_direct_msp_coverage(
  old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network
) -> DiffType:
  return matches_to_difftype(
    count_direct_msps(old, pfx) == 1, count_direct_msps(new, pfx) == 1
  )


def has_full_direct_msp_coverage(
  old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network
) -> DiffType:
  return matches_to_difftype(
    count_direct_msps(old, pfx) == 2, count_direct_msps(new, pfx) == 2
  )


def combined_has_address_msp_coverage(
  old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network
) -> Tuple[DiffType, DiffType, DiffType]:
  full_cov = pfx.num_addresses
  old_cov = count_msp_covered_addresses(old, pfx)
  new_cov = count_msp_covered_addresses(new, pfx)

  return (
    matches_to_difftype(old_cov == 0, new_cov == 0),
    matches_to_difftype(0 < old_cov < full_cov, 0 < new_cov < full_cov),
    matches_to_difftype(old_cov == full_cov, new_cov == full_cov),
  )


def has_sibling(
  old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network
) -> DiffType:
  return matches_to_difftype(
    has_sibling_in_pyt(old, pfx), has_sibling_in_pyt(new, pfx)
  )


def has_direct_less_specific(
  old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network
) -> DiffType:
  return matches_to_difftype(
    has_direct_less_specific_in_pyt(old, pfx),
    has_direct_less_specific_in_pyt(new, pfx),
  )


def has_less_specific(
  old: PyTricia, new: PyTricia, pfx: ipaddress.ip_network
) -> DiffType:
  return matches_to_difftype(
    old.parent(pfx) is not None, new.parent(pfx) is not None
  )

def forward_count_diff(old: PyTricia, new: PyTricia) -> DefaultDict[int, ClassDiff]:
  diff = defaultdict(lambda: ClassDiff())
  for pfx_str in old:
    pfx = ipaddress.ip_network(pfx_str)
    if new.has_key(pfx_str):
      diff[pfx.prefixlen].count_change(DiffType.MAIN)
    else:
      diff[pfx.prefixlen].count_change(DiffType.LOSS)
  for pfx_str in new:
    if old.has_key(pfx_str):
      continue
    pfx = ipaddress.ip_network(pfx_str)
    diff[pfx.prefixlen].count_change(DiffType.GAIN)
  return diff


def forward_diff_pyts(old: PyTricia, new: PyTricia) -> PfxFowardDiff:
  diff = PfxFowardDiff()

  # Add simple overlap statistics.
  diff.cnt_pfx_old = len(old)
  diff.cnt_pfx_new = len(new)

  # update the count statistics.
  cntdiff = forward_count_diff(old, new)
  for cidr in cntdiff:
    diff.class_totals.cnt_pfx.add_diff(cntdiff[cidr])
    diff.classtracker_by_cidr[cidr].cnt_pfx = cntdiff[cidr]

  for pfx_str in old:
    # is this pfx in both pyts and can be compared?
    if not new.has_key(pfx_str):
      continue

    pfx = ipaddress.ip_network(pfx_str)

    # Calc difftypes
    msp_dir_no = has_no_direct_msp_coverage(old, new, pfx)
    msp_dir_part = has_partial_direct_msp_coverage(old, new, pfx)
    msp_dir_full = has_full_direct_msp_coverage(old, new, pfx)
    cov_no, cov_part, cov_full = combined_has_address_msp_coverage(old, new, pfx)
    sibling = has_sibling(old, new, pfx)
    lsp_dir = has_direct_less_specific(old, new, pfx)
    lsp_cov = has_less_specific(old, new, pfx)

    # tracking total values
    diff.class_totals.has_no_direct_msp_coverage.count_change(msp_dir_no)
    diff.class_totals.has_partial_direct_msp_coverage.count_change(msp_dir_part)
    diff.class_totals.has_full_direct_msp_coverage.count_change(msp_dir_full)
    diff.class_totals.has_no_msp_coverage.count_change(cov_no)
    diff.class_totals.has_partial_msp_coverage.count_change(cov_part)
    diff.class_totals.has_full_msp_coverage.count_change(cov_full)
    diff.class_totals.has_sibling.count_change(sibling)
    diff.class_totals.has_direct_less_specific.count_change(lsp_dir)
    diff.class_totals.has_less_specific.count_change(lsp_cov)

    # tracking per-cidr-size values
    diff.classtracker_by_cidr[pfx.prefixlen].has_no_direct_msp_coverage.count_change(msp_dir_no)
    diff.classtracker_by_cidr[pfx.prefixlen].has_partial_direct_msp_coverage.count_change(msp_dir_part)
    diff.classtracker_by_cidr[pfx.prefixlen].has_full_direct_msp_coverage.count_change(msp_dir_full)
    diff.classtracker_by_cidr[pfx.prefixlen].has_no_msp_coverage.count_change(cov_no)
    diff.classtracker_by_cidr[pfx.prefixlen].has_partial_msp_coverage.count_change(cov_part)
    diff.classtracker_by_cidr[pfx.prefixlen].has_full_msp_coverage.count_change(cov_full)
    diff.classtracker_by_cidr[pfx.prefixlen].has_sibling.count_change(sibling)
    diff.classtracker_by_cidr[pfx.prefixlen].has_direct_less_specific.count_change(lsp_dir)
    diff.classtracker_by_cidr[pfx.prefixlen].has_less_specific.count_change(lsp_cov)

  return diff

@dataclass
class AsLevelFowardDiff:
  # ASes that were observed during first, both, second snapshot 
  asns_observe: ClassDiff = field(default_factory=ClassDiff)

  # Maintained ASes that newly gained prefixes, maintained, and losses pfxs
  asns_pfx_total: ClassDiff = field(default_factory=ClassDiff)

  # ASNs with at least one prefix withour direct msp coverage
  asns_pfx_no_direct_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # ASNs with at least one prefix with partial direct msp coverage
  asns_pfx_partial_direct_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # ASNs with at least one prefix withfull direct msp coverage
  asns_pfx_full_direct_msp_coverage: ClassDiff = field(default_factory=ClassDiff)

  # ASNs with at least one prefix without indirect msp coverage
  asn_pfx_no_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # ASNs with at least one pfx with parts of its address space covered by (in)direct MSPs.
  asn_pfx_partial_msp_coverage: ClassDiff = field(default_factory=ClassDiff)
  # ASNs with at least one pfx with all of its address space covered by (in)direct MSPs.
  asn_pfx_full_msp_coverage: ClassDiff = field(default_factory=ClassDiff)

  # ASNs with at least one pfx with a sibling.
  asn_pfx_sibling: ClassDiff = field(default_factory=ClassDiff)
  # ASNs with at least one pfx with a direct less-specific
  asn_pfx_direct_less_specific: ClassDiff = field(default_factory=ClassDiff)
  # ASNs with at least one pfx with an indirect sibling.
  asn_pfx_less_specific: ClassDiff = field(default_factory=ClassDiff)


def as_forward_diff_pyts(snap_old: Snapshot, snap_new: Snapshot) -> AsLevelFowardDiff:
  diff = AsLevelFowardDiff()
  split_old = snap_old.as_level_split()
  split_new = snap_new.as_level_split()

  # Get total observation difference.
  for asn in split_old:
    if asn in split_new:
      diff.asns_observe.count_change(DiffType.MAIN)
    else:
      diff.asns_observe.count_change(DiffType.LOSS)
  for asn in split_new:
    if asn not in split_old:
      diff.asns_observe.count_change(DiffType.GAIN)

  for asn in split_old:
    # We iterate only over maintained ASNs.
    if asn not in split_new:
      continue

    fwd_pfx_diff = forward_diff_pyts(split_old[asn], split_new[asn])

    # ASNs that gained/maintained/lossed prefixes.
    if fwd_pfx_diff.cnt_pfx_old > fwd_pfx_diff.cnt_pfx_new:
      diff.asns_pfx_total.count_change(DiffType.LOSS)
    elif fwd_pfx_diff.cnt_pfx_old == fwd_pfx_diff.cnt_pfx_new:
      diff.asns_pfx_total.count_change(DiffType.MAIN)
    else:
      diff.asns_pfx_total.count_change(DiffType.GAIN)

    # no direct msps.
    if fwd_pfx_diff.class_totals.has_no_direct_msp_coverage.gain > 0:
      diff.asns_pfx_no_direct_msp_coverage.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_no_direct_msp_coverage.main > 0:
      diff.asns_pfx_no_direct_msp_coverage.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_no_direct_msp_coverage.loss > 0:
      diff.asns_pfx_no_direct_msp_coverage.count_change(DiffType.LOSS)

    # some direct msps.
    if fwd_pfx_diff.class_totals.has_partial_direct_msp_coverage.gain > 0:
      diff.asns_pfx_partial_direct_msp_coverage.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_partial_direct_msp_coverage.main > 0:
      diff.asns_pfx_partial_direct_msp_coverage.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_partial_direct_msp_coverage.loss > 0:
      diff.asns_pfx_partial_direct_msp_coverage.count_change(DiffType.LOSS)

    # some full msps.
    if fwd_pfx_diff.class_totals.has_full_direct_msp_coverage.gain > 0:
      diff.asns_pfx_full_direct_msp_coverage.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_full_direct_msp_coverage.main > 0:
      diff.asns_pfx_full_direct_msp_coverage.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_full_direct_msp_coverage.loss > 0:
      diff.asns_pfx_full_direct_msp_coverage.count_change(DiffType.LOSS)

    # ASNs with at least one prefix without indirect msp coverage
    if fwd_pfx_diff.class_totals.has_no_msp_coverage.gain > 0:
      diff.asn_pfx_no_msp_coverage.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_no_msp_coverage.main > 0:
      diff.asn_pfx_no_msp_coverage.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_no_msp_coverage.loss > 0:
      diff.asn_pfx_no_msp_coverage.count_change(DiffType.LOSS)

    # ASNs with at least one prefix with partial indirect msp coverage
    if fwd_pfx_diff.class_totals.has_partial_msp_coverage.gain > 0:
      diff.asn_pfx_partial_msp_coverage.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_partial_msp_coverage.main > 0:
      diff.asn_pfx_partial_msp_coverage.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_partial_msp_coverage.loss > 0:
      diff.asn_pfx_partial_msp_coverage.count_change(DiffType.LOSS)

    # ASNs with at least one prefix with fullindirect msp coverage
    if fwd_pfx_diff.class_totals.has_full_msp_coverage.gain > 0:
      diff.asn_pfx_full_msp_coverage.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_full_msp_coverage.main > 0:
      diff.asn_pfx_full_msp_coverage.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_full_msp_coverage.loss > 0:
      diff.asn_pfx_full_msp_coverage.count_change(DiffType.LOSS)

    # ASNs with at least one pfx with a sibling.
    if fwd_pfx_diff.class_totals.has_sibling.gain > 0:
      diff.asn_pfx_sibling.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_sibling.main > 0:
      diff.asn_pfx_sibling.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_sibling.loss > 0:
      diff.asn_pfx_sibling.count_change(DiffType.LOSS)

    # ASNs with at least one pfx with a direct less-specific
    if fwd_pfx_diff.class_totals.has_direct_less_specific.gain > 0:
      diff.asn_pfx_direct_less_specific.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_direct_less_specific.main > 0:
      diff.asn_pfx_direct_less_specific.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_direct_less_specific.loss > 0:
      diff.asn_pfx_direct_less_specific.count_change(DiffType.LOSS)

    # ASNs with at least one pfx with an indirect sibling.
    if fwd_pfx_diff.class_totals.has_less_specific.gain > 0:
      diff.asn_pfx_less_specific.count_change(DiffType.GAIN)
    if fwd_pfx_diff.class_totals.has_less_specific.main > 0:
      diff.asn_pfx_less_specific.count_change(DiffType.MAIN)
    if fwd_pfx_diff.class_totals.has_less_specific.loss > 0:
      diff.asn_pfx_less_specific.count_change(DiffType.LOSS)

  return diff 


def load_pfx_tries(fn: str) -> Tuple[Snapshot, Snapshot]:
  logger.info("Starting to read data from %s.", fn)
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

  logger.info("Finished reading data from %s.", fn)
  return (
    Snapshot(pyt4, 4, max_vis_asn_v4, max_vis_nhop_v4),
    Snapshot(pyt6, 6, max_vis_asn_v6, max_vis_nhop_v6),
  )


if __name__ == "__main__":

  fn_old = "../../../pfx2origin/output/2012-01/pfx2as_2012-01-01.bz2"
  fn_new = "../../../pfx2origin/output/2013-01/pfx2as_2013-01-01.bz2"

  (old4, old6) = load_pfx_tries(fn_old)
  (new4, new6) = load_pfx_tries(fn_new)

  vis_frac = 0.75
  for snap in [old4, new4, old6, new6]:
    snap.remove_low_vis_pfxs(vis_frac)

  logger.info("Starting to diff IPv4 pyts.")
  diff = forward_diff_pyts(old4.pyt, new4.pyt)
  print(f"Produced the following diff:\n{diff.cnt_pfx_old}, {diff.cnt_pfx_new}\n{repr(diff.class_totals)}")

  diff = as_forward_diff_pyts(old4, new4)
  print(f"Produced the following as-level diff:\n{repr(diff)}")


