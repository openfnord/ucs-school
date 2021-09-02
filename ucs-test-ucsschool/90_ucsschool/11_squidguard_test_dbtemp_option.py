#!/usr/share/ucs-test/runner pytest -s -l -v
## desc: squidguard - check dbtemp option and position of BDB backing files
## roles: [domaincontroller_master,domaincontroller_backup,domaincontroller_slave]
## bugs: [40541]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [squidguard]
## versions:
##  4.2-0: skip

from __future__ import print_function

import os
import subprocess
import tempfile

from univention.testing.strings import random_string

CONF_SQUIDGUARD = """logdir %(tempdir)s
dbhome %(tempdir)s/

src testusergroup {
    userlist testuser
}

dest whitelist {
    domainlist whitelisted-domains
    urllist    whitelisted-urls
}

acl {
         testusergroup {
                 pass whitelist none
                 redirect http://www.univention.de
         }

         default {
                  pass whitelist all
                  redirect http://www.univention.com
         }
}
"""


def test_squidguard_test_dbtemp_option():
    def write_sg_cfg(prefix=""):
        with open(fn_cfg, "w") as fd:
            fd.write("\n".join([prefix, CONF_SQUIDGUARD % {"tempdir": tempdir}]))

    def print_sg_log():
        print(open(fn_log, "r").read() + "\n")

    def exists_in_sg_log(searchstring):
        # check if given string exists in logfile
        content = open(fn_log, "r").read()
        return searchstring in content

    def write_lists():
        with open(fn_userlist, "w") as fd:
            for i in range(1000):
                for name in (
                    "anton",
                    "berta",
                    "caesar",
                    "doris",
                    "emil",
                    "frieda",
                    "gustav",
                    "hanna",
                    "immo",
                    "jane",
                ):
                    fd.write("%s%d\nMYDOMAIN\\%s%d\n" % (name, i, name, i))
        with open(fn_whitelist_domains, "w") as fd:
            for i in range(5000):
                for name in ("univention.de", "software-univention.de"):
                    fd.write("%d.%s\nsmtp%d.%s\n" % (i, name, i, name))
        with open(fn_whitelist_urls, "w") as fd:
            for i in range(10000):
                fd.write(
                    "http://updates.software-univention.de/%s/%s.html\n"
                    % (random_string(), random_string())
                )

    def count_bdb_files(path):
        # count number of files starting with "BDB" in their filenames in given directory
        return len([x for x in os.listdir(path) if x.startswith("BDB")])

    def truncate_sg_log():
        with open(fn_log, "w") as fd:
            fd.write("\n")

    try:
        tempdir = tempfile.mkdtemp(prefix="tmp.ucs-test.squidguard.")
        print("TEMPDIR=%r" % (tempdir,))
        fn_cfg = os.path.join(tempdir, "squidguard.conf")
        fn_log = os.path.join(tempdir, "squidGuard.log")
        fn_userlist = os.path.join(tempdir, "testuser")
        fn_whitelist_domains = os.path.join(tempdir, "whitelisted-domains")
        fn_whitelist_urls = os.path.join(tempdir, "whitelisted-urls")

        # create database files and config
        write_lists()
        write_sg_cfg("")
        exitcode = subprocess.call(
            ["squidGuard", "-d", "-c", fn_cfg, "-C", "all"],
            stdin=open("/dev/null", "r"),
            stdout=open(fn_log, "a+"),
            stderr=open(fn_log, "a+"),
        )
        print_sg_log()
        assert not exitcode, "Creating databases failed"
        assert not exists_in_sg_log("dbtemp"), '"dbtemp" should not be mentioned after db creation'

        # normal run
        truncate_sg_log()
        cnt_old_vartmp = count_bdb_files("/var/tmp")
        cnt_old_tempdir = count_bdb_files(tempdir)
        exitcode = subprocess.call(
            ["squidGuard", "-d", "-c", fn_cfg],
            stdin=open("/dev/null", "r"),
            stdout=open(fn_log, "a+"),
            stderr=open(fn_log, "a+"),
        )
        print_sg_log()
        assert not exitcode, "squidguard run 1 failed"
        assert not exists_in_sg_log("dbtemp"), '"dbtemp" should not be mentioned in run 1'
        cnt_new_vartmp = count_bdb_files("/var/tmp")
        cnt_new_tempdir = count_bdb_files(tempdir)
        print(
            "Counts: /var/tmp: %d ==> %d    %s: %d ==> %d"
            % (
                cnt_old_vartmp,
                cnt_new_vartmp,
                tempdir,
                cnt_old_tempdir,
                cnt_new_tempdir,
            )
        )
        assert (
            cnt_old_vartmp < cnt_new_vartmp and cnt_old_tempdir == cnt_new_tempdir
        ), "Unexpected number of temporary backing files"
        # tempdir should not change; at least one new file in /var/tmp/

        # run with special dbtemp option
        truncate_sg_log()
        write_sg_cfg("dbtemp %s" % (tempdir,))
        cnt_old_vartmp = count_bdb_files("/var/tmp")
        cnt_old_tempdir = count_bdb_files(tempdir)
        exitcode = subprocess.call(
            ["squidGuard", "-d", "-c", fn_cfg],
            stdin=open("/dev/null", "r"),
            stdout=open(fn_log, "a+"),
            stderr=open(fn_log, "a+"),
        )
        print_sg_log()
        assert not exitcode, "squidguard run 2 failed"
        assert exists_in_sg_log("dbtemp"), '"dbtemp" should be mentioned in run 2'
        cnt_new_vartmp = count_bdb_files("/var/tmp")
        cnt_new_tempdir = count_bdb_files(tempdir)
        print(
            "Counts: /var/tmp: %d ==> %d    %s: %d ==> %d"
            % (
                cnt_old_vartmp,
                cnt_new_vartmp,
                tempdir,
                cnt_old_tempdir,
                cnt_new_tempdir,
            )
        )
        assert (
            cnt_old_vartmp == cnt_new_vartmp and cnt_old_tempdir < cnt_new_tempdir
        ), "Unexpected number of temporary backing files"
        # /var/tmp should not change; at least one new file in $tempdir

        # short functional test
        truncate_sg_log()
        write_sg_cfg("dbtemp %s" % (tempdir,))
        p = subprocess.Popen(
            ["squidGuard", "-d", "-c", fn_cfg],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=open(fn_log, "a+"),
        )
        for i in range(100000):
            if not i % 5000:
                print("%d/100000" % i)
            username = random_string(length=8)
            if i % 3 == 1:
                username = "anton1"
            elif i % 3 == 2:
                username = "-"
            p.stdin.write(
                (
                    "http://www.univention.de/%s/%s.html 10.20.30.40/- %s GET\n"
                    % (random_string(), random_string(), username)
                ).encode("utf-8")
            )
            p.stdout.readline()
        print("")
        # p.stdin.close()
        p.communicate()
        print_sg_log()
        assert not p.returncode, "squidguard run 3 failed"
        assert exists_in_sg_log("dbtemp"), '"dbtemp" should be mentioned in run 3'
    finally:
        subprocess.call(["rm", "-Rf", tempdir])
