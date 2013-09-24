#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
# Copyright 2013 KNX-User-Forum e.V.            http://knx-user-forum.de/
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
#  along with SmartHome.py. If not, see <http://www.gnu.org/licenses/>.
#########################################################################

import logging
import threading
import json
import lib.my_asynchat

logger = logging.getLogger('')


class XBMC():

    def __init__(self, smarthome):
        self._sh = smarthome
        self._boxes = []

    def run(self):
        self.alive = True

    def stop(self):
        self.alive = False
        for box in self._boxes:
            box.handle_close()

    def notify_all(self, title, message, image=None):
        for box in self._boxes:
            box.notify(title, message, image)

    def parse_item(self, item):
        if 'xbmc_host' in item.conf:
            self._boxes.append(xbmc(self._sh, item))


class xbmc(lib.my_asynchat.AsynChat):

    _notification_time = 10000
    _listen_keys = ['volume', 'mute', 'title', 'media', 'state']
    _send_keys = {'volume': 'Application.SetVolume', 'mute': 'Application.SetMute'}

    def __init__(self, smarthome, item):
        if 'xbmc_port' in item.conf:
            port = int(item.conf['xbmc_port'])
        else:
            port = 9090
        host = item.conf['xbmc_host']
        lib.my_asynchat.AsynChat.__init__(self, smarthome, host, port)
        self.terminator = '}'
        self._sh = smarthome
        smarthome.monitor_connection(self)
        self._id = 1
        self._rid = None
        self._cmd_lock = threading.Lock()
        self._reply_lock = threading.Condition()
        self._reply = None
        self._items = {'state': item}
        for child in self._sh.find_children(item, 'xbmc_listen'):
            listen_to = child.conf['xbmc_listen']
            if listen_to in self._listen_keys:
                self._items[listen_to] = child
        for child in self._sh.find_children(item, 'xbmc_send'):
            send_to = child.conf['xbmc_send']
            if send_to in self._send_keys:
                child.add_trigger_method(self._send_value)
        item.notify = self.notify

    def notify(self, title, message, image=None):
        if image is None:
            self._send('GUI.ShowNotification', {'title': title, 'message': message, 'displaytime': self._notification_time})
        else:
            self._send('GUI.ShowNotification', {'title': title, 'message': message, 'image': image, 'displaytime': self._notification_time})

    def _send_value(self, item, caller=None, source=None, dest=None):
        if caller != 'XBMC':
            self._send(self._send_keys[item.conf['xbmc_send']], {item.conf['xbmc_send']: item()}, wait=False)

    def run(self):
        self.alive = True

    def _send(self, method, params=None, id=None, wait=True):
        self._cmd_lock.acquire()
        self._reply = None
        if id is None:
            self._id += 1
            id = self._id
            if id > 100:
                self._id = 0
        self._rid = id
        if params is not None:
            data = {"jsonrpc": "2.0", "id": id, "method": method, 'params': params}
        else:
            data = {"jsonrpc": "2.0", "id": id, "method": method}
        self._reply_lock.acquire()
        #logger.debug("XBMC sending: {0}".format(json.dumps(data, separators=(',', ':'))))
        self.push(json.dumps(data, separators=(',', ':')) + '\r\n')
        if wait:
            self._reply_lock.wait(2)
        self._reply_lock.release()
        reply = self._reply
        self._reply = None
        self._cmd_lock.release()
        return reply

    def _set_item(self, key, value):
        if key in self._items:
            self._items[key](value, 'XBMC')

    def found_terminator(self):
        self.buffer.extend(b'}')
        if self.buffer.count(b'{') == self.buffer.count(b'}'):
            event = json.loads(self.buffer.decode())
            self.buffer = bytearray()
            #logger.debug("XBMC receiving: {0}".format(event))
            if 'id' in event:
                if event['id'] == self._rid:
                    self._rid = None
                    self._reply = event
                self._reply_lock.acquire()
                self._reply_lock.notify()
                self._reply_lock.release()
                return
            if 'method' in event:
                if event['method'] == 'Player.OnPause':
                    self._items['state']('Pause', 'XBMC')
                elif event['method'] == 'Player.OnStop':
                    self._items['state']('Menu', 'XBMC')
                    self._items['media']('', 'XBMC')
                    self._items['title']('', 'XBMC')
                if event['method'] in ['Player.OnPlay']:
                    # use a different thread for event handling
                    self._sh.trigger('xmbc-event', self._parse_event, 'XBMC', value={'event': event})
                elif event['method'] in ['Application.OnVolumeChanged']:
                    if 'mute' in self._items:
                        self._set_item('mute', event['params']['data']['muted'])
                    if 'volume' in self._items:
                        self._set_item('volume', event['params']['data']['volume'])

    def _parse_event(self, event):
        if event['method'] == 'Player.OnPlay':
            result = self._send('Player.GetActivePlayers')['result'][0]
            playerid = result['playerid']
            typ = result['type']
            self._items['state']('Playing', 'XBMC')
            if typ == 'video':
                result = self._send('Player.GetItem', {"properties": ["title"], "playerid": playerid}, "VideoGetItem")['result']
                title = result['item']['title']
                typ = result['item']['type']
                self._items['media'](typ.capitalize(), 'XBMC')
            elif typ == 'audio':
                self._items['media'](typ.capitalize(), 'XBMC')
                result = self._send('Player.GetItem', {"properties": ["title", "artist"], "playerid": playerid}, "AudioGetItem")['result']
                artist = result['item']['artist'][0]
                title = artist + ' - ' + result['item']['title']
            elif typ == 'picture':
                self._items['media'](typ.capitalize(), 'XBMC')
                title = ''
            else:
                logger.warning("Unknown type: {0}".format(typ))
                return
            self._items['title'](title, 'XBMC')
