# -*- coding: utf-8 -*-
#
# Univention UCS@school
# Copyright 2018 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

"""
Default configuration checks.

See docstring of module ucsschool.importer.utils.configuration_checks on how to
add your own checks.
"""

from ucsschool.lib.models.utils import ucr
from ucsschool.importer.exceptions import InitialisationError
from ucsschool.importer.utils.configuration_checks import ConfigurationChecks


class DefaultConfigurationChecks(ConfigurationChecks):
	def test_minimal_mandatory_attributes(self):
		for attr in ("firstname", "lastname", "name", "record_uid", "school", "source_uid"):
			if attr not in self.config.get("mandatory_attributes", []):
				raise InitialisationError("Configured list of 'mandatory_attributes' must include {!r}.".format(attr))

	def test_source_uid(self):
		if not self.config.get("sourceUID"):
			raise InitialisationError("No sourceUID was specified.")

	def test_input_type(self):
		if not self.config["input"].get("type"):
			raise InitialisationError("No input:type was specified.")

	def test_deprecated_user_deletion(self):
		if "user_deletion" in self.config:
			raise InitialisationError(
				"The 'user_deletion' configuration key is deprecated. Please set 'deletion_grace_period'.")

	def test_username_max_length(self):
		for role in ('default', 'staff', 'student', 'teacher', 'teacher_and_staff'):
			try:
				username_max_length = self.config["username"]["max_length"][role]
			except KeyError:
				continue
			if username_max_length < 4:
				raise InitialisationError(
					"Configuration value of username:max_length:{} must be higher than 3.".format(role)
				)
		for role in ('default', 'staff', 'teacher', 'teacher_and_staff'):
			username_max_length = self.config["username"]["max_length"].get(role, 20)
			if username_max_length > 20:
				raise InitialisationError(
					"Configuration value of username:max_length:{} must be 20 or less.".format(role)
				)

	def test_exam_user_prefix_length(self):
		exam_user_prefix_length = len(ucr.get("ucsschool/ldap/default/userprefix/exam", "exam-"))
		student_username_max_length = self.config["username"]["max_length"].get("student", 20 - exam_user_prefix_length)
		if student_username_max_length > 20 - exam_user_prefix_length:
			raise InitialisationError(
				"Configuration value of username:max_length:student must be {} or less.".format(
					20 - exam_user_prefix_length)
			)

	def test_user_role_role_mapping_combination(self):
		if self.config['user_role'] and '__role' in self.config['csv']['mapping'].values():
			raise InitialisationError("Using 'user_role' setting and '__role' mapping at the same time is not allowed.")
