"""Build the .rav package without uploading it (what `main.py deploy` does, minus the upload).

    python tools/build_rav.py [--pyc] [--out overblaster.rav]

Run from the repo root. Needs the Raven framework installed. --pyc compiles to bytecode, which
needs the same Python major.minor as the glasses (see the framework's config.json).
"""

import argparse
import os
import shutil
import sys

from raven_framework.core.deploy_app import deploy_app

ap = argparse.ArgumentParser()
ap.add_argument("--pyc", action="store_true", help="compile to .pyc (deploy-pyc)")
ap.add_argument("--out", default="overblaster.rav")
args = ap.parse_args()

built = deploy_app(app_name="overblaster", compile_pyc=args.pyc)
if not built:
    sys.exit("build failed")
if os.path.abspath(built) != os.path.abspath(args.out):
    shutil.move(built, args.out)
print(f"{args.out}: {os.path.getsize(args.out) / 1e6:.1f} MB")
