#!/usr/bin/env python
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
import os
import shutil

logger = logging.getLogger('')


def parse_tpl(template, replace):
    try:
        with open(template, 'r') as f:
            tpl = f.read()
    except IOError, e:
        logger.error("Could not read template file: {0}".format(template))
        return ''
    for s, r in replace:
        tpl = tpl.replace(s, r)
    return tpl


def room(smarthome, room, tpldir):
    widgets = ''
    if 'visu_img' in room.conf:
        rimg = room.conf['visu_img']
    else:
        rimg = ''
    for item in smarthome.find_children(room, 'visu_widget'):
        if 'visu_img' in item.conf:
            img = item.conf['visu_img']
        else:
            img = ''
        if isinstance(item.conf['visu_widget'], list):
            widget = ', '.join(item.conf['visu_widget'])
        else:
            widget = item.conf['visu_widget']
        widgets += parse_tpl(tpldir + '/widget.html', [('{{ visu_name }}', str(item)), ('{{ visu_img }}', img), ('{{ visu_widget }}', widget), ('item.name', str(item)), ("'item", item.id())])
    return parse_tpl(tpldir + '/room.html', [('{{ visu_name }}', str(room)), ('{{ visu_widgets }}', widgets), ('{{ visu_img }}', rimg)])


def pages(smarthome, directory):
    nav_lis = ''
    outdir = directory + '/pages/smarthome'
    tpldir = directory + '/pages/base/tpl'
    tmpdir = directory + '/temp'
    # clear temp directory
    if not os.path.isdir(tmpdir):
        logger.warning("Could not find directory: {0}".format(tmpdir))
        return
    for dn in os.listdir(tmpdir):
        if len(dn) != 2:  # only delete Twig temp files
            continue
        dp = os.path.join(tmpdir, dn)
        try:
            if os.path.isdir(dp):
                shutil.rmtree(dp)
        except Exception, e:
            logger.warning("Could not delete directory {0}: {1}".format(dp, e))
    # remove old dynamic files
    if not os.path.isdir(outdir):
        logger.warning("Could not find directory: {0}".format(outdir))
        return
    for fn in os.listdir(outdir):
        fp = os.path.join(outdir, fn)
        try:
            if os.path.isfile(fp):
                os.unlink(fp)
        except Exception, e:
            logger.warning("Could not delete file {0}: {1}".format(fp, e))
    for item in smarthome.find_items('visu_page'):
        r = room(smarthome, item, tpldir)
        if 'visu_img' in item.conf:
            img = item.conf['visu_img']
        else:
            img = ''
        nav_lis += parse_tpl(tpldir + '/navi.html', [('{{ visu_page }}', item.id()), ('{{ visu_name }}', str(item)), ('{{ visu_img }}', img)])
        with open("{0}/{1}.html".format(outdir, item.id()), 'w') as f:
            f.write(r)
    nav = parse_tpl(tpldir + '/navigation.html', [('{{ visu_navis }}', nav_lis)])
    with open(outdir + '/navigation.html', 'w') as f:
        f.write(nav)
    shutil.copy(tpldir + '/rooms.html', outdir + '/')
    shutil.copy(tpldir + '/index.html', outdir + '/')
