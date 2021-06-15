#!/usr/share/ucs-test/runner python
## desc: Check if UCS 4.4 is installed
## tags: [apptest,ucsschool]
## exposure: safe
## bug: [40475]

import univention.config_registry
import univention.testing.utils as utils

EXPECTED_VERSION = "5.0"


def main():
    ucr = univention.config_registry.ConfigRegistry()
    ucr.load()

    current_version = ucr.get("version/version", "")
    if current_version != EXPECTED_VERSION:
        utils.fail(
            "Expected UCS version (%s) does not match with installed UCS version (%s)!"
            % (EXPECTED_VERSION, current_version)
        )


if __name__ == "__main__":
    main()
