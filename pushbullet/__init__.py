#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
#  Copyright 2011 KNX-User-Forum e.V.           http://knx-user-forum.de/
#########################################################################
#  This file is part of SmartHome.py.    http://mknx.github.io/smarthome/
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

import json
import requests
import magic
import os

logger = logging.getLogger("Pushbullet")

class Pushbullet(object):
    _apiurl = "https://api.pushbullet.com/v2/pushes"
    _upload_apiurl = "https://api.pushbullet.com/v2/upload-request"

    def __init__(self, smarthome, apikey=None, deviceid=None):
        self._apikey = apikey
        self._deviceid = deviceid
        self._sh = smarthome

    def run(self):
        pass

    def stop(self):
        pass

    def note(self, title, body, deviceid=None, apikey=None):
        self._push(data={"type": "note", "title": title, "body": body}, deviceid=deviceid, apikey=apikey)

    def link(self, title, url, deviceid=None, apikey=None, body=None):
        self._push(data={"type": "link", "title": title, "url": url, "body": body}, deviceid=deviceid, apikey=apikey)

    def address(self, name, address, deviceid=None, apikey=None):
        self._push(data={"type": "address", "name": name, "address": address}, deviceid=deviceid, apikey=apikey)

    def list(self, title, items, deviceid=None, apikey=None):
        self._push(data={"type": "list", "title": title, "items": items}, deviceid=deviceid, apikey=apikey)

    def file(self, filepath, deviceid=None, apikey=None, body=None):
        if os.path.exists(filepath) == False:
            logger.error("Trying to push non existing file: {0}".format(filepath))
            return

        self._upload_and_push_file(filepath, body, deviceid, apikey)

    def _upload_and_push_file(self, filepath, body=None, deviceid=None, apikey=None):
        try:
            headers = {"User-Agent": "SmartHome.py", "Content-Type": "application/json"}

            if apikey == None:
                apikey = self._apikey

            upload_request_response = requests.post(self._upload_apiurl, data={"file_name": os.path.basename(filepath), "file_type": magic.from_file(filepath, mime=True)}, headers=headers, auth=apikey)

            if self._is_response_ok(upload_request_response) == True:
                data = upload_request_response.json()
                upload_response = requests.post(data["upload_url"], data=data["data"], headers={"User-Agent": "SmartHome.py"}, files={"file": open(filepath, "rb")}, auth=apikey)

                if self._is_response_ok(upload_response) == True:
                    self._push(data={"type": "file", "file_name": data["file_name"], "file_type": data["file_type"], "file_url": data["file_url"], "body": body}, deviceid=deviceid, apikey=apikey)
                else:
                    logger.error("Error while uploading file: {0}".format(upload_response.text))
            else:
                logger.error("Error while requesting upload: {0}".format(upload_request_response.text))
        except RequestException as exception:
            logger.error("Could not send file to Pushbullet notification. Error: {0}".format(exception))

    def _push(self, data, deviceid=None, apikey=None):
        if apikey == None:
            apikey = self._apikey

        data["device_iden"] = self._deviceid
        if deviceid:
            data["device_iden"] = deviceid

        try:
            response = requests.post(self._apiurl, data=json.dumps(data), headers={"User-Agent": "SmartHome.py", "Content-Type": "application/json"}, auth=apikey)
            if self._is_response_ok(response) == False:
                logger.error("Could not send Pushbullet notification. Error: {0}".format(response.text))
        except RequestException as exception:
            logger.error("Could not send Pushbullet notification. Error: {0}".format(exception))

    @staticmethod
    def _is_response_ok(response):
        if response.status_code == 200:
            logger.debug("Pushbullet returns: Notification submitted.")
            return True
        elif response.status_code == 400:
            logger.warning("Pushbullet returns: Bad Request - Often missing a required parameter.")
        elif response.status_code == 401:
            logger.warning("Pushbullet returns: Unauthorized - No valid API key provided.")
        elif response.status_code == 402:
            logger.warning("Pushbullet returns: Request Failed - Parameters were valid but the request failed.")
        elif response.status_code == 403:
            logger.warning("Pushbullet returns: Forbidden - The API key is not valid for that request.")
        elif response.status_code == 404:
            logger.warning("Pushbullet returns: Not Found - The requested item doesn't exist.")
        elif response.status_code >= 500:
            logger.warning("Pushbullet returns: Server errors - something went wrong on PushBullet's side.")
        else:
            logger.error("Pushbullet returns unknown HTTP status code = {0}".format(response.status_code))
        return False
