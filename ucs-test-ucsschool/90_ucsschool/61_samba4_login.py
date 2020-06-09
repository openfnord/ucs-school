#!/usr/share/ucs-test/runner python
## desc: Create an user and check the samba login
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
## packages:
##  - univention-samba4
## exposure: dangerous
## tags:
##  - ucsschool
##  - apptest

import univention.config_registry as config_registry
import subprocess
from ldap.filter import escape_filter_chars
import univention.testing.udm as udm_test
import univention.testing.strings as uts
from univention.testing.ucs_samba import wait_for_drs_replication, wait_for_s4connector


class SambaLoginFailed(Exception):
	pass


if __name__ == "__main__":
	ucr = config_registry.ConfigRegistry()
	ucr.load()

	with udm_test.UCSTestUDM() as udm:
		username = uts.random_username()
		password = uts.random_string()

		user = udm.create_user(username=username, password=password)

		print "Waiting for DRS replication..."
		wait_for_drs_replication("(sAMAccountName=%s)" % (escape_filter_chars(username),), attrs="objectSid")
		wait_for_s4connector()

		cmd = ("/usr/bin/smbclient", "-U%s%%%s" % (username, password), "//%s/sysvol" % ucr.get('hostname'), '-c', 'ls')
		retcode = subprocess.call(cmd, shell=False)
		if retcode:
			raise SambaLoginFailed()
