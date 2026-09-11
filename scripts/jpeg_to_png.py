#!/usr/bin/env python3
"""Convert the 4x JPEG masters to lossless PNG, in place, no resizing.

Writes img.png beside each img.jpeg under chapters/4x/ and sloks/4x/.
Same engine as tier_images.py, just pinned to tier 4.

    python3 scripts/jpeg_to_png.py
    python3 scripts/jpeg_to_png.py --roots chapters
"""

import sys

import tier_images

if __name__ == "__main__":
    sys.argv.extend(["--tiers", "4"])
    tier_images.main()
