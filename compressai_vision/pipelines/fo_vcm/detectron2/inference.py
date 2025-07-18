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

"""Using the Detectron2 library to evaluate encoded/decoded image.  WARNING:
legacy code, should not be use.

This file has been modified from "from
detectron2.evaluation.inference_on_dataset" by Interdigital to include bpp (bits
per pixel) calculations
"""

import datetime
import logging
import time


# from collections import OrderedDict, abc
from contextlib import ExitStack, contextmanager

import torch

from detectron2.evaluation import DatasetEvaluator  # , DatasetEvaluators
from detectron2.utils.comm import get_world_size  # , is_main_process
from detectron2.utils.logger import log_every_n_seconds
from torch import nn

from .tools import filterInstances

# from typing import List, Union


def inference_on_dataset(
    model=None,
    data_loader=None,
    evaluator: DatasetEvaluator = None,
    mapping: dict = None,
):
    """
    Run model on the data_loader and evaluate the metrics with evaluator. Also
    benchmark the inference speed of `model.__call__` accurately. The model will
    be used in eval mode.

    Args:
        model (callable): a callable which takes an object from
            `data_loader` and returns some outputs.

            If it's an nn.Module, it will be temporarily set to `eval` mode. If
            you wish to evaluate a model in `training` mode instead, you can
            wrap the given model and override its behavior of `.eval()` and
            `.train()`.

        data_loader: an iterable object with a length.
            The elements it generates will be the inputs to the model.

        evaluator: the evaluator(s) to run. Use `None` if you only want to
        benchmark,
            but don't want to do any evaluation.

        mapping [optional]: values of this dictionary (which are class id
        numbers) are used to filter the results

    Returns:
        The return value of `evaluator.evaluate()`
    """
    assert issubclass(model.__class__, nn.Module)
    assert issubclass(data_loader.__class__, torch.utils.data.DataLoader)
    assert issubclass(evaluator.__class__, DatasetEvaluator)

    class_list = None
    if mapping is not None:
        class_list = list(mapping.values())

    num_devices = get_world_size()
    logger = logging.getLogger("inference_on_dataset")
    logger.info("Start inference on {} batches".format(len(data_loader)))

    total = len(data_loader)  # inference data loader must have a fixed length
    """
    if evaluator is None:
        # create a no-op evaluator
        evaluator = DatasetEvaluators([])
    if isinstance(evaluator, abc.MutableSequence):
        evaluator = DatasetEvaluators(evaluator)
    """
    evaluator.reset()

    num_warmup = min(5, total - 1)
    start_time = time.perf_counter()
    total_data_time = 0
    total_compute_time = 0
    total_eval_time = 0
    bpp_sum = 0
    cc = 0
    with ExitStack() as stack:
        if isinstance(model, nn.Module):
            stack.enter_context(inference_context(model))
        stack.enter_context(torch.no_grad())

        start_data_time = time.perf_counter()
        for idx, inputs in enumerate(data_loader):
            total_data_time += time.perf_counter() - start_data_time
            if idx == num_warmup:
                start_time = time.perf_counter()
                total_data_time = 0
                total_compute_time = 0
                total_eval_time = 0

            start_compute_time = time.perf_counter()

            for input in inputs:
                cc += 1
                # print("evaluator got>", input["bpp"])
                bpp_sum += input["bpp"]
                # print("now>", cc, bpp_sum)

            outputs = model(inputs)  # apply Detectron2 model
            # print("instances>", outputs[0]["instances"])
            """outputs:

            ::

                [
                    {"instances": Instances object}
                ]


            instances is an Instances object (please refer to detectron2's
            documentation)
            """

            """apply a mapping from Detectron2 output to the more
            reduced/specialized test set"""
            if class_list is not None:
                instances = outputs[0][
                    "instances"
                ]  # peel off detectron2's encapsulation..
                instances = filterInstances(instances, class_list)
                outputs = [{"instances": instances}]  # encapsulation again..

            if torch.cuda.is_available():
                torch.cuda.synchronize()
            total_compute_time += time.perf_counter() - start_compute_time

            start_eval_time = time.perf_counter()

            evaluator.process(inputs, outputs)
            """So how does this work?  Seems to be like this:

            evaluator: `COCOEvaluator("my_dataset_val", output_dir="./output")`

            x = input to neural net (image) y = results from neural net (Instace
            object with bboxes, etc.) Y = ground truth

            Each one "carries" image_id information so that evaluation can be
            done against the ground truth:

            y = net(x) / x has image_id => y has image_id Y = ground truth /
            evaluator has Y with image_id

            evaluator takes x image_id from inputs, y from outputs =>
            y(image_id) compares Y(image_id) to y(image_id)
            """
            total_eval_time += time.perf_counter() - start_eval_time

            iters_after_start = idx + 1 - num_warmup * int(idx >= num_warmup)
            data_seconds_per_iter = total_data_time / iters_after_start
            compute_seconds_per_iter = total_compute_time / iters_after_start
            eval_seconds_per_iter = total_eval_time / iters_after_start
            total_seconds_per_iter = (
                time.perf_counter() - start_time
            ) / iters_after_start
            if idx >= num_warmup * 2 or compute_seconds_per_iter > 5:
                eta = datetime.timedelta(
                    seconds=int(total_seconds_per_iter * (total - idx - 1))
                )
                log_every_n_seconds(
                    logging.INFO,
                    (
                        f"Inference done {idx + 1}/{total}. "
                        f"Dataloading: {data_seconds_per_iter:.4f} s/iter. "
                        f"Inference: {compute_seconds_per_iter:.4f} s/iter. "
                        f"Eval: {eval_seconds_per_iter:.4f} s/iter. "
                        f"Total: {total_seconds_per_iter:.4f} s/iter. "
                        f"ETA={eta}"
                    ),
                    n=5,
                )
            start_data_time = time.perf_counter()

    # Measure the time only for this worker (before the synchronization barrier)
    total_time = time.perf_counter() - start_time
    total_time_str = str(datetime.timedelta(seconds=total_time))
    # NOTE this format is parsed by grep
    logger.info(
        "Total inference time: {} ({:.6f} s / iter per device, on {} devices)".format(
            total_time_str, total_time / (total - num_warmup), num_devices
        )
    )
    total_compute_time_str = str(datetime.timedelta(seconds=int(total_compute_time)))
    logger.info(
        "Total inference pure compute time: {} ({:.6f} s / iter per device, on {} devices)".format(
            total_compute_time_str,
            total_compute_time / (total - num_warmup),
            num_devices,
        )
    )

    results = evaluator.evaluate()
    if results is not None:
        if cc <= 0:
            results["bpp"] = 0
        else:
            results["bpp"] = bpp_sum / cc

    # An evaluator may return None when not in main process. Replace it by an
    # empty dict instead to make it easier for downstream code to handle
    return results


@contextmanager
def inference_context(model):
    """
    A context where the model is temporarily changed to eval mode,
    and restored to previous mode afterwards.

    Args:
        model: a torch Module
    """
    training_mode = model.training
    model.eval()
    yield
    model.train(training_mode)
