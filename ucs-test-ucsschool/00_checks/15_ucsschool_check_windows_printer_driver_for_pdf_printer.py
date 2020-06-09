#!/usr/share/ucs-test/runner python
## desc: Check windows printer driver default for PDF printer in UCS@school
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool]
## exposure: safe
## packages: [ucs-school-umc-printermoderation]

import subprocess

import univention.testing.utils as utils
import univention.testing.ucr as ucr_test


def check_value(path, key, value):
	cmd = ['net', 'registry', 'getvalue', path, key]
	out, err = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
	found = False
	print path + ' ' + key
	for i in out.split('\n'):
		print i
		if i.startswith('Value '):
			v = i.split('=')[1].strip().strip('"')
			if v == value:
				found = True
	if not found:
		utils.fail("value in '%s' is '%s' not!" % (path + '\\' + key, value))


def main():
	with ucr_test.UCSTestConfigRegistry() as ucr:
		driver_name = ucr.get('ucsschool/printermoderation/windows/driver/name')
		printer_name = 'PDFDrucker'
		registry_path = 'HKLM\Software\Microsoft\Windows NT\CurrentVersion\Print\Printers\%s' % printer_name
		check_value(registry_path, 'Printer Driver', driver_name)
		check_value(registry_path + '\DsSpooler', 'driverName', driver_name)


if __name__ == '__main__':
	main()
