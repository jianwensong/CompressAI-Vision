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

"""Convert from MPEG/VCM format to OpenImageV6 that can be read with fiftyone

This is the official OpenImageV6 dir structure:
```
├── data [5000 entries exceeds filelimit, not opening dir]
├── labels
│   ├── classifications.csv # image-level annotations
│   ├── detections.csv  # bbox annotations
│   ├── masks (several subdirectories)
|   |      0/, 1/, 2/, ..  each directory with lots of png images featuring the masks
|   |      A/, B/, C/, ..
|   |
│   ├── relationships.csv
│   └── segmentations.csv # segmentations
|       [MaskPath,ImageID,LabelName,BoxID,BoxXMin,BoxXMax,BoxYMin,BoxYMax,PredictedIoU,Clicks]
|        MaskPath refers to png files in that masks directory (omitting directories 0/, 1/, etc.?)
|
└── metadata
    ├── attributes.csv
    ├── classes.csv     # all classes for image level labels (and bboxes?)
    ├── hierarchy.json
    ├── image_ids.csv
    └── segmentation_classes.csv # all classes for segmentation
```

For minimal bbox detection problem, this is sufficient:
```
.
├── data -> ../../images
├── labels
│   └── detections.csv
└── metadata
    └── classes.csv
```

"""

import glob
import os
import pathlib
import shutil

from pathlib import Path


def imageIdFileList(*args):
    """Just list arguments of .lst files.  They will be combined together.

    ::

        imageIdFileIt(first.lst, second.lst, ..)

    .lst file format is:

    ::

        bef50424c62d12c5.jpg
        c540d9c96b6a79a2.jpg
        a1b20ed591193c06.jpg
        945d6f685752e31b.jpg
        d18700eda95548c8.jpg
        ...

    """
    lis = []
    for fname in args:
        assert os.path.exists(fname), "can't find file " + fname
        with open(fname, "r") as source:
            for line in source:  # bef50424c62d12c5.jpg, ..
                ImageID = line.strip().split(".")[0]  # bef50424c62d12c5
                # yield ImageID # we're an iterator # nopes..
                if ImageID not in lis:
                    lis.append(ImageID)
    return lis


