# -*- coding: utf-8 -*-

import sys
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import QSize
from PyQt4.QtGui import QCheckBox, QMainWindow, QVBoxLayout, QHBoxLayout, QLayout, QLabel, QLineEdit, QWidget

from pizco import Proxy


class ControlForm(QtGui.QDialog):

    def __init__(self, proxy, parent=None):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)

        self.proxy = proxy
        self.proxy.lights_on_changed.connect(self.object_lights_on_changed)
        self.proxy.door_open_changed.connect(self.object_door_open_changed)
        self.proxy.color_changed.connect(self.object_color_changed)

    def on_lights_on_changed(self, value):
        proxy.lights_on = self.lights.isChecked()

    def on_door_open_changed(self, value):
        proxy.door_open = self.door_open.isChecked()

    def object_lights_on_changed(self, value, old_value, other):
        if value == self.lights.isChecked():
            return
        self.lights.setChecked(value)

    def object_door_open_changed(self, value, old_value, other):
        if value == self.door_open.isChecked():
            return
        self.door_open.setChecked(value)

    def object_color_changed(self, value, old_value, other):
        if value == self.color.text():
            return
        self.color.setText(value)
        self.color.textChanged.emit(value)

    def on_color_text_changed(self, value):
        self.color_box.setStyleSheet("QLabel { background-color: %s }" % value)

    def setupUi(self, parent):
        self.resize(275, 172)
        self.setWindowTitle('House')

        self.layout = QVBoxLayout(parent)
        self.layout.setSizeConstraint(QLayout.SetFixedSize)
        #align = (Qt.AlignRight | Qt.AlignTrailing | Qt.AlignVCenter)

        self.layout1 = QHBoxLayout()
        self.label1 = QLabel()
        self.label1.setMinimumSize(QSize(100, 0))
        self.label1.setText('Lights:')
        self.lights = QCheckBox()
        self.lights.setTristate(False)
        self.layout1.addWidget(self.label1)
        self.layout1.addWidget(self.lights)

        self.layout2 = QHBoxLayout()
        self.label2 = QLabel()
        self.label2.setMinimumSize(QSize(100, 0))
        self.label2.setText('Front door:')
        self.door_open = QCheckBox()
        self.door_open.setTristate(False)
        self.layout2.addWidget(self.label2)
        self.layout2.addWidget(self.door_open)

        self.layout3 = QHBoxLayout()
        self.label3 = QLabel()
        self.label3.setMinimumSize(QSize(100, 0))
        self.label3.setText('Color:')
        self.color = QLineEdit()
        self.color.setReadOnly(True)
        self.color.textChanged.connect(self.on_color_text_changed)
        self.color_box = QLabel()
        self.color_box.setText('  ')
        self.layout3.addWidget(self.label3)
        self.layout3.addWidget(self.color)
        self.layout3.addWidget(self.color_box)

        self.lights.stateChanged.connect(self.on_lights_on_changed)
        self.door_open.stateChanged.connect(self.on_door_open_changed)

        self.layout.addLayout(self.layout1)
        self.layout.addLayout(self.layout2)
        self.layout.addLayout(self.layout3)


if __name__ == "__main__":
    proxy = Proxy('tcp://127.0.0.1:8000')
    app = QtGui.QApplication(sys.argv)
    main = ControlForm(proxy)
    main.show()
    if sys.platform.startswith('darwin'):
        main.raise_()
    sys.exit(app.exec_())
