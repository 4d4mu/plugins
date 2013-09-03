#!/usr/bin/env python
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
# Copyright 2013 Robert Budde                        robert@projekt131.de
#########################################################################
#  Squeezebox-Plugin for SmartHome.py.  http://mknx.github.com/smarthome/
#
#  This plugin is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This plugin is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this plugin. If not, see <http://www.gnu.org/licenses/>.
#########################################################################

import logging
import struct
import time
import urllib2
import lib.my_asynchat
import re

logger = logging.getLogger('Squeezebox')

class Squeezebox(lib.my_asynchat.AsynChat):

    def __init__(self, smarthome, host='127.0.0.1', port=9090):
        lib.my_asynchat.AsynChat.__init__(self, smarthome, host, port)
        self._sh = smarthome
        self._val = {}
        self._obj = {}
        self._init_cmds = []
        smarthome.monitor_connection(self)

    def _check_mac(self, mac):
        return re.match("[0-9a-f]{2}([:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", mac.lower())

    def _resolv_full_cmd(self, item, attr):
        # check if PlayerID wildcard is used
        if '<playerid>' in item.conf[attr]:
            # try to get from parent object
            parent_item = item.return_parent()
            if (parent_item != None) and ('squeezebox_playerid' in parent_item.conf) and self._check_mac(parent_item.conf['squeezebox_playerid']):
                item.conf[attr] = item.conf[attr].replace('<playerid>', parent_item.conf['squeezebox_playerid'])
            else:
                logger.warning("squeezebox: could not resolve playerid for {0} from parent item {1}".format(item, parent_item))
                return None
        return item.conf[attr]

    def parse_item(self, item):
        if 'squeezebox_recv' in item.conf:
            cmd = self._resolv_full_cmd(item,'squeezebox_recv')
            if (cmd == None):
                return None 

            logger.debug("squeezebox: {0} receives updates by \"{1}\"".format(item, cmd))
            if not cmd in self._val:
                self._val[cmd] = {'items': [item], 'logics': []}
            else:
                if not item in self._val[cmd]['items']:
                    self._val[cmd]['items'].append(item)

            if ('squeezebox_init' in item.conf):
                cmd = self._resolv_full_cmd(item,'squeezebox_init')
                if (cmd == None):
                    return None 

                logger.debug("squeezebox: {0} is initialized by \"{1}\"".format(item, cmd))
                if not cmd in self._val:
                    self._val[cmd] = {'items': [item], 'logics': []}
                else:
                    if not item in self._val[cmd]['items']:
                        self._val[cmd]['items'].append(item)

            if not cmd in self._init_cmds:
                self._init_cmds.append(cmd)

        if 'squeezebox_send' in item.conf:
            cmd = self._resolv_full_cmd(item,'squeezebox_send')
            if (cmd == None):
                return None
            logger.debug("squeezebox: {0} is send to \"{1}\"".format(item, cmd))
            return self.update_item
        else:
            return None

    def parse_logic(self, logic):
        pass

    def update_item(self, item, caller=None, source=None, dest=None):
        # be careful: as the server echoes ALL comands not using this will result in a loop
        if caller != 'LMS':
            cmd = self._resolv_full_cmd(item, 'squeezebox_send').split()
            if self._check_mac(cmd[0]):
                cmd[0] = urllib2.quote(cmd[0])
            if isinstance(item(), str):
                value = urllib2.quote(item().encode('utf-8'))
            elif (item._type == 'bool'):
                # convert to get '0'/'1' instead of 'True'/'False'
                value = int(item())
            else:
                value = item()

            # special handling for bool-types who need other comands or values to behave intuitively
            if (len(cmd) >= 2) and not item():
                if (cmd[1] == 'play'):
                    # if 'play' was set to false, send 'stop' to allow single-item-operation
                    cmd[1] = 'stop'
                    value = 1
                if (cmd[1] == 'playlist') and (cmd[2] in ['shuffle', 'repeat']):
                    # if a boolean item of [...] was set to false, send '0' to disable the option whatsoever
                    # replace cmd[3], as there are fixed values given and filling in 'value' is pointless
                    cmd[3] = '0'

            self._send(' '.join(cmd_str for cmd_str in cmd).format(value).replace('°','%B0'))

    def _send(self, cmd):
        logger.debug("Sending request: {0}".format(cmd))
        self.push(cmd+'\r\n')

    def _parse_response(self, response):
        data = [urllib2.unquote(data_str) for data_str in response.split()]
        logger.debug("Got: {0}".format(data))

        if (data[0].lower() == 'listen'):
            value = int(data[1])
            if (value == 1):
                logger.info("Listen-mode enabled")
            else:
                logger.info("Listen-mode disabled")

        if self._check_mac(data[0]):
            if (data[1] == 'play'):
                self._update_items_with_data([data[0], 'play', 1])
                self._update_items_with_data([data[0], 'stop', 0])
                self._update_items_with_data([data[0], 'pause', 0])
                # play also overrules mute
                self._update_items_with_data([data[0], 'prefset server mute', 0])
                return
            elif (data[1] == 'stop'):
                self._update_items_with_data([data[0], 'play', 0])
                self._update_items_with_data([data[0], 'stop', 1])
                self._update_items_with_data([data[0], 'pause', 0])
                return
            elif (data[1] == 'pause'):
                self._send(data[0] + ' mode ?')
                self._send(data[0] + ' mixer muting ?')
                return
            elif (data[1] == 'mode'):
                self._update_items_with_data([data[0], 'play', data[2] == 'play'])
                self._update_items_with_data([data[0], 'stop', data[2] == 'stop'])
                self._update_items_with_data([data[0], 'pause', data[2] == 'pause'])
                # play also overrules mute
                if (data[2] == 'play'):
                    self._update_items_with_data([data[0], 'prefset server mute', 0])
                return
            elif re.match("[+-][0-9]+$", data[-1]):
                # handle a relative step like '+1' or '-10'
                logger.debug('got relative value - can\'t handle that - requesting absolute value')
                self._send(' '.join(data_str for data_str in data[:-1]) + ' ?')
                return
            elif (data[1] == 'prefset'):
                if (data[2] == 'server'):
                    if (data[3] == 'volume'):
                        # make sure value is always positive - also if muted!
                        data[4] = abs(int(data[4]))
            elif (data[1] == 'playlist'):
                if (data[2] == 'jump') and (len(data) == 4):
                    self._update_items_with_data([data[0], 'playlist index', data[3]]) 
                elif (data[2] == 'newsong'):
                    if (len(data) >= 4):
                        self._update_items_with_data([data[0], 'title', data[3]])
                    else:
                        self._send(data[0] + ' title ?')
                    if (len(data) >= 5):
                        self._update_items_with_data([data[0], 'playlist index', data[4]])
                    # trigger reading of other song fields
                    for field in ['genre', 'artist', 'album', 'duration']:
                        self._send(data[0] + ' ' + field + ' ?')
            elif (data[1] in ['genre', 'artist', 'album', 'title']) and (len(data) == 2):
                # these fields are returned empty so update fails - append '' to allow update
                data.append('')
            elif (data[1] in ['duration']) and (len(data) == 2):
                # these fields are returned empty so update fails - append '0' to allow update
                data.append('0')
        # finally check for '?'
        if (data[-1] == '?'):
            return
        self._update_items_with_data(data)

    def _update_items_with_data(self, data):
        cmd = ' '.join(data_str for data_str in data[:-1])
        if (cmd in self._val):
            for item in self._val[cmd]['items']:
                if isinstance(item(), (str, unicode)):
                    data[-1] = data[-1].decode('utf-8')

                item(data[-1], 'LMS', "{}:{}".format(self.addr[0],self.addr[1]))

    def found_terminator(self):
        response = self.buffer
        self.buffer = ''
        self._parse_response(response)

    def handle_connect(self):
        self.discard_buffers()
        # enable listen-mode to get notified of changes
        self._send('listen 1')
        if self._init_cmds != []:
            if self.is_connected:
                logger.debug('squeezebox: init read')
                for cmd in self._init_cmds:
                    self._send(cmd + ' ?')

    def run(self):
        self.alive = True

    def stop(self):
        self.alive = False
        self.handle_close()
