#!/usr/bin/env python3
import pathlib
import sys
import xml.etree.ElementTree as ET  # nosec

if __name__ == "__main__":
    test_report_path = pathlib.Path("./results")
    error_counter = 0
    for junit_file in test_report_path.glob("*/test-reports/**/*.xml"):
        print(f"Parsing {junit_file}")
        root = ET.fromstring(junit_file.open().read())  # noqa: S314
        error_counter = int(root.attrib["failures"]) + int(root.attrib["errors"])
        if error_counter > 0:
            print("Found errors.")
            sys.exit(1)
