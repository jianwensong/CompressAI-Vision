# Copyright (c) 2022-2024 InterDigital Communications, Inc
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted (subject to the limitations in the disclaimer
# below) provided that the following conditions are met:

# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of InterDigital Communications, Inc nor the names of its
#   contributors may be used to endorse or promote products derived from this
#   software without specific prior written permission.

# NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY
# THIS LICENSE. THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
# CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT
# NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import inspect
import logging
import os
import subprocess

from collections import OrderedDict

from PIL import Image


def confLogger(logger, level):
    logger.setLevel(level)
    logger.propagate = False
    # print("confLogger", logger.handlers)
    # print("confLogger", logger.hasHandlers())
    # if not logger.hasHandlers(): # when did this turn into a practical joke?
    logger.handlers = []
    # if len(logger.handlers) < 1:
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def quickLog(name, level):
    logger = logging.getLogger(name)
    confLogger(logger, level)
    return logger


def pathExists(p):
    return os.path.exists(os.path.expanduser(p))


def getModulePath():
    lis = inspect.getabsfile(inspect.currentframe()).split("/")
    st = "/"
    for f in lis[:-1]:
        st = os.path.join(st, f)
    return st


def getDataPath():
    return os.path.join(getModulePath(), "data")


def getDataFile(fname):
    """Return complete path to datafile fname.  Data files are in the directory compressai_vision/"""
    return os.path.join(getDataPath(), fname)


def test_command(comm):
    try:
        subprocess.Popen(
            comm, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except FileNotFoundError:
        raise
    else:
        return comm


def dumpImageArray(arr, dir, name, is_bgr=False):
    os.makedirs(dir, exist_ok=True)
    if is_bgr:
        arr_ = arr[:, :, ::-1]  # BGR --> RGB
    else:
        arr_ = arr
    Image.fromarray(arr_).save(os.path.join(dir, name))


def findMapping(det: list = None, gt: list = None):
    """
    :param det: A list of tags, used by the trained detector i.e. ["cat, "dog",
    "horse", "plant", ..]
    :param gt: List of tags used by the evaluation ground truth set is different
    to det, but however has a notable
    intersection with the det list of tags

    valid/usable tags are the intersection of det & gt

    returns valid_tags: list, mapping: dict

    mapping is a mapping from ground truth class ids to the class ids used by
    the detector

    An example:

    ::

        det = ["cat", "dog", "horse", "plant"]
        gt = ["Car", "Cat", "Dog"]
        ==> mapping = {1:0, 2:1} & valid_tags = ["cat", "dog"]

    Supposing ``train_classes`` & ``gt_classes`` are lists of tags, then:

    ::

        for m1, m2 in mapping.items(): # key, value
            print(m1, gt_classes[m1], "--> ", m2, target_classes[m2])

    gives this output:

    ::

        1 Cat -->  0 cat
        2 Dog -->  1 dog

    You can use mapDataset to go from gt format dataset to detector formatted dataset
    """
    assert det is not None
    assert gt is not None

    # all tags to lowercase
    det = [i.lower() for i in det]
    gt = [i.lower() for i in gt]
    d = OrderedDict()
    ins = set(det).intersection(set(gt))  # {'cat','dog'}
    lis = list(ins)  # ['cat','dog']
    tags = []
    indexes = []

    for i in lis:  # tags intersection
        tags.append(i)
        val = det.index(i)
        key = gt.index(i)
        d[key] = val
        indexes.append(key)
    indexes.sort()
    d_sorted = OrderedDict()
    for i in indexes:
        d_sorted[i] = d[i]
    return tags, d_sorted
