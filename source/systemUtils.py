# -*- coding: UTF-8 -*-
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2020 NV Access Limited, Łukasz Golonka
# This file may be used under the terms of the GNU General Public License, version 2 or later.
# For more details see: https://www.gnu.org/licenses/gpl-2.0.html

""" System related functions."""

import ctypes
import winKernel
import shellapi
import winUser
import os


def openUserConfigurationDirectory():
	"""Opens directory containing config files for the current user"""
	import globalVars
	try:
		# configPath is guaranteed to be correct for NVDA, however it will not exist for NVDA_slave.
		path = globalVars.appArgs.configPath
	except AttributeError:
		import config
		path = config.getUserDefaultConfigPath()
		if not path:
			raise ValueError("no user default config path")
		config.initConfigPath(path)
	shellapi.ShellExecute(0, None, path, None, None, winUser.SW_SHOWNORMAL)


TokenUIAccess = 26


def hasUiAccess():
	token = ctypes.wintypes.HANDLE()
	ctypes.windll.advapi32.OpenProcessToken(
		ctypes.windll.kernel32.GetCurrentProcess(),
		winKernel.MAXIMUM_ALLOWED,
		ctypes.byref(token)
	)
	try:
		val = ctypes.wintypes.DWORD()
		ctypes.windll.advapi32.GetTokenInformation(
			token,
			TokenUIAccess,
			ctypes.byref(val),
			ctypes.sizeof(ctypes.wintypes.DWORD),
			ctypes.byref(ctypes.wintypes.DWORD())
		)
		return bool(val.value)
	finally:
		ctypes.windll.kernel32.CloseHandle(token)


def execElevated(path, params=None, wait=False, handleAlreadyElevated=False):
	import subprocess
	if params is not None:
		params = subprocess.list2cmdline(params)
	sei = shellapi.SHELLEXECUTEINFO(lpFile=os.path.abspath(path), lpParameters=params, nShow=winUser.SW_HIDE)
	# IsUserAnAdmin is apparently deprecated so may not work above Windows 8
	if not handleAlreadyElevated or not ctypes.windll.shell32.IsUserAnAdmin():
		sei.lpVerb = "runas"
	if wait:
		sei.fMask = shellapi.SEE_MASK_NOCLOSEPROCESS
	shellapi.ShellExecuteEx(sei)
	if wait:
		try:
			h = ctypes.wintypes.HANDLE(sei.hProcess)
			msg = ctypes.wintypes.MSG()
			while ctypes.windll.user32.MsgWaitForMultipleObjects(1, ctypes.byref(h), False, -1, 255) == 1:
				while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
					ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
					ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
			return winKernel.GetExitCodeProcess(sei.hProcess)
		finally:
			winKernel.closeHandle(sei.hProcess)


def terminateRunningNVDA(window):
	processID, threadID = winUser.getWindowThreadProcessID(window)
	winUser.PostMessage(window, winUser.WM_QUIT, 0, 0)
	h = winKernel.openProcess(winKernel.SYNCHRONIZE, False, processID)
	if not h:
		# The process is already dead.
		return
	try:
		res = winKernel.waitForSingleObject(h, 4000)
		if res == 0:
			# The process terminated within the timeout period.
			return
	finally:
		winKernel.closeHandle(h)

	# The process is refusing to exit gracefully, so kill it forcefully.
	forceTerminateProcess(processID)


def forceTerminateProcess(processID):
	h = winKernel.openProcess(winKernel.PROCESS_TERMINATE | winKernel.SYNCHRONIZE, False, processID)
	if h == 0:
		ctypes.WinError()
	try:
		winKernel.TerminateProcess(h, 1)
		winKernel.waitForSingleObject(h, 2000)
	finally:
		winKernel.closeHandle(h)


def getRunningProcessInstances(name: str):
	"""Retrieves Process Identifiers for running processes with the specified name, if any."""
	import comtypes.client
	wmi = comtypes.client.CoGetObject("winmgmts:")
	# WMI requires paths with backslahses escaped
	escapedName = name.replace("\\", r"\\")
	processes = wmi.ExecQuery(f"SELECT ProcessId FROM Win32_Process WHERE ExecutablePath = '{escapedName}'")
	# We need the number of processes to enumerate the result.
	# If we somehow threw an invalid query at WMI, fetching the count will reveal that with a COMError,
	# which should be caught by the caller
	count = processes.Count
	return tuple(
		processes.ItemIndex(i).Properties_['ProcessId'].Value
		for i in range(count)
	)
