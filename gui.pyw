import ctypes
import mp_controller as mp
import struct
import sys
import win32clipboard


from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QKeySequence

# Subclass QMainWindow to customise your application's main window
class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
     
        self.setGeometry(0, 0, 400, 300)

        # start the MobilePass all and hide it
        self.mp_instance = mp.MPController()
        self.mp_instance.start()
        self.mp_instance.toggle_vis()

        # put in a shortcut to it
        self.mp_toggle = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        self.mp_toggle.activated.connect(self.mp_instance.toggle_vis)

        # restart the mobile pass application
        self.mp_restart = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self.mp_restart.activated.connect(self.restart_mp)

        # put in a shortcut to copy pin
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.copy_shortcut.activated.connect(self.copy_clicked)
        
        # init vars
        self.secret = ""
        self.countDown = 0
        self.layout_setting = -1 #-1 default 0 = verticle /1 = horizontal
        # store token that was last written to file
        self.lastSavedToken = ""
        self.invalWarn=False

        self.settings = QtCore.QSettings("mp_gui", "mp_gui")
        self.setWindowTitle("MobilePasser")

        # setup our icon
        icon = QIcon("icon.ico")
        self.setWindowIcon(icon)
        # stop windows from using python icon in task bar
        appid = "python.mobilepass.gui"  # arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)

        # add a text editor for notes
        self.p_text = QPlainTextEdit(self)
        self.p_text.setSizePolicy(
            QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.MinimumExpanding,
                QtWidgets.QSizePolicy.MinimumExpanding,
            )
        )
        stylesheet = """
            QProgressBar{
                background-color: LightSlateGrey;
                border: 2px solid black;
                border-radius: 5px;
                text-align: center;
                font-size: 30px;
                color: Ivory;
            }
            QProgressBar::chunk {
                background-color: green;
                width: 1px;
                margin: 0px;
            }
            QLabel{
                font-size: 30px;
                background-color: LightSlateGrey;
                color: Ivory;
                border-radius: 5px;
                border: 2px solid black;
            }
            """

        # add layout for MP
        # add pin related stuff
        self.pin_label = QLabel("Pin")
        self.pin_label.setStyleSheet(stylesheet)
        self.pin_label.setFixedHeight(35)
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.returnPressed.connect(self.get_pin_input)
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setAlignment(QtCore.Qt.AlignCenter) 

        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self.copy_clicked)
        self.copy_button.setText("Copy Passcode")
        self.copy_button.hide()

        self.pbar = QProgressBar()
        self.pbar.setMaximum(29)
        self.pbar.setFormat("%v")
        self.pbar.setAlignment(Qt.AlignCenter)
        self.pbar.setRange(0, 29)
        self.pbar.setFixedHeight(35)
        self.pbar.setStyleSheet(stylesheet)

        # setup the horizontal/verticle layouts
        self.h_layout = QHBoxLayout()
        self.mp_layout = QVBoxLayout()
        self.mp_layout.setSpacing(5)
        self.mp_layout.setAlignment(Qt.AlignTop) 

        self.main_widget = QWidget()

        # set initial state
        self.window_state_enter_pin()

        # look at our settings to see if there is a setting called geometry saved.
        # Otherwise we default to an empty string
        geometry = self.settings.value("geometry", bytes("", "utf-8"))

        # restoreGeometry that will restore whatever values we give it.
        self.restoreGeometry(geometry)

        # kick off the application
        self.main_timer = QTimer()
        self.main_timer.timeout.connect(self.main_loop)
        self.main_timer.start(100)

    def main_loop(self):

        if self.mp_instance.running:

            state = self.mp_instance.find_state()
            if (state & mp.MP_SELECT_ITEM) == mp.MP_SELECT_ITEM:
                self.mp_instance.list_select()
            elif (state & mp.MP_INVALID_PIN) == mp.MP_INVALID_PIN and self.invalWarn == False:
                self.set_invalid_pin()
            elif (state & mp.MP_INVALID_PIN) == mp.MP_INVALID_PIN and self.invalWarn == True and len(self.secret) > 0:
                self.mp_instance.enter_pin(self.secret)
                self.invalWarn = False
            elif (state & mp.MP_INVALID_TOK) == mp.MP_INVALID_TOK:
                pass
            elif ((state & mp.MP_ENTER_PIN) == mp.MP_ENTER_PIN) and len(self.secret) > 0:
                self.mp_instance.enter_pin(self.secret)
            elif (state & mp.MP_TOKEN) == mp.MP_TOKEN:
                result = self.mp_instance.get_token()
                #split in the middle of the token.
                if(len(result) == 2):
                    result_len = len(result[1])
                    split = int(result_len / 2)
                    self.pbar.setValue(int(result[0]))
                    self.pbar.setFormat("{0} {1}".format(result[1][:split], result[1][split:]))
                    self.save_token(result[1])

    # rename return_pressed
    def get_pin_input(self):
        self.secret = self.pin_input.text()

        # swap state of pin gathering
        self.copy_button.show()
        self.pbar.show()

        self.pin_label.hide()
        self.pin_input.hide()


    def set_invalid_pin(self):
        self.pin_label.setText("Invalid Pin")
        self.copy_button.hide()
        self.pbar.hide()
        self.invalWarn = True
        self.pin_label.show()
        self.pin_input.show()
        self.pin_input.setText('')
        self.secret = ''

    def save_token(self, token_text):
        # only save when it changes
        if self.lastSavedToken != token_text:
            with open("token.txt", "w") as tok_file:
                tok_file.write(token_text)
            self.lastSavedToken = token_text

    def restart_mp(self):
        self.mp_instance.stop()
        self.mp_instance.start()
        self.mp_instance.toggle_vis()


    def copy_clicked(self):
        out = self.pbar.format().replace(" ", "")
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(out, win32clipboard.CF_TEXT)
        win32clipboard.CloseClipboard()

    def window_state_enter_pin(self):
        # hide all token related functions
        self.copy_button.hide()
        self.pbar.hide()

        # show pin gathering functions
        self.pin_label.show()
        self.pin_input.show()


    def window_state_show_token(self):
        self.pin_label.hide()
        self.pin_input.hide()


    def clean_layout(self):
        self.pin_label.setParent(None)
        self.pin_input.setParent(None)
        self.pbar.setParent(None)
        self.copy_button.setParent(None)
        self.p_text.setParent(None)
        self.mp_layout.setParent(None)


    def vert_layout(self):
        print("vert_layout")
        self.mp_layout.addWidget(self.pin_label)
        self.mp_layout.addWidget(self.pin_input)
        self.mp_layout.addWidget(self.pbar)
        self.mp_layout.addWidget(self.copy_button)
        self.mp_layout.addWidget(self.p_text, stretch=100)
        self.setMinimumSize(200, 500)
        self.pin_label.setMinimumWidth(100)
        self.pin_input.setMinimumWidth(100)
        self.pbar.setMinimumWidth(100)
        self.copy_button.setMinimumWidth(100)
        self.h_layout.addLayout(self.mp_layout)
        self.main_widget.setLayout(self.h_layout)
        self.setCentralWidget(self.main_widget)
        self.layout_setting = 0


    def horz_layout(self):
        print("horz_layout")
        self.mp_layout.addWidget(self.pin_label)
        self.mp_layout.addWidget(self.pin_input)
        self.mp_layout.addWidget(self.pbar)
        self.mp_layout.addWidget(self.copy_button)     
        self.h_layout.addWidget(self.p_text, stretch=100)
        self.pin_label.setMinimumWidth(150)
        self.pin_input.setMinimumWidth(150)
        self.pbar.setMinimumWidth(150)
        self.copy_button.setMinimumWidth(150)
        self.h_layout.addLayout(self.mp_layout)
        self.main_widget.setLayout(self.h_layout)
        self.setCentralWidget(self.main_widget)
        self.layout_setting = 1


    def set_layout(self):
        rect = self.geometry()
        vert =  (rect.width() < rect.height() / 2)

        if( vert and self.layout_setting != 0):
            self.clean_layout()
            self.vert_layout()
        elif(not vert and self.layout_setting != 1):
            self.clean_layout()
            self.horz_layout()


    def resizeEvent(self, event):
        self.set_layout()
        return super(MainWindow, self).resizeEvent(event)


    def closeEvent(self, event):
        geometry = self.saveGeometry()
        self.settings.setValue("geometry", geometry)
        self.mp_instance.stop()
        super(MainWindow, self).closeEvent(event)


if __name__ == "__main__":
    if 8 * struct.calcsize("P") != 64:
        sys.exit("Sorry... Application only supports 64 bit python!")

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
