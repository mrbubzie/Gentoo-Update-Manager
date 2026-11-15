"""Embedded interactive PTY for Portage commands; no external terminal required."""
import errno
import os
import pty
import re
import select
import shutil
import signal
import struct
import fcntl
import termios
from PySide6.QtCore import Qt, QSocketNotifier, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPlainTextEdit,
    QLineEdit, QPushButton, QHBoxLayout, QMessageBox)

ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[@-_])')

class TransactionDialog(QDialog):
    completed = Signal(int)
    def __init__(self, parent, cmd, title):
        super().__init__(parent)
        self.setWindowTitle(title + ' — Gentoo Update Manager')
        self.resize(900, 610)
        self.pid = None
        self.fd = None
        self.returncode = None
        self._partial = ''
        self._last_cr = False
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('Interactive Portage transaction — review the output before approving changes.'))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(12000)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.output)
        controls = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText('Type a response and press Enter (e.g. y or n)')
        self.entry.returnPressed.connect(self.send_line)
        controls.addWidget(self.entry)
        self.send = QPushButton('Send')
        self.send.clicked.connect(self.send_line)
        controls.addWidget(self.send)
        lay.addLayout(controls)
        bottom = QHBoxLayout()
        self.state = QLabel('Starting…')
        bottom.addWidget(self.state, 1)
        self.cancel = QPushButton('Cancel transaction')
        self.cancel.clicked.connect(self.cancel_transaction)
        bottom.addWidget(self.cancel)
        self.close_btn = QPushButton('Close')
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        bottom.addWidget(self.close_btn)
        lay.addLayout(bottom)
        self._start(cmd)

    def _append(self, data):
        # Strip terminal formatting while retaining readable Portage prompts.
        data = ANSI.sub('', data).replace('\r\n', '\n').replace('\r', '\n')
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(data)
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def _start(self, cmd):
        if os.geteuid() != 0:
            if shutil.which('pkexec'):
                cmd = ['pkexec'] + cmd
            elif shutil.which('sudo'):
                cmd = ['sudo'] + cmd
            elif shutil.which('doas'):
                cmd = ['doas'] + cmd
            else:
                self._append('No authentication tool found. Install polkit (pkexec), sudo, or doas.\n')
                self._finish(127)
                return
        try:
            pid, fd = pty.fork()
        except OSError as e:
            self._append(f'Unable to open PTY: {e}\n')
            self._finish(127)
            return
        if pid == 0:
            try:
                os.environ['TERM'] = os.environ.get('TERM', 'xterm-256color')
                os.execvp(cmd[0], cmd)
            except Exception as exc:
                os.write(2, f'Could not start command: {exc}\n'.encode())
                os._exit(127)
        self.pid, self.fd = pid, fd
        fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 36, 110, 0, 0))
        except OSError:
            pass
        self.notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._read)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(150)
        self.state.setText('Running — input is available below')
        self.entry.setFocus()

    def _read(self, *_):
        if self.fd is None:
            return
        try:
            while True:
                data = os.read(self.fd, 65536)
                if not data:
                    break
                self._append(data.decode('utf-8', errors='replace'))
        except BlockingIOError:
            pass
        except OSError as e:
            if e.errno != errno.EIO:
                self._append(f'\nPTY read error: {e}\n')

    def _poll(self):
        if self.pid is None:
            return
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid:
            self._read()
            code = os.waitstatus_to_exitcode(status)
            self._finish(code)

    def _finish(self, code):
        if getattr(self, 'timer', None):
            self.timer.stop()
        if getattr(self, 'notifier', None):
            self.notifier.setEnabled(False)
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.pid = None
        self.returncode = code
        self._append(f'\n\nTransaction finished (exit code {code}).\n')
        self.state.setText('Completed successfully' if code == 0 else f'Finished with exit code {code}')
        self.entry.setEnabled(False)
        self.send.setEnabled(False)
        self.cancel.setEnabled(False)
        self.close_btn.setEnabled(True)
        self.completed.emit(code)

    def send_line(self):
        if self.fd is None:
            return
        try:
            os.write(self.fd, (self.entry.text() + '\n').encode('utf-8'))
            self.entry.clear()
        except OSError as e:
            self._append(f'\nUnable to send input: {e}\n')

    def cancel_transaction(self):
        if self.pid is None:
            return
        if QMessageBox.question(self, 'Cancel operation?',
                'Interrupting Portage during a transaction may leave packages partially updated. Send Ctrl+C?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                os.write(self.fd, b'\x03')
            except OSError:
                pass

    def reject(self):
        if self.pid is not None:
            QMessageBox.information(self, 'Transaction running',
                'Wait for Portage to finish, or use Cancel transaction to interrupt it.')
            return
        super().reject()
