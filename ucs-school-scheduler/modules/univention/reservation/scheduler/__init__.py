#!/usr/bin/python2.4
# -*- coding: utf-8 -*-
#
# Copyright 2008-2010 Univention GmbH
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

import univention.debug
from univention.config_registry import ConfigRegistry

ucr = ConfigRegistry ()
ucr.load ()

def init_debug():
	_d = univention.debug.function('scheduler.init_debug')
	if ucr.has_key('scheduler/debug/function'):
		try:
			function_level = int (ucr['scheduler/debug/function'])
		except:
			function_level = 0
	else:
		function_level = 0
	univention.debug.init('/var/log/univention/scheduler.log', 1, function_level)
	if ucr.has_key('scheduler/debug/level'): # values between 0-4 are allowed
		debug_level=int (ucr['scheduler/debug/level'])
	else:
		debug_level = 2
	univention.debug.set_level(univention.debug.MAIN, debug_level)

def close_debug():
	_d = univention.debug.function('scheduler.close_debug')
	univention.debug.debug(univention.debug.MAIN, univention.debug.INFO, "close debug")
	univention.debug.end('/var/log/univention/scheduler.log')
	univention.debug.exit('/var/log/univention/scheduler.log')
