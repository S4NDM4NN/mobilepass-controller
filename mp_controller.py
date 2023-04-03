from ctypes import byref
from ctypes import c_int
from ctypes import c_int32
from ctypes import c_int64
from ctypes import c_size_t
from ctypes import c_uint32
from ctypes import c_uint64
from ctypes import windll
import ctypes
import os
import sys
import win32con
import win32gui
import win32process
import time

PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020

MEM_COMMIT = 0x00001000
MEM_DECOMMIT = 0x4000
MEM_RELEASE = 0x8000
MEM_RESERVE = 0x00002000
PAGE_READWRITE = 0x04

LVIF_STATE = 8
LVIS_SELECTED = 0x0002
LVM_FIRST = 0x1000
LVM_SETITEMSTATE = LVM_FIRST + 43


class LVITEMW(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("mask", c_uint32),  # 0
        ("iItem", c_int32),  # 4
        ("iSubItem", c_int32),  # 8
        ("state", c_uint32),  # 12
        ("stateMask", c_uint32),  # 16
        ("padding1", c_int),
        ("pszText", c_uint64),  # 20 --> 24 after padding (A pointer)
        ("cchTextMax", c_int32),  # 32
        ("iImage", c_int32),  # 36
        ("lParam", c_uint64),  # 40 (On 32 bit should be c_long which is 32 bits)
        ("iIndent", c_int32),  # 48
        ("iGroupId", c_int32),  # 52
        ("cColumns", c_uint32),  # 56
        ("padding2", c_int),
        ("puColumns", c_uint64),  # 60 --> 64 after padding (A pointer)
        ("piColFmt", c_int64),  # 72 (A pointer)
        ("iGroup", c_int32),  # 80
        ("padding3",c_int32),  # The total length was 84 before padding3 was added, which is not dividable by 8
    ]


MP_SELECT_ITEM = 1
MP_ENTER_PIN = 2
MP_TOKEN = 4
MP_INVALID_PIN = 8
MP_INVALID_TOK = 16


def _windowEnumerationHandler(hwnd, resultList):
    resultList.append((hwnd, win32gui.GetWindowText(hwnd), win32gui.GetClassName(hwnd)))


