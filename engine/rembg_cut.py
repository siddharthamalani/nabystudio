#!/usr/bin/env python3
"""AI cut-out with rembg (MIT, github.com/danielgatis/rembg), run in tools/cutout_env.
  tools/cutout_env/bin/python engine/rembg_cut.py in.png out.png [model]
Models are stored in tools/models/u2net."""
import os, sys
os.environ.setdefault("U2NET_HOME", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "models", "u2net"))
from rembg import remove, new_session
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]; model = sys.argv[3] if len(sys.argv) > 3 else "isnet-general-use"
out = remove(Image.open(src).convert("RGB"), session=new_session(model), post_process_mask=True)
out.save(dst); print("ok", dst)
