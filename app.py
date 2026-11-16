#!/usr/bin/env python3
"""Gentoo-only Qt frontend for the original Gentoo Update Manager backend."""
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QTimer, QSize
from PySide6.QtGui import QPalette, QIcon, QFontMetrics
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QStyleFactory, QHeaderView, QSizePolicy, QStyle,
    QPushButton, QLineEdit, QTabWidget, QTableWidget, QTableWidgetItem, QMessageBox,
    QAbstractItemView, QDialog, QTextEdit, QDialogButtonBox, QInputDialog, QCheckBox, QStackedWidget, QScrollArea, QDialogButtonBox)

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gentoo_backend', HERE / 'gentoo-update-manager.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

class CheckThread(QThread):
    finished_check = Signal(int, str, str)
    def __init__(self, cmd):
        super().__init__(); self.cmd = cmd
    def run(self):
        env = dict(os.environ, EMERGE_DEFAULT_OPTS='', LC_ALL='C')
        try:
            p = subprocess.run(self.cmd, text=True, capture_output=True, env=env)
            self.finished_check.emit(p.returncode, p.stdout, p.stderr)
        except OSError as exc:
            self.finished_check.emit(127, '', str(exc))

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = backend.load_config()
        self.updates = []; self.installed = []; self.selected_updates = set()
        self.checked = False; self.raw = ''; self.worker = None
        self._session_password = None
        self.setWindowTitle('Gentoo Update Manager')
        self.resize(1280, 790)
        self.setMinimumSize(1120, 710)
        self.setWindowIcon(QIcon(str(HERE / 'assets' / 'gentoo-update-manager-256.png')))
        root = QWidget(); self.setCentralWidget(root)
        root.setObjectName('root')
        shell = QHBoxLayout(root); shell.setContentsMargins(0, 0, 0, 0); shell.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(335)
        shell.addWidget(sidebar)
        side = QVBoxLayout(sidebar); side.setContentsMargins(20, 24, 20, 22); side.setSpacing(10)
        brand = QVBoxLayout(); brand.setSpacing(10)
        logo = QLabel(); logo.setPixmap(QIcon(str(HERE / 'assets' / 'gentoo-update-manager-256.png')).pixmap(58, 58))
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_title = QLabel('Gentoo Update Manager'); brand_title.setObjectName('brandTitle'); brand_title.setWordWrap(False); brand_title.setMinimumWidth(290); brand_title.setStyleSheet('font-size: 17px; font-weight: 750;')
        brand_text.addWidget(brand_title)
        brand_caption = QLabel('Portage • Gentoo Linux'); brand_caption.setObjectName('brandCaption')
        brand_text.addWidget(brand_caption)
        brand.addLayout(brand_text); side.addLayout(brand)
        side.addSpacing(32)
        nav_title = QLabel('PACKAGE MANAGEMENT'); nav_title.setObjectName('navTitle'); side.addWidget(nav_title)
        self.nav_buttons = []
        for i, (label, icon_name) in enumerate([
            ('Overview', 'overview'), ('Updates', 'updates'),
            ('Installed software', 'installed'), ('Held back', 'held')]):
            btn = QPushButton(label)
            btn.setIcon(QIcon(str(HERE / 'assets' / 'navigation' / f'{icon_name}.svg')))
            btn.setIconSize(QSize(23, 23))
            btn.setObjectName('navButton')
            btn.setCheckable(True)
            btn.setMinimumHeight(49)
            btn.clicked.connect(lambda checked=False, index=i: self.navigate(index))
            side.addWidget(btn)
            self.nav_buttons.append(btn)
        side.addSpacing(20)
        maintenance_title = QLabel('SYSTEM MAINTENANCE'); maintenance_title.setObjectName('navTitle')
        side.addWidget(maintenance_title)
        for label, icon_name, callback in [
            ('Sync repositories', 'sync', self.sync),
            ('Depclean', 'depclean', self.depclean),
            ('Preserved rebuild', 'rebuild', self.preserved),
            ('Config updates', 'config', self.config_updates)]:
            b = QPushButton(label)
            b.setIcon(QIcon(str(HERE / 'assets' / 'navigation' / f'{icon_name}.svg')))
            b.setIconSize(QSize(23, 23))
            b.setObjectName('sideAction')
            b.clicked.connect(callback)
            b.setMinimumHeight(44)
            side.addWidget(b)
        side.addStretch(1)
        about = QLabel('Gentoo Update Manager  •  v1.2.7')
        about.setObjectName('sideFooter'); about.setWordWrap(False); side.addWidget(about)
        main = QWidget(); main.setObjectName('mainArea'); shell.addWidget(main, 1)
        outer = QVBoxLayout(main); outer.setContentsMargins(28, 24, 28, 20); outer.setSpacing(16)
        header = QHBoxLayout(); outer.addLayout(header)
        heading = QVBoxLayout(); header.addLayout(heading, 1)
        title = QLabel('Overview'); title.setObjectName('pageTitle'); heading.addWidget(title)
        self.page_title = title
        subtitle = QLabel('Manage updates, packages and system maintenance.'); subtitle.setObjectName('subtitle'); heading.addWidget(subtitle)
        self.page_subtitle = subtitle
        self.theme_indicator = QLabel(''); self.theme_indicator.setObjectName('themeIndicator'); header.addWidget(self.theme_indicator)
        summary_frame = QFrame(); summary_frame.setObjectName('summaryCard')
        summary_lay = QHBoxLayout(summary_frame); summary_lay.setContentsMargins(20, 16, 20, 16)
        summary_text = QVBoxLayout()
        summary_label = QLabel('PORTAGE STATUS'); summary_label.setObjectName('eyebrow'); summary_text.addWidget(summary_label)
        self.summary = QLabel('Ready to check for updates'); self.summary.setObjectName('summary'); summary_text.addWidget(self.summary)
        summary_lay.addLayout(summary_text, 1)
        self.check_btn = QPushButton('↻  Check for updates'); self.check_btn.setObjectName('primaryButton')
        self.check_btn.clicked.connect(self.check_updates); summary_lay.addWidget(self.check_btn)
        outer.addWidget(summary_frame)
        toolbar = QHBoxLayout(); outer.addLayout(toolbar)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search packages and hold rules…')
        self.search.textChanged.connect(self.refresh); toolbar.addWidget(self.search)
        self.stacked = QStackedWidget(); outer.addWidget(self.stacked, 1)
        self.tabs = QTabWidget(); self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setDocumentMode(True); self.tabs.setMovable(False)
        self.tables = []
        for name, cols in [('Updates', ['Select', 'Change', 'Package', 'New version', 'Installed']),
                           ('Installed software', ['Origin', 'Package', 'Version', 'Slot', 'Repository']),
                           ('Held back', ['Rule', 'Scope'])]:
            page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 10, 0, 0)
            table = QTableWidget(0, len(cols)); table.setHorizontalHeaderLabels(cols)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(len(cols)-1, QHeaderView.ResizeMode.Stretch)
            table.setAlternatingRowColors(True); table.setShowGrid(False); table.setSortingEnabled(False)
            table.setObjectName('packageTable'); table.verticalHeader().setVisible(False)
            lay.addWidget(table); self.tables.append(table); self.tabs.addTab(page, name)
        self.overview = QWidget(); self.overview.setObjectName('overview')
        overview_layout = QVBoxLayout(self.overview); overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(14)
        overview_row = QHBoxLayout(); overview_row.setSpacing(14)
        self.update_card, self.update_count = self.make_stat_card('AVAILABLE UPDATES', '0', 'Portage package changes')
        self.installed_card, self.installed_count = self.make_stat_card('INSTALLED PACKAGES', '0', 'Packages on this system')
        self.held_card, self.held_count = self.make_stat_card('HELD BACK', '0', 'Application hold rules')
        for card in (self.update_card, self.installed_card, self.held_card):
            overview_row.addWidget(card, 1)
        overview_layout.addLayout(overview_row)
        info = QFrame(); info.setObjectName('infoCard')
        info_lay = QVBoxLayout(info); info_lay.setContentsMargins(24, 22, 24, 22)
        info_heading = QLabel('System maintenance'); info_heading.setObjectName('cardTitle')
        info_lay.addWidget(info_heading)
        info_text = QLabel('Review available updates, manage installed software, and keep your Gentoo system maintained with Portage. All package operations remain interactive.')
        info_text.setWordWrap(True); info_text.setObjectName('cardDescription'); info_lay.addWidget(info_text)
        quick = QHBoxLayout(); quick.setSpacing(10)
        for label, callback in [('View updates', lambda: self.navigate(1)),
                                ('Installed software', lambda: self.navigate(2)),
                                ('Sync repositories', self.sync)]:
            btn = QPushButton(label); btn.clicked.connect(callback); quick.addWidget(btn)
        quick.addStretch(); info_lay.addLayout(quick)
        overview_layout.addWidget(info); overview_layout.addStretch()
        self.stacked.addWidget(self.overview)
        self.tabs.tabBar().hide()
        self.stacked.addWidget(self.tabs)
        from transaction import TransactionPanel
        self.transaction_panel = TransactionPanel(self)
        self.transaction_panel.completed.connect(self.transaction_finished)
        self.transaction_panel.back_requested.connect(lambda: self.navigate(0))
        self.stacked.addWidget(self.transaction_panel)
        self.tabs.currentChanged.connect(self.refresh)
        self.details = QLabel('Select a package to see details.'); self.details.setWordWrap(True)
        details_frame = QFrame(); details_frame.setObjectName('detailsPanel')
        details_layout = QVBoxLayout(details_frame)
        details_title = QLabel('PACKAGE DETAILS'); details_title.setObjectName('eyebrow'); details_layout.addWidget(details_title)
        details_layout.addWidget(self.details)
        outer.addWidget(details_frame)
        self.details_frame = details_frame
        actions = QHBoxLayout(); actions.setSpacing(7); outer.addLayout(actions)
        self.buttons = {}
        for label, callback in [('Select all', self.select_all), ('Select none', self.select_none),
            ('Install selected', self.install), ('Hold / release', self.hold), ('Add rule', self.add_rule),
            ('Release rule', self.release), ('Remove safely', self.remove), ('Force remove', self.force_remove),
            ('Reinstall', self.reinstall)]:
            b = QPushButton(label); b.clicked.connect(callback); actions.addWidget(b); self.buttons[label] = b
            if label == 'Install selected': b.setObjectName('primaryButton')
        self.actions_layout = actions
        bottom = QHBoxLayout(); outer.addLayout(bottom)
        self.status = QLabel('●  Ready. No changes will be made without confirmation.')
        self.status.setObjectName('status'); bottom.addWidget(self.status, 1)
        for label, callback in [('Technical output', self.show_log), ('Help', self.help)]:
            b = QPushButton(label); b.setObjectName('footerButton'); b.clicked.connect(callback); bottom.addWidget(b)
        self.navigate(0)
        self.tables[0].itemChanged.connect(self.selection_changed)
        self.tables[0].itemSelectionChanged.connect(self.show_details)
        self.tables[1].itemSelectionChanged.connect(self.show_details)
        self.reload_installed(); self.refresh()
        self.apply_theme()

    def make_stat_card(self, heading, value, description):
        card = QFrame(); card.setObjectName('statCard')
        layout = QVBoxLayout(card); layout.setContentsMargins(20, 18, 20, 18)
        heading_label = QLabel(heading); heading_label.setObjectName('eyebrow')
        number = QLabel(value); number.setObjectName('statNumber')
        caption = QLabel(description); caption.setObjectName('cardDescription')
        layout.addWidget(heading_label); layout.addWidget(number); layout.addWidget(caption)
        return card, number

    def navigate(self, index):
        if getattr(self, 'transaction_panel', None) and self.transaction_panel.running:
            self.notify('Transaction running', 'Finish or cancel the Portage operation before leaving this screen.')
            return
        self.active_page = index
        self.stacked.setCurrentIndex(0 if index == 0 else 1)
        if index > 0:
            self.tabs.setCurrentIndex(index - 1)
        names = ['Overview', 'Available updates', 'Installed software', 'Held back']
        descriptions = ['A quick look at your Gentoo system.',
                        'Review and install available Portage updates.',
                        'Browse, reinstall, or remove installed packages.',
                        'Manage packages excluded from updates.']
        self.page_title.setText(names[index])
        self.page_subtitle.setText(descriptions[index])
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        self.search.setVisible(index != 0)
        self.details_frame.setVisible(index != 0)
        self.refresh()

    def apply_theme(self):
        """Visual language aligned with Asahi Control Center 1.4.3.

        Uses its charcoal-purple surfaces, lavender selection and subtle borders,
        while preserving Gentoo Update Manager's own blue application icon.
        """
        self.theme_indicator.setText('●  Portage ready')
        self.setStyleSheet("""
            QMainWindow, QWidget#root, QWidget#mainArea, QWidget#overview {
                background: #191b26; color: #f3f2fa;
            }
            QWidget { font-family: 'Noto Sans', 'Inter', sans-serif; font-size: 13px; color: #f3f2fa; }
            QFrame#sidebar { background: #211e30; border-right: 1px solid #373444; }
            QLabel#brandTitle { color: #ffffff; font-size: 19px; font-weight: 750; }
            QLabel#brandCaption, QLabel#sideFooter { color: #adaec0; font-size: 11px; }
            QLabel#navTitle, QLabel#eyebrow { color: #c5b7df; font-size: 11px; font-weight: 700; }
            QPushButton#navButton, QPushButton#sideAction {
                text-align: left; border: 1px solid transparent; border-radius: 10px;
                background: transparent; color: #ded9ed; padding: 10px 16px; font-size: 13px;
            }
            QPushButton#navButton:hover:!checked, QPushButton#sideAction:hover { background: #3b334c; }
            QPushButton#navButton:checked {
                background: #7153c3; color: white; font-weight: 700; border: 1px solid #8f71dc;
            }
            QLabel#pageTitle { font-size: 28px; font-weight: 750; color: #f9f7ff; }
            QLabel#subtitle, QLabel#themeIndicator { color: #c0bfd0; font-size: 12px; }
            QFrame#summaryCard, QFrame#statCard, QFrame#infoCard, QFrame#detailsPanel {
                background: #262936; border: 1px solid #3b4053; border-radius: 18px;
            }
            QFrame#summaryCard QLabel, QFrame#statCard QLabel, QFrame#infoCard QLabel,
            QFrame#detailsPanel QLabel { background: transparent; border: none; }
            QLabel#summary { font-size: 21px; font-weight: 700; color: #ffffff; }
            QLabel#statNumber { font-size: 43px; font-weight: 800; color: #ffffff; }
            QLabel#cardTitle { font-size: 17px; font-weight: 700; color: #ffffff; }
            QLabel#cardDescription { color: #c0bfd0; font-size: 12px; }
            QLabel#status { color: #c0bfd0; font-size: 11px; }
            QTabWidget::pane { border: 0; background: transparent; }
            QTableWidget#packageTable {
                background: #262936; alternate-background-color: #2c2e3e;
                border: 1px solid #3b4053; border-radius: 12px;
                color: #f3f2fa; gridline-color: #3b4053;
                selection-background-color: #7153c3; selection-color: white;
            }
            QTableWidget::item { padding: 5px; }
            QHeaderView::section {
                background: #303244; color: #eeeaf6; padding: 11px 8px;
                border: none; border-bottom: 1px solid #48495f; font-weight: 650;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                background: #303244; color: #f3f2fa; border: 1px solid #525466;
                border-radius: 10px; padding: 10px 12px;
            }
            QLineEdit:focus { border: 1px solid #a98af5; }
            QPushButton {
                background: #383448; color: #e8e2f5; border: 1px solid #5e5277;
                border-radius: 10px; padding: 9px 12px;
            }
            QPushButton:hover { background: #51436d; border-color: #a887ed; }
            QPushButton:disabled { color: #aaa8ba; background: #414351; }
            QPushButton#primaryButton {
                background: #7354c9; color: #ffffff; border: none; font-weight: 700;
                border-radius: 12px; padding: 11px 16px;
            }
            QPushButton#primaryButton:hover { background: #8c6be0; }
            QPushButton#footerButton { background: transparent; border-color: #45405e; }
            QScrollBar:vertical { background: #1f212e; width: 10px; margin: 4px 2px; border: 0; }
            QScrollBar::handle:vertical { background: #55506b; border-radius: 5px; min-height: 32px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: 0; }
            QToolTip { background: #303144; color: #f5f2ff; border: 1px solid #655981; }
        """)

    def notify(self, title, message): QMessageBox.information(self, title, message)
    def confirm(self, title, message):
        return QMessageBox.question(self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
    def reload_installed(self): self.installed = backend.scan_installed()
    def held(self, p): return p.cpn in self.cfg['ignored'] or '=' + p.cpv in self.cfg['ignored']
    def current(self, tab):
        r = self.tables[tab].currentRow()
        items = [self.updates, self.installed, self.cfg['ignored']][tab]
        if r < 0: return None
        cell = self.tables[tab].item(r, 0)
        idx = cell.data(Qt.ItemDataRole.UserRole) if cell else None
        return items[idx] if isinstance(idx, int) and idx < len(items) else None
    def refresh(self, *_):
        query = self.search.text().lower()
        for tab, records in enumerate([self.updates, self.installed, self.cfg['ignored']]):
            table = self.tables[tab]; table.blockSignals(True); table.setRowCount(0)
            for idx, obj in enumerate(records):
                key = obj if isinstance(obj, str) else obj.cpv
                if query not in key.lower(): continue
                row = table.rowCount(); table.insertRow(row)
                if tab == 0:
                    values = ['', obj.kind, obj.cpn, obj.ver, obj.old]
                elif tab == 1:
                    values = ['Yours' if obj.in_world else 'Auto', obj.cpn, obj.ver, obj.slot, obj.repo]
                else: values = [obj, 'Version only' if obj.startswith('=') else 'All versions']
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value)); item.setData(Qt.ItemDataRole.UserRole, idx)
                    if tab == 0 and col == 0:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Checked if obj.key in self.selected_updates else Qt.CheckState.Unchecked)
                        if self.held(obj): item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    table.setItem(row, col, item)
            table.blockSignals(False)
        self.tabs.setTabText(0, f'Updates  ({len(self.updates)})')
        self.tabs.setTabText(1, f'Installed software  ({len(self.installed)})')
        self.tabs.setTabText(2, f'Held back  ({len(self.cfg["ignored"])})')
        self.summary.setText(f'{len(self.updates)} changes available' if self.checked else 'Ready to check for updates')
        self.update_count.setText(str(len(self.updates)))
        self.installed_count.setText(str(len(self.installed)))
        self.held_count.setText(str(len(self.cfg['ignored'])))
        t = self.active_page - 1
        if self.active_page == 4: t = -1
        for label in ['Select all', 'Select none', 'Install selected', 'Hold / release']:
            self.buttons[label].setVisible(t == 0)
        for label in ['Remove safely', 'Force remove', 'Reinstall']:
            self.buttons[label].setVisible(t == 1)
        for label in ['Add rule', 'Release rule']:
            self.buttons[label].setVisible(t == 2)
    def selection_changed(self, item):
        if item.column() != 0: return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int) or idx >= len(self.updates): return
        p = self.updates[idx]
        if self.held(p): return
        if item.checkState() == Qt.CheckState.Checked: self.selected_updates.add(p.key)
        else: self.selected_updates.discard(p.key)
    def show_details(self):
        tab = self.tabs.currentIndex(); p = self.current(tab)
        if not p: return
        if isinstance(p, str): self.details.setText(f'Hold rule: {p}'); return
        path = backend.DB_DIR / p.cpn / (p.cpn.split('/')[-1] + '-' + p.ver)
        def read(n):
            try: return (path / n).read_text().strip().replace('\n', ' ')[:250]
            except OSError: return ''
        self.details.setText(f'{p.cpn} {p.ver}  •  {read("DESCRIPTION")}  {read("HOMEPAGE")}')
    def check_updates(self):
        if self.worker and self.worker.isRunning(): return
        cmd = ['emerge', '--pretend', '--verbose', '--color=n', '--nospinner'] + self.cfg['update_args']
        self.check_btn.setEnabled(False); self.status.setText('Checking Portage dependencies…')
        self.worker = CheckThread(cmd); self.worker.finished_check.connect(self.checked_done); self.worker.start()
    def checked_done(self, rc, out, err):
        self.check_btn.setEnabled(True); self.raw = '$ emerge --pretend …\n' + out + '\n' + err
        self.updates = backend.parse_pretend(out); self.selected_updates.clear()
        self.checked = rc == 0
        self.status.setText(f'{len(self.updates)} proposed changes.' if rc == 0 else 'Portage reported an error; see Technical output.')
        self.refresh()
        if rc: self.notify('Portage reported an error', 'The update check did not complete successfully. Review Technical output before installing.')
    def select_all(self):
        self.selected_updates = {p.key for p in self.updates if not self.held(p)}; self.refresh()
    def select_none(self): self.selected_updates.clear(); self.refresh()
    def ensure_auth(self):
        """Request a password only when a privileged operation is selected.

        The password is kept in process memory only until this window closes;
        it is never saved to disk or inserted into command arguments.
        """
        if os.geteuid() == 0:
            return []
        if not shutil.which('sudo'):
            self.notify('Authentication unavailable', 'Install and configure sudo to use privileged Portage operations.')
            return None
        if self._session_password is None:
            password, ok = QInputDialog.getText(
                self, 'Administrator authentication',
                'Enter your sudo password to authorize privileged operations for this application session.\n'
                'It will be held in memory until you close the application.',
                QLineEdit.EchoMode.Password)
            if not ok:
                return None
            if not password:
                self.notify('Authentication required', 'Enter a password to continue.')
                return None
            self._session_password = password
        return ['sudo', '-p', '[Gentoo Update Manager] Password: ']

    def _password_retry(self):
        """Re-prompt after sudo rejects the cached password."""
        self._session_password = None
        password, ok = QInputDialog.getText(
            self, 'Authentication failed',
            'The administrator password was rejected. Enter it again:',
            QLineEdit.EchoMode.Password)
        if ok and password:
            self._session_password = password
            self.transaction_panel.provide_password(password)
        else:
            self.transaction_panel.cancel_authentication()

    def run_portage(self, cmd, title):
        if self.transaction_panel.running:
            self.notify('Transaction in progress', 'Finish the current Portage operation first.')
            return
        if not self.confirm(title, 'Run this Portage operation?\n\n' + shlex.join(cmd) +
                            '\n\nYou can review Portage output and respond to prompts inside the application.'):
            return
        prefix = self.ensure_auth()
        if prefix is None:
            return
        self.active_page = 4
        self.stacked.setCurrentIndex(2)
        self.page_title.setText(title)
        self.page_subtitle.setText('Live Portage output and interactive prompts')
        self.summary.setText('Transaction in progress')
        self.search.hide()
        self.details_frame.hide()
        for button in self.nav_buttons: button.setChecked(False)
        self.refresh()
        self.transaction_panel.start(prefix + cmd, title,
                                     password=self._session_password if prefix else None,
                                     password_retry=self._password_retry)

    def transaction_finished(self, code):
        if code == 0:
            self.reload_installed()
            self.checked = False
            self.updates.clear()
            self.selected_updates.clear()
            self.refresh()
            self.status.setText('Operation completed. Check for updates to refresh the package list.')
        else:
            self.status.setText(f'Operation exited with code {code}. Review the output above.')
        self.summary.setText('Operation completed' if code == 0 else 'Operation needs attention')

    def closeEvent(self, event):
        if self.transaction_panel.running:
            self.notify('Operation running', 'Finish or cancel the Portage operation before closing.')
            event.ignore(); return
        self._session_password = None
        super().closeEvent(event)

    def install(self):
        if not self.checked:
            self.notify('Check first', 'Run a successful update check before installing.'); return
        chosen = [p.atom for p in self.updates if p.key in self.selected_updates and not self.held(p)]
        if not chosen: self.notify('Nothing selected', 'Select one or more available updates.'); return
        self.run_portage(['emerge'] + self.cfg['emerge_opts'] + ['--oneshot'] + chosen, 'Install selected updates')
    def hold(self):
        p = self.current(0)
        if not p: return
        if self.held(p):
            self.cfg['ignored'] = [r for r in self.cfg['ignored'] if r not in (p.cpn, '=' + p.cpv)]
        else:
            choices = ['All versions', 'Only ' + p.ver]
            choice, ok = QInputDialog.getItem(self, 'Hold package', 'Hold back:', choices, 0, False)
            if not ok: return
            self.cfg['ignored'].append(p.cpn if choice == choices[0] else '=' + p.cpv)
        backend.save_config(self.cfg); self.refresh()
    def add_rule(self):
        value, ok = QInputDialog.getText(self, 'Add hold rule', 'Gentoo package atom (e.g. sys-devel/gcc or =sys-devel/gcc-14.2.1):')
        if ok and value.strip() and value.strip() not in self.cfg['ignored']:
            self.cfg['ignored'].append(value.strip()); backend.save_config(self.cfg); self.refresh()
    def release(self):
        rule = self.current(2)
        if rule: self.cfg['ignored'].remove(rule); backend.save_config(self.cfg); self.refresh()
    def remove(self):
        p = self.current(1)
        if p: self.run_portage(['emerge', '--ask', '--verbose', '--depclean', p.cpn + (':' + p.slot if p.slot else '')], 'Remove safely')
    def force_remove(self):
        p = self.current(1)
        if p and self.confirm('Danger: force removal', 'This bypasses dependency checks and can break installed software. Continue?'):
            self.run_portage(['emerge', '--ask', '--verbose', '--unmerge', p.cpn + (':' + p.slot if p.slot else '')], 'Force remove')
    def reinstall(self):
        p = self.current(1)
        if p: self.run_portage(['emerge'] + self.cfg['emerge_opts'] + ['--oneshot', p.atom], 'Reinstall package')
    def sync(self): self.run_portage(['emaint', 'sync', '-a'] if shutil.which('emaint') else ['emerge', '--sync'], 'Sync repositories')
    def depclean(self): self.run_portage(['emerge', '--ask', '--verbose', '--depclean'], 'Remove unused packages')
    def preserved(self): self.run_portage(['emerge', '--ask', '--verbose', '@preserved-rebuild'], 'Preserved rebuild')
    def config_updates(self):
        tool = 'dispatch-conf' if shutil.which('dispatch-conf') else 'etc-update'
        self.run_portage([tool], 'Review configuration updates')
    def text_dialog(self, title, text):
        dlg = QDialog(self); dlg.setWindowTitle(title); dlg.resize(850, 520)
        layout = QVBoxLayout(dlg); editor = QTextEdit(); editor.setReadOnly(True); editor.setPlainText(text)
        layout.addWidget(editor); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject); layout.addWidget(buttons); dlg.exec()
    def show_log(self): self.text_dialog('Technical output', self.raw or 'No check has been run yet.')
    def help(self): self.text_dialog('Original Gentoo Update Manager help', backend.HELP)

def main():
    if not shutil.which('emerge'):
        sys.exit('Gentoo Update Manager requires Portage (emerge).')
    app = QApplication(sys.argv); app.setApplicationName('Gentoo Update Manager')
    window = Window(); window.show(); sys.exit(app.exec())
if __name__ == '__main__': main()
