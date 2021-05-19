#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: test content of API root
## tags: [ucs_school_http_api]
## exposure: dangerous
## packages: [ucs-school-http-api-bb]
## bugs: []

from __future__ import unicode_literals

import logging
from unittest import TestCase, main

import requests

from univention.testing.ucsschool.bb_api import API_ROOT_URL, RESSOURCE_URLS, HttpApiUserTestBase

logger = logging.getLogger("univention.testing.ucsschool")


class Test(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth_headers = {"Authorization": "{} {}".format(*HttpApiUserTestBase.get_token())}
        print("*** auth_headers={!r}".format(cls.auth_headers))

    def test_01_unauth_connection(self):
        response = requests.get(API_ROOT_URL, verify=False)
        self.assertEqual(
            response.status_code,
            401,
            "response.status_code = {} for URL {!r} -> {!r}".format(
                response.status_code, response.url, response.text
            ),
        )

    def test_02_auth_connection(self):
        response = requests.get(API_ROOT_URL, headers=self.auth_headers, verify=False)
        self.assertEqual(
            response.status_code,
            200,
            "response.status_code = {} for URL {!r} response.text={!r}.".format(
                response.status_code, response.url, response.text
            ),
        )

    def test_03_resources_in_api_root(self):
        response = requests.get(API_ROOT_URL, headers=self.auth_headers, verify=False)
        res = response.json() if callable(response.json) else response.json
        self.assertDictEqual(
            RESSOURCE_URLS,
            res,
            "response.status_code = {} for URL {!r} -> {!r}".format(
                response.status_code, response.url, response.text
            ),
        )


if __name__ == "__main__":
    main(verbosity=2)
