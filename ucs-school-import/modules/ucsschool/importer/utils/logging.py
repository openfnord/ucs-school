# -*- coding: utf-8 -*-
#
# Copyright 2016-2018 Univention GmbH
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
Central place to get logger for import.
"""

from ucsschool.lib.models.utils import get_logger as get_lib_logger, logger as lib_logger

try:
	from typing import Optional
except ImportError:
	pass


def get_logger():  # type: () -> logging.Logger
	return get_lib_logger("import")


def make_stdout_verbose():  # type: () -> logging.Logger
	return get_lib_logger("import", "DEBUG")


def add_file_handler(filename, uid=None, gid=None, mode=None):
	# type: (str, Optional[int], Optional[int], Optional[int]) -> logging.Logger
	if filename.endswith(".log"):
		info_filename = "{}.info".format(filename[:-4])
	else:
		info_filename = "{}.info".format(filename)
	handler_kwargs = {'fuid': uid, 'fgid': gid, 'fmode': mode}
	get_lib_logger("import", "DEBUG", filename, handler_kwargs=handler_kwargs)
	return get_lib_logger("import", "INFO", target=info_filename, handler_kwargs=handler_kwargs)


def move_our_handlers_to_lib_logger():  # type: () -> ()
	import_logger = get_logger()
	for handler in import_logger.handlers:
		lib_logger.addHandler(handler)
		import_logger.removeHandler(handler)
