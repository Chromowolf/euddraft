#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Copyright (c) 2014 trgk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import os
import subprocess
import sys
import traceback

import eudplib as ep

import freezeMpq
import msgbox
import scbank_core
from freeze import decryptOffsets, encryptOffsets, obfpatch, obfunpatch, unFreeze
from msgbox import MB_ICONHAND, MB_OK, MessageBeep, MessageBox
from pluginLoader import (
    isFreezeIssued,
    isPromptIssued,
    isSCBankIssued,
    loadPluginsFromConfig,
)
from readconfig import readconfig


def createPayloadMain(pluginList, pluginFuncDict):
    @ep.EUDFunc
    def payloadMain():
        """Main function of euddraft payload."""
        # init plugins
        if isFreezeIssued():
            unFreeze()
            # ep.PRT_SetInliningRate(0.05)

        if isSCBankIssued():
            scbank_core.onPluginStart()

        for pluginName in pluginList:
            onPluginStart = pluginFuncDict[pluginName][0]
            onPluginStart()

        # Do trigger loop
        if ep.EUDInfLoop()():
            if isFreezeIssued():
                decryptOffsets()
                obfpatch()

            if isSCBankIssued():
                scbank_core.beforeTriggerExec()

            for pluginName in pluginList:
                beforeTriggerExec = pluginFuncDict[pluginName][1]
                beforeTriggerExec()

            ep.RunTrigTrigger()

            for pluginName in reversed(pluginList):
                afterTriggerExec = pluginFuncDict[pluginName][2]
                afterTriggerExec()

            if isSCBankIssued():
                scbank_core.afterTriggerExec()

            if isFreezeIssued():
                obfunpatch()
                encryptOffsets()

            ep.EUDDoEvents()

        ep.EUDEndInfLoop()

    return payloadMain


##############################

if getattr(sys, "frozen", False):
    # frozen
    basepath = os.path.dirname(sys.executable)
else:
    # unfrozen
    basepath = os.path.dirname(os.path.realpath(__file__))

globalPluginPath = os.path.join(basepath, "plugins").lower()
# cx_Freeze modifies ep.__file__ to library.zip. So we use this convoluted
# way of getting eudplib install path.
epPath = os.path.dirname(ep.eudplibVersion.__code__.co_filename).lower()
edPath = os.path.dirname(MessageBox.__code__.co_filename).lower()


def isEpExc(s):
    s = s.lower()
    return (
        epPath in s
        or edPath in s
        or "<frozen " in s
        or (basepath in s and globalPluginPath not in s)
        or "runpy.py" in s
        or s.startswith('  file "eudplib')
    )


##############################


def applyEUDDraft(sfname):
    try:
        config = readconfig(sfname)
        mainSection = config["main"]
        ifname = mainSection["input"]
        ofname = mainSection["output"]
        if ifname == ofname:
            raise RuntimeError("input and output file should be different.")

        try:
            if mainSection["debug"]:
                ep.EPS_SetDebug(True)
        except KeyError:
            pass
        try:
            unitname_encoding = mainSection["decodeUnitName"]
            from eudplib.core.mapdata.tblformat import DecodeUnitNameAs

            DecodeUnitNameAs(unitname_encoding)
        except KeyError:
            pass
        try:
            if mainSection["objFieldN"]:
                from eudplib.eudlib.objpool import SetGlobalPoolFieldN

                field_n = int(mainSection["objFieldN"])
                SetGlobalPoolFieldN(field_n)
        except KeyError:
            pass

        sectorSize = 15
        try:
            if mainSection["sectorSize"]:
                sectorSize = int(mainSection["sectorSize"])
        except KeyError:
            pass
        except:
            sectorSize = None

        print("---------- Loading plugins... ----------")
        ep.LoadMap(ifname)
        pluginList, pluginFuncDict = loadPluginsFromConfig(ep, config)

        print("--------- Injecting plugins... ---------")

        payloadMain = createPayloadMain(pluginList, pluginFuncDict)
        ep.CompressPayload(True)

        if ep.IsSCDBMap():
            if isFreezeIssued():
                raise RuntimeError(
                    "Can't use freeze protection on SCDB map!\nDisable freeze by following plugin settings:\n\n[freeze]\nfreeze : 0\n"
                )
            print("SCDB - sectorSize disabled")
            sectorSize = None
        elif isFreezeIssued():
            # FIXME: Add variable sectorSize support for freeze
            print("Freeze - sectorSize disabled")
            sectorSize = None
        ep.SaveMap(ofname, payloadMain, sectorSize=sectorSize)

        if isFreezeIssued():
            if isPromptIssued():
                print("Freeze - prompt enabled ")
                sys.stdout.flush()
                os.system("pause")
            print("[Stage 4/3] Applying freeze mpq modification...")
            try:
                ofname = ofname.encode("mbcs")
            except LookupError:
                ofname = ofname.encode(sys.getfilesystemencoding())
            ret = freezeMpq.applyFreezeMpqModification(ofname, ofname)
            if ret != 0:
                raise RuntimeError("Error on mpq protection (%d)" % ret)

        MessageBeep(MB_OK)
        return True

    except Exception as e:
        print("==========================================")
        MessageBeep(MB_ICONHAND)
        exc_type, exc_value, exc_traceback = sys.exc_info()
        excs = traceback.format_exception(exc_type, exc_value, exc_traceback)
        formatted_excs = []

        for i, exc in enumerate(excs):
            if isEpExc(exc) and not all(isEpExc(e) for e in excs[i + 1 : -1]):
                continue
            ver = ep.eudplibVersion()
            plibPath = (
                'File "C:\\Py\\lib\\site-packages\\eudplib-%s-py3.8-win32.egg\\eudplib\\'
                % ver
            )
            exc.replace(plibPath, 'eudplib File"')
            formatted_excs.append(exc)

        print("[Error] %s" % e, "".join(formatted_excs), file=sys.stderr)
        if msgbox.isWindows:
            msgbox.SetForegroundWindow(msgbox.GetConsoleWindow())
        return False
