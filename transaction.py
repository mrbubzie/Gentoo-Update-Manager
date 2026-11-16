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
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPlainTextEdit,
    QLineEdit, QPushButton, QHBoxLayout, QMessageBox)

ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[@-_])')

class TransactionPanel(QWidget):
    completed = Signal(int)
    back_requested = Signal()
    def __init__(self, parent):
        super().__init__(parent)
        self.pid = None
        self.fd = None
        self.returncode = None
        self._partial = ''
        self._password_mode = False
        self._last_cr = False
        self._cached_password = None
        self._password_retry = None
        self._auth_prompt_seen = False
        self._auth_retry_pending = False
        lay = QVBoxLayout(self)
        intro = QLabel('Review Portage output and respond to prompts below. Administrator authentication is requested only for privileged operations.')
        intro.setWordWrap(True)
        lay.addWidget(intro)
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
        self.close_btn = QPushButton('Back to overview')
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.back_requested.emit)
        bottom.addWidget(self.close_btn)
        lay.addLayout(bottom)
        self.running = False

    def _set_password_mode(self, enabled):
        self._password_mode = enabled
        self.entry.setEchoMode(QLineEdit.EchoMode.Password if enabled else QLineEdit.EchoMode.Normal)
        self.entry.setPlaceholderText('Administrator password (hidden) — press Enter' if enabled else 'Type a response and press Enter (e.g. y or n)')

    def _append(self, data):
        # Strip terminal formatting while retaining readable Portage prompts.
        data = ANSI.sub('', data).replace('\r\n', '\n').replace('\r', '\n')
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(data)
        # sudo writes prompts to the PTY without a newline. Never display or
        # echo credentials; automatically answer using the in-memory session value.
        tail = self.output.toPlainText()[-400:]
        prompt = bool(re.search(r'\[Gentoo Update Manager\] Password:\s*$', tail))
        rejected = 'Sorry, try again.' in tail or 'incorrect password' in tail.lower()
        if rejected and not self._auth_retry_pending:
            self._auth_retry_pending = True
            self._cached_password = None
            self._auth_prompt_seen = False
            if self._password_retry:
                QTimer.singleShot(0, self._password_retry)
        elif prompt and not self._auth_prompt_seen and not self._auth_retry_pending:
            self._auth_prompt_seen = True
            if self._cached_password is not None:
                QTimer.singleShot(0, lambda: self.provide_password(self._cached_password))
            elif self._password_retry:
                self._auth_retry_pending = True
                QTimer.singleShot(0, self._password_retry)
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def start(self, cmd, title, password=None, password_retry=None):
        if self.running:
            return
        self.running = True
        self._cached_password = password
        self._password_retry = password_retry
        self._auth_prompt_seen = False
        self._auth_retry_pending = False
        self.returncode = None
        self.output.clear()
        self._set_password_mode(False)
        self.entry.setEnabled(True)
        self.send.setEnabled(True)
        self.cancel.setEnabled(True)
        self.close_btn.setEnabled(False)
        self.state.setText('Starting ' + title + '…')
        self._start(cmd)

    def provide_password(self, password):
        if self.fd is None:
            return
        self._cached_password = password
        self._auth_retry_pending = False
        self._auth_prompt_seen = True
        try:
            os.write(self.fd, (password + '\n').encode('utf-8'))
        except OSError as exc:
            self._append(f'\nUnable to send authentication: {exc}\n')

    def cancel_authentication(self):
        if self.fd is not None:
            try:
                os.write(self.fd, b'\x03')
            except OSError:
                pass

    def _start(self, cmd):
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
        self.running = False
        self.returncode = code
        self._cached_password = None
        self._password_retry = None
        self._append('\n\n' + ('Operation completed successfully.' if code == 0 else f'Operation failed (exit code {code}).') + '\n')
        self.state.setText('Completed successfully' if code == 0 else f'Operation failed (exit code {code})')
        self._set_password_mode(False)
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
            if self._password_mode:
                self._set_password_mode(False)
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

