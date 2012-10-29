#!/usr/bin/env python
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
# Copyright 2012 KNX-User-Forum e.V.            http://knx-user-forum.de/
#########################################################################
#  This file is part of SmartHome.py.   http://smarthome.sourceforge.net/
#
#  SmartHome.py is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SmartHome.py is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHome.py.  If not, see <http://www.gnu.org/licenses/>.
#########################################################################

import logging
import socket
import threading
import struct

import lib.my_asynchat

logger = logging.getLogger('')

REQ_DELIMITER = '\r'
RESP_DELIMITER = '\r\n'

class Russound(lib.my_asynchat.AsynChat):

    def __init__(self, smarthome, host, port=9621):
        lib.my_asynchat.AsynChat.__init__(self, smarthome, host, port)
        self.terminator = RESP_DELIMITER
        self._sh = smarthome
        self.params = {}
        self._timers = {}
        smarthome.monitor_connection(self)

    def parse_item(self, item):
        if 'rus_path' in item.conf:
            path = item.conf['rus_path']
            parts = path.split('.', 2)
            
            if len(parts) is not 3:
                logger.warning("Invalid Russound path with value {0}, format should be 'c.z.p' c = controller, z = zone, p = parameter name.".format(path))
                return None

            c = parts[0]
            z = parts[1]
            param = parts[2]

        else:
            if 'rus_controller' in item.conf:
                c = item.conf['rus_controller']
                path = c + '.'
            else:
                return None

            if 'rus_zone' in item.conf:
                z = item.conf['rus_zone']
                path += z + '.'
            else:
                logger.warning("No zone specified for controller {0} in config of item {1}".format(c,item))
                return None

            if 'rus_parameter' in item.conf:
                param = item.conf['rus_parameter']
                path += param
            else:
                logger.warning("No parameter specified for zone {0} on controller {1} in config of item {2}".format(z,c,item))
                return None

            item.conf['rus_path'] = path
            
        param = param.lower()
        self.params[path] = {'c': int(c), 'z': int(z), 'param':param, 'item':item}
        logger.debug("Parameter {0} with path {1} added".format(item, path))

        if param == 'relativevolume':
            if 'rus_intervall' in item.conf:
                intervall = float(item.conf['rus_intervall'])
            else:
                intervall = 200.0

            self._timers[path] = Timer(intervall / 1000.0, _dim_volume, path)
            logger.debug("Timer for path {0} with intervall {1} added".format(path, intervall))

        return self.update_item

    def parse_logic(self, logic):
        pass

    def update_item(self, item, caller=None, source=None):
        if caller != 'Russound':
            p = self.params[item.conf['rus_path']]
            cmd = p['param']
            c = p['c']
            z = p['z']

            if cmd == 'bass':
                self.send_set(c, z, cmd, int(round(float(item()) / (128.0 / 10.0))))
            elif cmd == 'treble':
                self.send_set(c, z, cmd, int(round(float(item()) / (128.0 / 10.0))))
            elif cmd == 'balance':
                self.send_set(c, z, cmd, int(round(float(item()) / (128.0 / 10.0))))
            elif cmd == 'loudness':
                self.send_set(c, z, cmd, 'ON' if item() else 'OFF')
            elif cmd == 'turnonvolume':
                self.send_set(c, z, cmd, int(round(float(item()) / (255.0 / 50.0))))
            elif cmd == 'status':
                self.send_event(c, z, 'ZoneOn' if item() else 'ZoneOff')
            elif cmd == 'partymode':
                self.send_event(c, z, cmd, item().lower())
            elif cmd == 'donotdisturb':
                self.send_event(c, z, cmd, 'on' if item() else 'off')
            elif cmd == 'volume':
                self.send_event(c, z, 'KeyPress', 'Volume', int(round(float(item()) / (255.0 / 50.0))))
            elif cmd == 'currentsource':
                self.send_event(c, z, 'SelectSource', item())
            elif cmd == 'mute':
                self.send_event(c, z, 'KeyRelease', 'Mute')
            elif cmd == 'relativevolume':
                if item()[1] == 0:
                    self._timers[p].cancel()
                else:
                    self._timers[p].start()

    def send_set(self, c, z, cmd, value):
        self._send_cmd('SET C[{0}].Z[{1}].{2}="{3}"\r'.format(c, z, cmd, value))

    def send_event(self, c, z, cmd, value1=None, value2=None):
        if value1 is None and value2 is None:
            self._send_cmd('EVENT C[{0}].Z[{1}]!{2}\r'.format(c, z, cmd))
        elif value2 is None:
            self._send_cmd('EVENT C[{0}].Z[{1}]!{2} {3}\r'.format(c, z, cmd, value1))
        else:
            self._send_cmd('EVENT C[{0}].Z[{1}]!{2} {3} {4}\r'.format(c, z, cmd, value1, value2))
        
    def _dim_volume(self, path):
        p = self.params[path]
        c = p['c']
        z = p['z']
        item = p['item']
        direction = item()[0]
        step = item()[1]

        if step == 0:
            return

        if direction == 1:
            self.send_event(c, z, 'KeyPress', 'VolumeUp')
        else:
            self.send_event(c, z, 'KeyPress', 'VolumeDown')

        # restart the timer for continues in-/decreasing of the volume
        # until we receive the stop command
        self._timers[path].start()
    
    def _watch_zone(self, controller, zone):
        self._send_cmd('WATCH C[{0}].Z[{1}] ON\r'.format(controller, zone))

    def _watch_system(self):
        self._send_cmd('WATCH System ON\r') 

    def _send_cmd(self, cmd):
        logger.debug("Sending request: {0}".format(cmd))
        
        # if connection is closed we don't wait for sh.con to reopen it
        # instead we reconnect immediatly
        if not self.is_connected:
            self.connect()

        self.push(cmd)

    def _parse_response(self, resp):
        try:
            logger.debug("Parse response: {0}".format(resp))
            if resp[0] == 'S':
                return 
            if resp[0] == 'E':
                logger.debug("Received response error: {0}".format(resp))
            elif resp[0] == 'N':
                resp = resp[2:]

                if resp[0] == 'C':
                    resp = resp.split('.', 2)
                    c = int(resp[0][2])
                    z = int(resp[1][2])
                    resp = resp[2]
                    cmd = resp.split('=')[0].lower()
                    value = resp.split('"')[1]

                    path = '{0}.{1}.{2}'.format(c, z, cmd)
                    if path in self.params.keys():
                        self.params[path]['item'](self._decode(cmd, value), 'Russound')
                elif resp.startswith('System.status'):
                    return
                elif resp[0] == 'S':
                    return
        except Exception, e:
            logger.error(e)

    def _decode(self, cmd, value):
        cmd = cmd.lower()

        if cmd == 'bass' or cmd == 'treble' or cmd == 'balance':
            return int(round(float(value) * (128.0 / 10.0)))
        elif cmd == 'loudness' or cmd == 'status' or cmd == 'mute':
            return value == 'ON'
        elif cmd == 'turnonvolume' or cmd == 'volume':
            return int(round(float(value) * (255.0 / 50.0)))
        elif cmd == 'partymode' or cmd == 'donotdisturb':
            return value.lower()
        elif cmd == 'currentsource':
            return value

    def found_terminator(self):
        data = self.buffer
        self.buffer = ''
        self._parse_response(data)

    def handle_connect(self):
        self.terminator = RESP_DELIMITER
        self._watch_system()

        zones = []
        for path in self.params:
            p = self.params[path]
            key = '{0}.{1}'.format(p['c'], p['z'])
            if not key in zones:
                zones.append(key)
                self._watch_zone(p['c'], p['z'])

    def run(self):
        self.alive = True

    def stop(self):
        self.alive = False

        for path in self._timers:
            self._timers[path].cancel()

        self.handle_close()
