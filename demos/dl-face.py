#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
"""A command line interface for running and testing face tools.

.. moduleauthor:: Ulf Krumnack

"""

# standard imports
from argparse import ArgumentParser
import os

# toolbox imports
from dltb.base.data import Data
from dltb.datasource import ImageDirectory
from dltb.tool import Tool
from dltb.tool.detector import ImageDetector
from dltb.util.image import imshow


def output_detections(detector: ImageDetector, data: Data,
                      extract: bool = False) -> None:
    """Output detections in textual and graphical form.
    """
    detections = detector.detections(data)
    marked_image = detector.marked_image(data)

    print(detections.description)
    if detections:
        print(f"{detections.description}: {len(detections)}")
        for index, region in enumerate(detections.regions):
            print(f"({index+1}) {region.location}")
    else:
        print(f"{detections.description}: no detections")

    imshow(marked_image, wait_for_key=True, timeout=5)

    if extract:
        extractions = detector.extractions(data)
        print(f"Showing {len(extractions)} extractions:")
        for index, extraction in enumerate(extractions):
            print(f"({index+1}) {extraction.shape}")
            imshow(extraction, wait_for_key=True, timeout=1)


def main():
    """Main program: parse command line options and start face tools.
    """

    parser = ArgumentParser(description='Deep learning based face processing')
    parser.add_argument('images', metavar='IMAGE', type=str, nargs='+',
                        help='an image to use')
    parser.add_argument('--detect', action='store_true', default=True,
                        help='run face detection')
    parser.add_argument('--loop', action='store_true', default=True,
                        help='run in loop mode')
    args = parser.parse_args()

    if args.detect:
        detector = Tool['haar']
        print(f"Detector: {detector} [prepared={detector.prepared}]")
        detector.prepare()
        print(f"Detector: {detector} [prepared={detector.prepared}]")

        for url in args.images:
            if os.path.isdir(url):
                datasource = ImageDirectory('images')
                datasource.prepare()
                for data in datasource:
                    print(detector(data))
                    # detector.process(data, mark=True)
                    # output_detections(detector, data)
            else:
                print(f"Applying detector to {url}")
                # print(detector(url))
                result = ('detections', 'mark', 'extract')
                data = detector.process_image(url, result=result) #mark=True, extract=True
                data.debug()
                output_detections(detector, data, extract=True)

    else:
        print("No operation specified.")


if __name__ == "__main__":
    main()