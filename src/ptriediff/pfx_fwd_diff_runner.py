import ptriediff
import argparse
import datetime
import sys
import os
from dataclasses import dataclass
from typing import Dict

try:
    import cPickle as pickle
except:
    import pickle

sys.path.append("../pfxburnrate")
import pfxburnrate


VIS_THRESH = 0.66

ALLOWED_WINDOW_SIZES = {
  "w": datetime.timedelta(days = 7),
  "m": datetime.timedelta(days = 30),
  "y": datetime.timedelta(days = 365),
}

WINDOW_SIZE_NAMES = {
  "w": "Week",
  "m": "Month",
  "y": "Year",
}

WINDOW_SIZES_SORTED = sorted(list(ALLOWED_WINDOW_SIZES.keys()))

@dataclass
class Results:
  pfx_diff: ptriediff.PfxFowardDiff
  asn_diff: ptriediff.AsLevelFowardDiff

@dataclass
class ResultContainer:
  end_date: datetime.datetime
  results: Dict[str, Results]

def outfn_from_date(basepath: str, date: datetime.date) -> str:
  fn = date.strftime("%Y-%m/pfxfwdres_%Y-%m-%d.pkl")
  return os.path.join(basepath, fn)

def filepath_from_date(basepath: str, date: datetime.date) -> str:
  fn = date.strftime("%Y-%m/pfx2as_%Y-%m-%d.bz2")
  return os.path.join(basepath, fn)

def dirpath_from_date(basepath: str, date: datetime.date) -> str:
  dn = date.strftime("%Y-%m")
  return os.path.join(basepath, dn)

def get_start_date(end_date: datetime, window: str) -> datetime:
  return end_date - ALLOWED_WINDOW_SIZES[window]


if __name__ == "__main__":
  
  # parse input args
  parser=argparse.ArgumentParser(description="Foward Prefix Diff Runner")
  parser.add_argument('data_dir', type=str, help='directory to iterate')
  parser.add_argument('out_dir', type=str, help='directory to iterate')
  parser.add_argument('end', type=datetime.datetime.fromisoformat, help='start date in ISOformat - YYYY-MM-DD:HH:mm:ss')
  args=vars(parser.parse_args())

  # get the related start times.
  start_dates = [get_start_date(args['end'], w) for w in WINDOW_SIZES_SORTED]

  # semantic validation (inputs)
  for date in [*start_dates, args['end']]:
    fn = filepath_from_date(args['data_dir'], date)
    if not os.path.isfile(fn):
      print(f"Error: Expected file {fn} to be available but it is not.")
      sys.exit(1)

  # semantic validation (outputs)
  dn = dirpath_from_date(args['out_dir'], args['end'])
  if not os.path.isdir(dn):
    print(f"Error: Expected dir {dn} to be available but it is not.")
    sys.exit(1)

  # load data
  snaps_v4, snaps_v6 = [], []
  for date in [*start_dates, args['end']]:
    # load, filter, and collect the tries.
    sv4, sv6 = ptriediff.load_pfx_tries(filepath_from_date(args['data_dir'], date))
    sv4.remove_low_vis_pfxs(VIS_THRESH)
    sv6.remove_low_vis_pfxs(VIS_THRESH)
    snaps_v4.append(sv4)
    snaps_v6.append(sv6)

  results = {}
  # run actual calculations
  for proto_suffix, snaps in [("IPv6", snaps_v6), ("IPv4", snaps_v4)]:
    # one calc per starting snapshot
    for i, snap in enumerate(snaps[:-1]):
      key = f"{WINDOW_SIZE_NAMES[WINDOW_SIZES_SORTED[i]]}-{proto_suffix}"
      pfx_diff = ptriediff.forward_diff_pyts(snap.pyt, snaps[-1].pyt)
      asn_diff = ptriediff.as_forward_diff_pyts(snap, snaps[-1])
      results[key] = Results(pfx_diff, asn_diff)

  rc = ResultContainer(args['end'], results)
  fn = outfn_from_date(args['out_dir'], args['end'])

  with open(fn, 'wb') as fh:
    pickle.dump(rc, fh)

  print(f"Wrote results for {args['end']} to {fn}")





