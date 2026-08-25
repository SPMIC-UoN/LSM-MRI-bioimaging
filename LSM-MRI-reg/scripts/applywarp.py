#!/usr/bin/env python
# -*- coding: utf-8 -*-

#   _______ _____ _____  _                    _       _
#  |__   __|_   _|  __ \| |                  (_)     | |
#     | |    | | | |__) | |     ___  ___ _ __ _ _ __ | |_ ___
#     | |    | | |  _  /| |    / __|/ __| '__| | '_ \| __/ __|
#     | |   _| |_| | \ \| |____\__ \ (__| |  | | |_) | |_\__ \
#     |_|  |_____|_|  \_\______|___/\___|_|  |_| .__/ \__|___/
#                                              | |
#                                              |_|
#
# Copyright (C) 2018-2024 University of Oxford
# Part of the FMRIB Software Library (FSL)
# Author: Istvan N. Huszar


# SHBASECOPYRIGHT


"""
Applies a physical transformation to a NIfTI volume.

"""

__tirlscript__ = "stanford.applywarp"


# IMPORTS

import sys
import argparse
import numpy as np
import nibabel as nib

# TIRL IMPORTS

import tirl
from tirl.timage import TImage
from tirl.interpolation.scipyinterpolator import ScipyInterpolator
from tirl.interpolation.scipyinterpolator import ScipyRegularGridInterpolator


# DEFINITIONS

IPOL_METHODS = ("nearest", "linear", "cubic", "quintic")


# IMPLEMENTATION

def main(args):

    if isnifti(args.source):
        source = TImage(args.source, external="affine")
    else:
        source = TImage(args.source)
    if isnifti(args.target):
        target = TImage(args.target, external="affine")
    else:
        target = TImage(args.target)

    chain = tirl.load(args.warp)
    _set_interpolator(source, args.interpolation)
    _set_interpolator(target, args.interpolation)
    res = warp(source, target, chain)
    if args.output.endswith(".timg"):
        res.save(args.output, overwrite=False)
    elif args.output.endswith((".nii", ".nii.gz")):
        _snapshot(res, args.output)
    else:
        res.snapshot(args.output, overwrite=False)


def isnifti(f):
    return str(f).lower().endswith((".nii", ".nii.gz"))


def warp(source, target, chain=None):
    if chain is not None:
        target.domain.external += chain
    result = source.evaluate(target.domain)
    # result.domain = result.domain[:, :1]
    return result


def _snapshot(img, fname):
    affine = np.eye(4)
    chain = (img.domain.internal + img.domain.external[:1]).reduce()
    assert len(chain) == 1, "Unexpected transformation chain configuration."
    affine[:3] = chain[0].matrix
    nifti = nib.Nifti1Image(img.data, affine)
    nib.save(nifti, fname)


def _set_interpolator(img, method):
    assert isinstance(method, str)
    method = method.lower()

    if method == "nearest":
        ip = ScipyRegularGridInterpolator(method="nearest")
    elif method == "linear":
        ip = ScipyRegularGridInterpolator(method="linear")
        # ip = ScipyInterpolator(order=1, prefilter=True)
    elif method == "cubic":
        ip = ScipyInterpolator(order=3, prefilter=True)
    elif method == "quintic":
        ip = ScipyInterpolator(order=5, prefilter=True)
    else:
        raise ValueError(f"Unrecognised interpolator specification: {method}")
    img.interpolator = ip


def create_cli():
    parser = argparse.ArgumentParser(prog="applywarp")

    parser.add_argument(
        "-i", "--source", type=str,
        help="Source (input) image that will be warped.")
    parser.add_argument(
        "-r", "--target", type=str,
        help="Target image, used as a field-of-view reference.")
    parser.add_argument(
        "-w", "--warp", type=str,
        help="TIRL image transformation chain (*.img.chain).")
    parser.add_argument(
        "-o", "--output", type=str,
        help="Output file name (*.timg or *.nii or *.nii.gz).")
    parser.add_argument(
        "--interpolation", type=str, required=False, default="linear",
        help=f"Interpolation method: {IPOL_METHODS}")

    return parser


if __name__ == "__main__":
    parser = create_cli()
    if len(sys.argv[1:]) > 0:
        args = parser.parse_args()
        main(args)
    else:
        parser.print_help()
