# Brand files

Every logo and icon file here is made by one script, `build_logo.py`, from one
definition: the Manrope ExtraBold letters plus two custom peak shapes (the M and the A).
The letters are turned into shapes, so the files look the same on any computer, with or
without the font installed.

To change the logo, change the definition at the top of `build_logo.py` and run it
(`python brand/build_logo.py`, needs `fonttools` and `uharfbuzz`). It rewrites every SVG;
the PNGs are rendered from those SVGs. Never hand-edit an SVG, or the set drifts apart.

What each file is for, and the story behind the logo, are in `docs/BRAND.md`.
`fonts/` holds Manrope and its license (SIL Open Font License, free to use and share).
