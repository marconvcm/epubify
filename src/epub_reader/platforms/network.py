"""Foreground-only Android multicast lease; desktop/iOS use ordinary sockets."""

import importlib
from typing import Any

from PySide6.QtCore import QSysInfo


class NetworkLease:
    def __init__(self) -> None:
        self.lock: Any = None

    def acquire(self) -> None:
        if QSysInfo.productType() != "android":
            return
        # python-for-android must build pyjnius for the target ABI. QtNative
        # supplies the Qt activity; PythonActivity belongs to a different bootstrap.
        jni = importlib.import_module("jnius")
        activity = jni.autoclass("org.qtproject.qt.android.QtNative").activity()
        version = jni.autoclass("android.os.Build$VERSION")
        if (
            version.SDK_INT >= 37
            and activity.getApplicationInfo().targetSdkVersion >= 37
            and activity.checkSelfPermission("android.permission.ACCESS_LOCAL_NETWORK") != 0
        ):
            raise PermissionError("Local network permission has not been granted.")
        context = activity.getApplicationContext()
        wifi = context.getSystemService("wifi")
        self.lock = wifi.createMulticastLock("epubify-local-sync")
        self.lock.setReferenceCounted(False)
        self.lock.acquire()

    def release(self) -> None:
        if self.lock is not None:
            if self.lock.isHeld():
                self.lock.release()
            self.lock = None