def MPEGVCMToOpenImageV6(  # noqa: C901
    validation_csv_file: str = None,  # detection_validation_labels_5k.csv # OR # segmentation_validation_labels_5k.csv # image-level labels
    list_file: str = None,  # detection_validation_input_5k.lst
    bbox_csv_file: str = None,  # detection_validation_5k_bbox.csv # OR # segmentation_validation_bbox_5k.csv # OPTIONAL
    segmentation_csv_file: str = None,  # segmentation_validation_masks_5k.csv # OPTIONAL # TODO
    output_directory: str = None,
    data_dir: str = None,
    mask_dir: str = None,
    link=True,
    verbose=False,
    append_mask_dir=None,
):
    """From MPEG/VCM input file format to proper OpenImageV6 format

    :param validation_csv_file: MPEG/VCM image-level labels (typically ``detection_validation_labels_5k.csv`` or ``segmentation_validation_labels_5k.csv``)
    :param list_file: MPEG/VCM image list (typically ``detection_validation_input_5k.lst`` or ``segmentation_validation_input_5k.lst``)
    :param bbox_csv_file: MPEG/VCM detection input file (typically ``detection_validation_5k_bbox.csv`` or ``segmentation_validation_bbox_5k.csv``)
    :param seg_masks_csv_file: MPEG/VCM segmentation input file (typically ``segmentation_validation_masks_5k.csv``)
    :param output_directory: Path where the OpenImageV6 formatted files are dumped
    :param data_dir: Source directory where the image jpg files are.  Use the standard OpenImageV6 directory.
    :param mask_dir: Source directory where the mask png files are.  Use the standard OpenImageV6 directory.
    :param link: True (default): create a softlink from source data_dir to target data_dir.  False: copy all images to target.

    More details on the conversion follow

    ``bbox_csv_file``: A filename (``detection_validation_5k_bbox.csv``) with the MPEG/VCM format that looks like this:

    ::

        ImageID,LabelName,XMin,XMax,YMin,YMax,IsGroupOf
        bef50424c62d12c5,airplane,0.15641026,0.8282050999999999,0.16284987,0.82188296,0
        c540d9c96b6a79a2,person,0.4421875,0.5796875,0.67083335,0.84791666,0
        ...

    --> Converted to proper OpenImageV6 format:

    ::

        ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside
        ...

    ``seg_masks_csv_file``: A filename (``segmentation_validation_masks_5k.csv``) with the MPEG/VCM format that looks like this:

    ::

        ImageID,LabelName,ImageWidth,ImageHeight,XMin,YMin,XMax,YMax,IsGroupOf,Mask,MaskPath
        001464cfae2a30b8,sandwich,1024,683,0.261062,0.245575,0.681416,0.573009,0,eNqtlNlSwzAMR..GtiA5L,001464cfae2a30b8_m0cdn1_5fa59bf3.png
        ...


    We're using mask bitmaps from the original OpenImageV6 image set, i.e. we're omitting that "Mask" column that seems to be a byte blob encoded in some way

    --> Converted to proper OpenImageV6 format:

    ::

        MaskPath,ImageID,LabelName,BoxID,BoxXMin,BoxXMax,BoxYMin,BoxYMax,PredictedIoU,Clicks
        114d6b81e7b1fa08_m01bl7v_b62eb236.png,114d6b81e7b1fa08,/m/01bl7v,b62eb236,0.036101,0.332130,0.099278,0.888087,0.00000
        ...


    ``validation_csv_file`` = ``detection_validation_labels_5k.csv`` looks like this:

    ::

        ImageID,LabelName,Confidence
        0001eeaf4aed83f9,airplane,1
        000a1249af2bc5f0,person,1
        001083f05db4352b,car,1
        00146ba1e50ed8d8,person,1
        ...

    --> Converted to proper OpenImageV6 format (into ``classifications.csv``):

    ::

        ImageID,Source,LabelName,Confidence
        0001eeaf4aed83f9,verification,/m/0cmf2,1
        0004886b7d043cfd,verification,/m/01g317,0
        0004886b7d043cfd,verification,/m/04hgtk,0
        0004886b7d043cfd,verification,/m/09j2d,0
        ...


    ``output_directory``: Path to where the OpenImageV6 formatted files are dumped.  Files under that path are:

    ::

        .
        ├── data : --> softlink to original images
        ├── labels
        │   └── detections.csv          (converted from 'detection_validation_5k_bbox.csv' / 'segmentation_validation_bbox_5k.csv') # bbox_csv_file
        |       classifications.csv     (converted from 'detection_validation_labels_5k.csv' / 'segmentation_validation_labels_5k.csv') # validation_csv_file # image-level labels
        |       segmentations.csv       (converted from 'segmentation_validation_masks_5k.csv')
        |       masks/  --> softlink to original mask png files
        └── metadata
            └── classes.csv             take all possible classes from classifications.csv

    In particular, ``detections.csv`` has this format:

    ::

        ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside
        0001eeaf4aed83f9,source,tag,1,0.022673031,0.9642005,0.07103825,0.80054647,0,0,0,0,0
        ...
    """
    assert (
        validation_csv_file is not None
    ), "you _must_ provide at least MPEG/VCM-formatted image-level labels csv file, aka 'detection_validation_labels_5k.csv'"
    # assert(bbox_csv_file is not None), "please provide MPEG/VCM-formatted bbox csv file, aka 'detection_validation_5k_bbox.csv'" # OPT

    assert output_directory is not None, "please provide output root directory"
    assert data_dir is not None, "please provide data_dir where the images are located"

    # input path etc. check
    assert os.path.exists(validation_csv_file), (
        "file " + validation_csv_file + " does not exist"
    )
    if bbox_csv_file is not None:
        assert os.path.exists(bbox_csv_file), (
            "file " + bbox_csv_file + " does not exist"
        )
    if segmentation_csv_file is not None:
        assert os.path.exists(segmentation_csv_file), (
            "file " + segmentation_csv_file + " does not exist"
        )
        assert (
            mask_dir is not None
        ), "please provide mask_dir where the mask images are located (typically at labels/masks of your main OpenImageV6 dir)"
        assert os.path.exists(mask_dir), "directory " + mask_dir + " does not exist"

    assert os.path.exists(data_dir), "directory " + data_dir + " does not exist"
    if list_file is not None:
        assert os.path.exists(list_file), "file " + list_file + " does not exist"

    # target directories & files
    if os.path.exists(output_directory):
        print("WARNING: directory " + output_directory + " already exists")

    metadata_dir = os.path.join(output_directory, "metadata")
    # metadata/
    classes_csv = os.path.join(metadata_dir, "classes.csv")
    segmentation_classes_csv = os.path.join(
        metadata_dir, "segmentation_classes.csv"
    )  # TODO
    attributes_csv = os.path.join(metadata_dir, "attributes.csv")
    image_ids_csv = os.path.join(metadata_dir, "image_ids.csv")

    labels_dir = os.path.join(output_directory, "labels")
    # labels/
    detections_csv = os.path.join(labels_dir, "detections.csv")
    segmentations_csv = os.path.join(labels_dir, "segmentations.csv")
    classifications_csv = os.path.join(labels_dir, "classifications.csv")

    target_data_dir = os.path.join(output_directory, "data")
    target_mask_dir = os.path.join(output_directory, "labels", "masks")
    if append_mask_dir is not None:
        """For custom formats, user might provide a segmask dir without
        the 0/, 1/, etc. subdirectories

        So let's create labels/masks and link from labels/masks/0 -> segmask dir
        """
        os.makedirs(target_mask_dir, exist_ok=True)  # labels/masks
        # new link: labels/masks/0
        target_mask_dir = os.path.join(
            output_directory, "labels", "masks", append_mask_dir
        )

    if verbose:
        print("creating dirs")
    for d in [labels_dir, metadata_dir]:
        pathlib.Path(d).mkdir(parents=True, exist_ok=True)
    # all ready to go
    # get all existing labels

    if verbose:
        print("reading classes from", validation_csv_file)
    # can we safely assume that all used class labels are in the validation aka image-level annotation file?
    with open(validation_csv_file, "r") as f:
        f.readline()  # read the header line away: ImageID,LabelName,Confidence
        classes = []
        for line in f:
            name = line.strip().split(",")[1]
            # WARNING: MPEG/VCM input files include corrupt label names, i.e. "cell_phone"
            # instead of "cell phone" as understood by COCO-trained detectors
            # why provide such corrupt input files.. no idea. In the original MPEG/VCM pipeline, these labels are corrected "on-the-fly"
            name = name.replace("_", " ")
            if name not in classes:
                classes.append(name)

    if verbose:
        print("got classes", classes)

    # write classes.csv
    if verbose:
        print("writing", classes_csv)
    with open(classes_csv, "w") as f:
        for class_ in classes:
            f.write(class_ + "," + class_ + "\n")

    if segmentation_csv_file is not None:
        if verbose:
            print("writing", segmentation_classes_csv)
        with open(segmentation_classes_csv, "w") as f:
            for class_ in classes:
                f.write(class_ + "\n")

    with open(attributes_csv, "w") as f:
        f.write("nada,nada\n")

    if list_file is not None:
        with open(list_file, "r") as source:
            with open(image_ids_csv, "w") as target:
                target.write(
                    "ImageID,Subset,OriginalURL,OriginalLandingURL,License,AuthorProfileURL,Author,Title,OriginalSize,OriginalMD5,Thumbnail300KURL,Rotation\n"
                )
                for line in source:  # bef50424c62d12c5.jpg, ..
                    ImageID = line.strip().split(".")[0]  # bef50424c62d12c5
                    # and yes, all info is lost / not provided by MPEG/VCM files
                    Subset = "nada"
                    OriginalURL = "nada"
                    OriginalLandingURL = "nada"
                    License = "nada"
                    AuthorProfileURL = "nada"
                    Author = "John Doe"
                    Title = "nada"
                    OriginalSize = "nada"
                    OriginalMD5 = "nada"
                    Thumbnail300KURL = "nada"
                    Rotation = "0.0"
                    target.write(
                        ",".join(
                            (
                                ImageID,
                                Subset,
                                OriginalURL,
                                OriginalLandingURL,
                                License,
                                AuthorProfileURL,
                                Author,
                                Title,
                                OriginalSize,
                                OriginalMD5,
                                Thumbnail300KURL,
                                Rotation,
                            )
                        )
                        + "\n"
                    )
    else:  # no list file provided! but we still need image_ids.json
        with open(image_ids_csv, "w") as target:
            target.write(
                "ImageID,Subset,OriginalURL,OriginalLandingURL,License,AuthorProfileURL,Author,Title,OriginalSize,OriginalMD5,Thumbnail300KURL,Rotation\n"
            )
            # print(">>>", data_dir)
            for img_file_path in glob.glob(os.path.join(data_dir, "*")):
                p = Path(img_file_path)  # /path/to/some.jpg
                ImageID = p.stem  # some
                suffix = p.suffix  # .jpg
                # print(">>>>>", ImageID, suffix)
                if suffix not in [".png", ".jpg"]:
                    print("WARNING: omitting file", img_file_path)
                    continue
                Subset = "nada"
                OriginalURL = "nada"
                OriginalLandingURL = "nada"
                License = "nada"
                AuthorProfileURL = "nada"
                Author = "John Doe"
                Title = "nada"
                OriginalSize = "nada"
                OriginalMD5 = "nada"
                Thumbnail300KURL = "nada"
                Rotation = "0.0"
                target.write(
                    ",".join(
                        (
                            ImageID,
                            Subset,
                            OriginalURL,
                            OriginalLandingURL,
                            License,
                            AuthorProfileURL,
                            Author,
                            Title,
                            OriginalSize,
                            OriginalMD5,
                            Thumbnail300KURL,
                            Rotation,
                        )
                    )
                    + "\n"
                )
    if verbose:
        print("reading", validation_csv_file, "and writing", classifications_csv)
    with open(validation_csv_file, "r") as source:
        source.readline()  # ImageID,LabelName,Confidence
        with open(classifications_csv, "w") as target:
            target.write("ImageID,Source,LabelName,Confidence\n")
            for inp in source:
                row = inp.split(",")  # ImageID,LabelName,Confidence
                row = [r.strip() for r in row]
                ImageID, LabelName, Confidence = row
                Source = "mpeg_vcm"
                # WARNING: MPEG/VCM input files include corrupt label names, i.e. "cell_phone"
                # instead of "cell phone" as understood by COCO-trained detectors
                # why provide such corrupt input files.. no idea. In the original MPEG/VCM pipeline, these labels are corrected "on-the-fly"
                LabelName = LabelName.replace("_", " ")
                target.write(",".join((ImageID, Source, LabelName, Confidence)) + "\n")

    # used_image_ids=[] # keep track of necessary images
    if bbox_csv_file is not None:
        if verbose:
            print("reading", bbox_csv_file, "and writing", detections_csv)
        with open(bbox_csv_file, "r") as source:
            source.readline()  # ImageID,LabelName,XMin,XMax,YMin,YMax,IsGroupOf
            # MPEG/VCM format:
            # ImageID,LabelName,XMin,XMax,YMin,YMax,IsGroupOf
            # bef50424c62d12c5,airplane,0.15641026,0.8282050999999999,0.16284987,0.82188296,0
            # c540d9c96b6a79a2,person,0.4421875,0.5796875,0.67083335,0.84791666,0
            with open(detections_csv, "w") as target:
                # ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside
                # 0001eeaf4aed83f9,xclick,/m/0cmf2,1,0.022673031,0.9642005,0.07103825,0.80054647,0,0,0,0,0
                target.write(
                    "ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside\n"
                )
                for inp in source:
                    row = inp.split(
                        ","
                    )  # ImageID,LabelName,XMin,XMax,YMin,YMax,IsGroupOf
                    row = [r.strip() for r in row]
                    ImageID, LabelName, XMin, XMax, YMin, YMax, IsGroupOf = row
                    # missing stuff
                    Source = "mpeg_vcm"
                    Confidence = "1"
                    IsOccluded = "0"  # petty this information is lots..
                    IsTruncated = "0"
                    # IsGroupOf="0" # don't change this!
                    IsDepiction = "0"
                    IsInside = "0"
                    # WARNING: MPEG/VCM input files include corrupt label names, i.e. "cell_phone"
                    # instead of "cell phone" as understood by COCO-trained detectors
                    # why provide such corrupt input files.. no idea.  In the original MPEG/VCM pipeline, these labels are corrected "on-the-fly"
                    LabelName = LabelName.replace("_", " ")
                    target.write(
                        ",".join(
                            (
                                ImageID,
                                Source,
                                LabelName,
                                Confidence,
                                XMin,
                                XMax,
                                YMin,
                                YMax,
                                IsOccluded,
                                IsTruncated,
                                IsGroupOf,
                                IsDepiction,
                                IsInside,
                            )
                        )
                        + "\n"
                    )
                    """this is up to the dataset provider to define!
                        if ImageID not in used_image_ids:
                            used_image_ids.append(ImageID)
                        """

    if segmentation_csv_file is not None:
        if verbose:
            print("reading", segmentation_csv_file, "and writing", segmentations_csv)
        with open(segmentation_csv_file, "r") as source:
            source.readline()
            # ImageID,LabelName,ImageWidth,ImageHeight,XMin,YMin,XMax,YMax,IsGroupOf,Mask,MaskPath
            with open(segmentations_csv, "w") as target:
                target.write(
                    "MaskPath,ImageID,LabelName,BoxID,BoxXMin,BoxXMax,BoxYMin,BoxYMax,PredictedIoU,Clicks\n"
                )
                for inp in source:
                    row = inp.split(
                        ","
                    )  # ImageID,LabelName,XMin,XMax,YMin,YMax,IsGroupOf
                    row = [r.strip() for r in row]
                    (
                        ImageID,
                        LabelName,
                        ImageWidth,
                        ImageHeight,
                        XMin,
                        YMin,
                        XMax,
                        YMax,
                        IsGroupOf,
                        Mask,
                        MaskPath,
                    ) = row
                    # BoxID: 001464cfae2a30b8_m0cdn1_5fa59bf3.png == ImageID_xxx_BoxID.png
                    BoxID = MaskPath.split("_")[-1].split(".")[0]  # 5fa59bf3
                    BoxXMin = XMin  # I guess..?
                    BoxXMax = XMax
                    BoxYMin = YMin
                    BoxYMax = YMax
                    PredictedIoU = "0.0"  # lost information..
                    Clicks = "0.0"  # lost information..
                    # WARNING: MPEG/VCM input files include corrupt label names, i.e. "cell_phone"
                    LabelName = LabelName.replace("_", " ")
                    target.write(
                        ",".join(
                            (
                                MaskPath,
                                ImageID,
                                LabelName,
                                BoxID,
                                BoxXMin,
                                BoxXMax,
                                BoxYMin,
                                BoxYMax,
                                PredictedIoU,
                                Clicks,
                            )
                        )
                        + "\n"
                    )

    # pathlib.Path(target_data_dir).mkdir(parents=True, exist_ok=True) # not this

    """
    if os.path.exists(target_data_dir):
        print(
            "WARNING: the target data_dir (image directory) already exists.  Will leave as is"
        )
        print("DONE!")
        return

    if (segmentation_csv_file is not None) and os.path.exists(target_mask_dir):
        print(
            "WARNING: the target mask_dir (segmentation mask image directory) already exists.  Will leave as is"
        )
        print("DONE!")
        return
    """
    if link:
        if verbose:
            print("linking image dir", data_dir, "to", target_data_dir)
        if os.path.islink(target_data_dir):
            print("WARNING: link", target_data_dir, "exist already.  Will remove")
            os.remove(target_data_dir)
        os.symlink(data_dir, target_data_dir)
        if segmentation_csv_file is not None:
            if os.path.islink(target_mask_dir):
                print("WARNING: link", target_mask_dir, "exist already.  Will remove")
                os.remove(target_mask_dir)
            os.symlink(mask_dir, target_mask_dir)
    else:
        if verbose:
            print(
                "copying image dir",
                data_dir,
                "to",
                target_data_dir,
                "this might take a while..",
            )
        shutil.copytree(data_dir, target_data_dir)
        if segmentation_csv_file is not None:
            if verbose:
                print(
                    "copying segmentation mask image dir",
                    mask_dir,
                    "to",
                    target_mask_dir,
                    "this might take a while..",
                )
            shutil.copytree(mask_dir, target_mask_dir)

    print("DONE!")
