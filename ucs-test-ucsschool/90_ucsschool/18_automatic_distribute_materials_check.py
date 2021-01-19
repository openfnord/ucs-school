#!/usr/share/ucs-test/runner python
## desc: automatic_distribute_materials_check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-distribution]

from __future__ import print_function

import time
from subprocess import call

import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.config_registry import handler_set
from univention.testing.ucsschool.distribution import Distribution
from univention.testing.ucsschool.workgroup import Workgroup
from univention.testing.umc import Client


def main():
    MIN_DIST_TIME = 8 * 60
    MIN_COLL_TIME = 18 * 60
    try:
        with utu.UCSTestSchool() as schoolenv:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                host = ucr.get("hostname")
                handler_set(["umc/http/session/timeout=1200"])
                handler_set(["umc/module/timeout=1200"])
                call(["invoke-rc.d", "univention-management-console-web-server", "restart"])
                call(["invoke-rc.d", "univention-management-console-server", "restart"])
                connection = Client(host)

                # Create ou, teacher, student, group
                school, oudn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))
                tea, teadn = schoolenv.create_user(school, is_teacher=True)
                stu, studn = schoolenv.create_user(school)
                group = Workgroup(school, members=[studn])
                group.create()
                utils.wait_for_replication_and_postrun()

                connection.authenticate(tea, "univention")

                # Prepare times for auto distribution and collection
                local = time.localtime(time.time() + MIN_DIST_TIME)
                distTime = time.strftime("%H:%M", local)
                distDate = time.strftime("%Y-%m-%d", local)

                local = time.localtime(time.time() + MIN_COLL_TIME)
                collTime = time.strftime("%H:%M", local)
                collDate = time.strftime("%Y-%m-%d", local)

                # Creating new project
                project = Distribution(
                    school,
                    sender=tea,
                    connection=connection,
                    ucr=ucr,
                    files=[("file_name", "utf8")],
                    recipients=[group],
                    distributeType="automatic",
                    distributeTime=distTime,
                    distributeDate=distDate,
                    collectType="automatic",
                    collectTime=collTime,
                    collectDate=collDate,
                    flavor="teacher",
                )
                project.add()
                project.check_add()

                print("waiting for 6 mins for the project to be automatically distributed")
                time.sleep(MIN_DIST_TIME + 1)
                project.check_distribute([stu])

                print("waiting for 11 mins for the project to be automatically collected")
                time.sleep(MIN_COLL_TIME - MIN_DIST_TIME + 1)
                project.check_collect([stu])

                project.remove()
                project.check_remove()
    finally:
        call(["invoke-rc.d", "univention-management-console-web-server", "restart"])
        call(["invoke-rc.d", "univention-management-console-server", "restart"])
        time.sleep(
            5
        )  # wait some time for UMC web server and UMC server to be ready before the next test is called


if __name__ == "__main__":
    main()
