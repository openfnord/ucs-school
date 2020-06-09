#!/usr/share/ucs-test/runner python
## desc: ucs-school-helpdesk - send mail via helpdesk module
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-helpdesk]

import sys
import tempfile
import time

import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.config_registry import handler_set
from univention.testing.mail import MailSink
from univention.testing.network import NetworkRedirector
from univention.testing.umc import Client


def main():
    # initializing mail data
    message = time.time() * 1000
    message = "%.30f" % message
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            with NetworkRedirector() as nethelper:
                # creating ou & a teacher
                school, _ = schoolenv.create_ou(name_edudc=ucr.get("hostname"))
                tea, _ = schoolenv.create_user(school, is_teacher=True)
                utils.wait_for_replication_and_postrun()
                handler_set(["ucsschool/helpdesk/recipient=ucstest@univention.de"])
                host = ucr.get("hostname")
                connection = Client(host)
                connection.authenticate(tea, "univention")
                f = tempfile.NamedTemporaryFile(suffix=".eml", dir="/tmp")
                print "Creating temp mail file %s" % (f.name)
                nethelper.add_redirection("0.0.0.0/0", 25, 60025)
                ms = MailSink("127.0.0.1", 60025, filename=f.name)
                ms.start()
                params = {"username": tea, "school": school, "category": "Sonstige", "message": message}
                # Sending the mail message with the unique id
                print "Sending message..."
                result = connection.umc_command("helpdesk/send", params).result
                if not result:
                    utils.fail("Message was not sent successfully")
                print "Message sent."
                # time out for waiting for the message to be delivered	in seconds
                timeOut = 60
                print "Waiting %ds for incoming mail..." % (timeOut,)
                # periodically checking the receipt of the same sent mail
                for i in xrange(timeOut, 0, -1):
                    print i,
                    if message in open(f.name).read():
                        print "\nUnique id was found in target file %r" % (f.name,)
                        fail = 0
                        break
                    else:
                        fail = 1
                        time.sleep(1)
                        continue
                print
                ms.stop()
                f.close()
    if fail:
        utils.fail("Unique id was not found in target file")


if __name__ == "__main__":
    sys.exit(main())
