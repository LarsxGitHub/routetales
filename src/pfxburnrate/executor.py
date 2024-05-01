import argparse
import datetime
import sys
import os

import pfxburnrate

sys.path.append("../ptriediff")
import ptriediff

VIS_FRAC = 0.75
def filepath_from_date(basepath: str, date: datetime.date) -> str:
  fn = date.strftime("%Y-%m/pfx2as_%Y-%m-%d.bz2")
  return os.path.join(basepath, fn)

def res2csv(res: pfxburnrate.BurnRateResult) -> str:
  return f"{res.pfx_cnt_min},{res.pfx_cnt_mean},{res.pfx_cnt_max},{res.pfx_cnt_uniq}"

# parse input args
parser=argparse.ArgumentParser(description="sample argument parser")
parser.add_argument('dir', type=str, help='directory to iterate')
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
  fn = filepath_from_date(args['dir'], date)
  if not os.path.isfile(fn):
    print(f"Error: Expected file {fn} to be available but is not.")
    sys.exit(1)

# actual work
brc4s = pfxburnrate.BurnRateCalculator(args['k'])
brc6s = pfxburnrate.BurnRateCalculator(args['k'])

for date in pfxburnrate.date_iter(args['start'], args['end']):
  fn = filepath_from_date(args['dir'], date)
  snap4, snap6 = ptriediff.load_pfx_tries(fn)
  

  '''
  BurnThroughRatio: #uniq over time/#max over time
  '''
  print(snap4.as_level_split())
  '''
  # filter low-visibility prefixes.
  snap4.remove_low_vis_pfxs(VIS_FRAC)
  print(dir(snap4.pyt))
  snap6.remove_low_vis_pfxs(VIS_FRAC)

  # do the actual calc
  res4 = brc4.advance(snap4.pyt)
  res6 = brc6.advance(snap6.pyt)

  if res4:
    dstr = date.strftime("%Y-%m-%d")
    print(f"{dstr},{args['k']},{res2csv(res4)},{res2csv(res6)}")
  '''
  break

