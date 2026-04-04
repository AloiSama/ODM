# OpenDroneMap - output_parsers.py
# Regex-based parsers for extracting progress from external tool output
#
# Copyright (c) OpenDroneMap Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import re

def parse_openmvs_densify(line):
    """Parse OpenMVS DensifyPointCloud output for progress."""
    # Match: "Depth-maps estimated 10/150 (6%)" or similar
    m = re.search(r'(\d+)\s*/\s*(\d+)\s*\(?\s*\d*%?\)?', line)
    if m:
        done = int(m.group(1))
        total = int(m.group(2))
        if total > 0:
            pct = (done / float(total)) * 100.0
            return (pct, 'Depth maps: %d/%d images' % (done, total))

    # Match: "Densified 67%" or similar percentage
    m = re.search(r'(\d+)\s*%', line)
    if m:
        return (float(m.group(1)), None)

    return None


def parse_poisson_recon(line):
    """Parse PoissonRecon output for progress."""
    # Match: "Depth[ 8/ 10]" or similar depth level progress
    m = re.search(r'[Dd]epth\s*\[\s*(\d+)\s*/\s*(\d+)\s*\]', line)
    if m:
        done = int(m.group(1))
        total = int(m.group(2))
        if total > 0:
            pct = (done / float(total)) * 100.0
            return (pct, 'Depth level: %d/%d' % (done, total))

    # Match performance timing lines
    m = re.search(r'#\s+(\w[\w\s]+):\s+([\d.]+)\s*\(s\)', line)
    if m:
        return None  # timing info, not progress

    return None


def parse_texrecon(line):
    """Parse MVS-Texturing (texrecon) output for progress."""
    # Match: "Generating texture views (150/300)"
    m = re.search(r'\(\s*(\d+)\s*/\s*(\d+)\s*\)', line)
    if m:
        done = int(m.group(1))
        total = int(m.group(2))
        if total > 0:
            pct = (done / float(total)) * 100.0
            return (pct, 'Views: %d/%d' % (done, total))

    return None


def parse_orthophoto(line):
    """Parse odm_orthophoto output for progress."""
    # Match: "Writing: 45%" or "Progress: 45%"
    m = re.search(r'(\d+)\s*%', line)
    if m:
        return (float(m.group(1)), None)

    return None


def parse_opensfm(line):
    """Parse OpenSfM output for progress."""
    # Match: "Matching image 45/150" or similar per-image lines
    m = re.search(r'[Mm]atching\s+.*?(\d+)\s*/\s*(\d+)', line)
    if m:
        done = int(m.group(1))
        total = int(m.group(2))
        if total > 0:
            pct = (done / float(total)) * 100.0
            return (pct, 'Matching: %d/%d pairs' % (done, total))

    # Match: "Detecting features in image 45/150"
    m = re.search(r'[Dd]etect.*?(\d+)\s*/\s*(\d+)', line)
    if m:
        done = int(m.group(1))
        total = int(m.group(2))
        if total > 0:
            pct = (done / float(total)) * 100.0
            return (pct, 'Features: %d/%d images' % (done, total))

    # Match: "Reconstructing image 45/150"
    m = re.search(r'[Rr]econstructi.*?(\d+)\s*/\s*(\d+)', line)
    if m:
        done = int(m.group(1))
        total = int(m.group(2))
        if total > 0:
            pct = (done / float(total)) * 100.0
            return (pct, 'Reconstructing: %d/%d images' % (done, total))

    # Match: "Undistorting image 45/150"
    m = re.search(r'[Uu]ndistort.*?(\d+)\s*/\s*(\d+)', line)
    if m:
        done = int(m.group(1))
        total = int(m.group(2))
        if total > 0:
            pct = (done / float(total)) * 100.0
            return (pct, 'Undistorting: %d/%d images' % (done, total))

    return None


def parse_dem(line):
    """Parse DEM generation (renderdem) output for progress."""
    # Match percentage patterns
    m = re.search(r'(\d+)\s*%', line)
    if m:
        return (float(m.group(1)), None)

    return None


def parse_generic_pct(line):
    """Fallback: match any bare percentage pattern in output."""
    m = re.search(r'(\d+)\s*%', line)
    if m:
        pct = float(m.group(1))
        if 0 < pct <= 100:
            return (pct, None)
    return None


# Stage name -> parser function mapping
STAGE_PARSERS = {
    'openmvs': parse_openmvs_densify,
    'odm_meshing': parse_poisson_recon,
    'mvs_texturing': parse_texrecon,
    'odm_orthophoto': parse_orthophoto,
    'opensfm': parse_opensfm,
    'odm_dem': parse_dem,
}


def parse_line(line, current_stage):
    """Route a subprocess output line to the appropriate parser.

    Returns (progress_pct, detail_text) or None.
    """
    parser = STAGE_PARSERS.get(current_stage)
    if parser:
        result = parser(line)
        if result:
            return result
    return parse_generic_pct(line)
