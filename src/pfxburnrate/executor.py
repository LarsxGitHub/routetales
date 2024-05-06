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

import pfxburnrate

@dataclass
class BurnRateResultsContainer:
  end_date: datetime.datetime
  k: int
  results4: Dict[int, pfxburnrate.BurnRateResult]
  results6: Dict[int, pfxburnrate.BurnRateResult]

sys.path.append("../ptriediff")
import ptriediff

VIS_FRAC = 0.75
def filepath_from_date(basepath: str, date: datetime.date) -> str:
  fn = date.strftime("%Y-%m/pfx2as_%Y-%m-%d.bz2")
  return os.path.join(basepath, fn)

def outdir_from_date(basepath: str, date: datetime.date) -> str:
  fn = date.strftime("%Y-%m/")
  return os.path.join(basepath, fn)

def outfile_from_date(basepath: str, k: int, date: datetime.date) -> str:
  path = os.path.join(basepath, date.strftime("%Y-%m/"))
  fn = f"pbr_{k}_" + date.strftime("%Y-%m-%d.bz2")
  return os.path.join(path, fn)

def res2csv(res: pfxburnrate.BurnRateResult) -> str:
  return f"{res.pfx_cnt_min},{res.pfx_cnt_mean},{res.pfx_cnt_max},{res.pfx_cnt_uniq}"

# parse input args
parser=argparse.ArgumentParser(description="sample argument parser")
parser.add_argument('in_dir', type=str, help='directory to iterate')
parser.add_argument('out_dir', type=str, help='directory to write file into')
parser.add_argument('start', type=datetime.datetime.fromisoformat, help='start date in ISOformat - YYYY-MM-DD:HH:mm:ss')
parser.add_argument('end', type=datetime.datetime.fromisoformat, help='end date in ISOformat - YYYY-MM-DD:HH:mm:ss')
parser.add_argument('k', type =int, help='number of consecutive snapshots')
args=vars(parser.parse_args())

# semantic validation (dates)
if args['start'] > args['end']:
  print(f"Error: Exected start date ({args['start']}) to be earlier than end date ({args['end']}).")
  sys.exit(1)

# semantic validation (files)
for date in pfxburnrate.date_iter(args['start'], args['end']):
  fn = filepath_from_date(args['in_dir'], date)
  if not os.path.isfile(fn):
    print(f"Error: Expected file {fn} to be available but is not.")
    sys.exit(1)

for i, date in enumerate(pfxburnrate.date_iter(args['start'], args['end'])):
  if i < args['k']:
    continue
  path = outdir_from_date(args['out_dir'], date)
  if not os.path.isdir(path):
    print(f"Error: Expected path {path} to be available but is not.")
    sys.exit(1)



brc4 = pfxburnrate.BurnRateCalculator(args['k'])
brc6 = pfxburnrate.BurnRateCalculator(args['k'])


for date in pfxburnrate.date_iter(args['start'], args['end']):
  fn = filepath_from_date(args['in_dir'], date)

  # load snapshots
  snap4, snap6 = ptriediff.load_pfx_tries(fn)

  # filter low-visibility prefixes.
  snap4.remove_low_vis_pfxs(VIS_FRAC)
  snap6.remove_low_vis_pfxs(VIS_FRAC)

  as_split4 = snap4.as_level_split()
  as_split6 = snap6.as_level_split()

  brr4 = brc4.advance(as_split4)
  brr6 = brc6.advance(as_split6)

  # do we already have something to write down?
  if not brr4:
    continue

  rc = BurnRateResultsContainer(date, args['k'], brr4, brr6)
  fn = outfile_from_date(args['out_dir'], args['k'], date)
  with open(fn, "wb") as fh:
    pickle.dump(rc, fh)

  print(f"Wrote results for window size ={args['k']} till date {date} to {fn}.")