class MPController(object):
    def __init__(self):
        self.hwnd = 0
        self.state = 0
        self.visible = True
        self.running = True

    def start(self) -> bool:
        # check if mobilePass is running already
        if win32gui.FindWindow(None, "MobilePASS") != 0:
            self.hwnd = self._findMP()
            self.visible = bool(win32gui.IsWindowVisible(self.hwnd))
            return True

        # check the most likely place for program files
        programFiles = os.getenv("PROGRAMFILES(x86)")
        programFiles = (
                programFiles + "\\SafeNet\\Authentication\\MobilePASS\\MobilePASS.exe"
        )

        # if its not there try the other place
        if not os.path.exists(programFiles):
            programFiles = os.getenv("PROGRAMFILES")
            programFiles = (
                    programFiles + "\\SafeNet\\Authentication\\MobilePASS\\MobilePASS.exe"
            )

        # try starting it up
        try:
            os.startfile(programFiles)
            time.sleep(1)
        except SystemError:
            raise FileNotFoundError
        self.hwnd = self._findMP()
        self.running = True
        

    def stop(self) -> None:
        win32gui.SendMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        return

    def toggle_vis(self) -> None:
        """
        toggle the visibility of the MobilePass application
        :return:
        """
        # flip the bit of visible or not
        self.visible = not bool(win32gui.IsWindowVisible(self.hwnd))

        # set the right int for status
        status = win32con.SW_HIDE
        if self.visible:
            status = win32con.SW_SHOW

        win32gui.ShowWindow(self.hwnd, status)

    def enter_pin(self, pin: int) -> None:
        elements = self._dump_windows()
        conButton = None
        editField = None
        for elmt in elements:
            if elmt[2] == "Edit":
                editField = elmt[0]
            if elmt[1] == "Continue" and elmt[2] == "Button":
                conButton = elmt[0]

        if conButton and editField:
            win32gui.SendMessage(editField, win32con.WM_SETTEXT, 0, pin)
            win32gui.SendMessage(conButton, win32con.BM_CLICK, 0, 0)

    def get_token(self) -> list:
        out = []
        editField = None
        elements = self._dump_windows()
        for elmt in elements:
            if elmt[2] == "Edit":
                editField = elmt[0]
            elif elmt[2] == "Static" and len(elmt[1]) == 2:
                out.append(elmt[1])

        if editField:
            length = win32gui.SendMessage(editField, win32con.WM_GETTEXTLENGTH, 0, 0) * 2
            buffer = win32gui.PyMakeBuffer(length)
            win32gui.SendMessage(editField, win32con.WM_GETTEXT, length, buffer)
            out.append(buffer.tobytes().decode("UTF-16"))

        return out

    def _findMP(self):
        """
        find the running MobilePass proc
        :return: windowHandle
        """
        hwnd = 0
        while hwnd == 0:
            hwnd = win32gui.FindWindow(None, "MobilePASS")
        return hwnd

    def _dump_windows(self) -> list:
        children = []
        try:
            win32gui.EnumChildWindows(self.hwnd, _windowEnumerationHandler, children)
        except SystemError:
            pass
        return children

    def list_select(self):
        elements = self._dump_windows()
        for element in elements:
            if element[2] == "SysListView32":
                dwProcessId = win32process.GetWindowThreadProcessId(element[0])
                hproc = windll.kernel32.OpenProcess(
                    PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE,
                    False,
                    dwProcessId[1],
                )
                epLvi = windll.kernel32.VirtualAllocEx(
                    hproc, False, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
                )
                item = LVITEMW(
                    mask=LVIF_STATE, state=LVIS_SELECTED, stateMask=LVIS_SELECTED
                )
                windll.kernel32.WriteProcessMemory(
                    hproc, epLvi, item, sys.getsizeof(item), byref(c_size_t(0))
                )
                win32gui.SendMessage(element[0], LVM_SETITEMSTATE, 0, epLvi)
                windll.kernel32.VirtualFreeEx(
                    hproc, epLvi, 4096, MEM_DECOMMIT | MEM_RELEASE
                )
                windll.kernel32.CloseHandle(hproc)
                return
        return

    def find_state(self):
        elements = self._dump_windows()
        state = 0

        for elmt in elements:
            if str(elmt[1]).find("Attempts: ") != -1:
                state = state | MP_INVALID_PIN
            elif elmt[1] == "Token Authentication":
                state |= state | MP_ENTER_PIN
            elif elmt[1] == "Your Passcode":
                state |= state | MP_TOKEN
            elif elmt[1] == "Inactive Token":
                state |= state | MP_INVALID_TOK
            elif elmt[1] == "MobilePASS":
                state |= state | MP_SELECT_ITEM

        return state


def main(mp, pin):

    while mp.running:
        state = mp.find_state()
        if (state & MP_SELECT_ITEM) == MP_SELECT_ITEM:
            mp.list_select()
        elif (state & MP_INVALID_PIN) == MP_INVALID_PIN:
            return [-1,'Invalid Pin']
        elif (state & MP_INVALID_TOK) == MP_INVALID_TOK:
            return [-1,'Invalid Token']
        elif ((state & MP_ENTER_PIN) == MP_ENTER_PIN) and len(pin) > 0:
            mp.enter_pin(pin)
        elif (state & MP_TOKEN) == MP_TOKEN:
            token = mp.get_token()
            return token
        
        time.sleep(.1)
            

if __name__ == "__main__":

    if len(sys.argv) == 2:
        mp_instance = MPController()
        mp_instance.start()
        if(mp_instance.visible):
            mp_instance.toggle_vis()
        token = main(mp_instance, sys.argv[1])
        
        if(token[0] == -1): #error...
            print(f"There was an error: {token[1]}!")
        else:
            print(f"{token[0]} {token[1]}")

    else:
        print("Usage: mp_controller.py <pin>")


