#!/usr/share/ucs-test/runner python
## desc: ucs-school-printermoderation-find-printer-in-ou-check
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-printermoderation, ucs-school-import]

import socket
import subprocess
import tempfile

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.umc import Client


# add / del / modify Printer
def doPrinter(operation, printer_name, schoolName, spool_host, domainname):
    localIp = socket.gethostbyname(socket.gethostname())
    uri = "%s://%s" % ("lpd", localIp)
    print_server = "%s.%s" % (spool_host, domainname)
    f = tempfile.NamedTemporaryFile(suffix=".csv")
    line = ("%s\t%s\t%s\t%s\t%s\n" % (operation, schoolName, print_server, printer_name, uri)).encode(
        "utf-8"
    )
    f.write(line)
    f.flush()
    cmd = ["/usr/share/ucs-school-import/scripts/import_printer", f.name]
    retval = subprocess.call(cmd)
    f.close()
    if retval:
        utils.fail("Unexpected error while acting on Printer")
    utils.wait_for_replication_and_postrun()


# check the existance of the created printer
def printerExist(connection, printerName, schoolName):
    requestResult = connection.umc_command("printermoderation/printers", {"school": schoolName}).result
    printerFound = [d for d in requestResult if d["label"] == printerName]
    if printerFound:
        return True
    else:
        return False


def main():
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            newPrinterName = uts.random_string()
            host = ucr.get("hostname")
            domainname = ucr.get("domainname")
            connection = Client(host)
            account = utils.UCSTestDomainAdminCredentials()
            admin = account.username
            passwd = account.bindpw
            connection.authenticate(admin, passwd)

            # create more than one OU
            (schoolName1, _), (schoolName2, _), (schoolName3, _) = schoolenv.create_multiple_ous(
                3, name_edudc=host
            )

            # add new printer
            doPrinter("A", newPrinterName, schoolName1, host, domainname)

            # check if the printer exists in the correct OU
            for i in range(5):
                if not printerExist(connection, newPrinterName, schoolName1):
                    utils.fail("Printer not found in the specified OU")

                for school in [schoolName2, schoolName3]:
                    if printerExist(connection, newPrinterName, school):
                        utils.fail("Printer underneath of wrong OU was found.")

            # delete the created printer
            doPrinter("D", newPrinterName, schoolName1, host, domainname)


if __name__ == "__main__":
    main()
