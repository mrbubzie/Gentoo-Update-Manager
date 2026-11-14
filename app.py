#!/usr/bin/env python3
"""Gentoo-only Qt frontend for the original Gentoo Update Manager backend."""
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QTimer
from PySide6.QtGui import QPalette, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QStyleFactory, QHeaderView, QSizePolicy,
    QPushButton, QLineEdit, QTabWidget, QTableWidget, QTableWidgetItem, QMessageBox,
    QAbstractItemView, QDialog, QTextEdit, QDialogButtonBox, QInputDialog, QCheckBox)

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
        self.setWindowTitle('Gentoo Update Manager')
        self.resize(1120, 740)
        self.setMinimumSize(700, 490)
        self.setWindowIcon(QIcon(str(HERE / 'assets' / 'gentoo-update-manager.svg')))
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(22, 18, 22, 14); outer.setSpacing(14)
        root.setObjectName('root')
        header = QHBoxLayout(); outer.addLayout(header)
        heading = QVBoxLayout(); header.addLayout(heading, 1)
        title = QLabel('Gentoo Update Manager'); title.setObjectName('pageTitle'); heading.addWidget(title)
        subtitle = QLabel('Portage updates & system maintenance'); subtitle.setObjectName('subtitle'); heading.addWidget(subtitle)
        self.summary = QLabel('Ready to check for updates'); self.summary.setObjectName('summary'); header.addWidget(self.summary)
        self.theme_indicator = QLabel(''); self.theme_indicator.setObjectName('themeIndicator'); header.addWidget(self.theme_indicator)
        toolbar = QHBoxLayout(); outer.addLayout(toolbar)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search packages and rules…'); self.search.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search)
        self.check_btn = QPushButton('Check for updates'); self.check_btn.clicked.connect(self.check_updates); toolbar.addWidget(self.check_btn)
        self.tabs = QTabWidget(); self.tabs.setTabPosition(QTabWidget.TabPosition.North); self.tabs.setDocumentMode(True); self.tabs.setMovable(False); outer.addWidget(self.tabs, 1)
        self.tables = []
        for name, cols in [('Updates', ['Select', 'Change', 'Package', 'New version', 'Installed']),
                           ('Installed software', ['Origin', 'Package', 'Version', 'Slot', 'Repository']),
                           ('Held back', ['Rule', 'Scope'])]:
            page = QWidget(); lay = QVBoxLayout(page)
            table = QTableWidget(0, len(cols)); table.setHorizontalHeaderLabels(cols)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(len(cols)-1, QHeaderView.ResizeMode.Stretch)
            table.setAlternatingRowColors(True)
            table.setShowGrid(False)
            table.setSortingEnabled(False)
            table.setObjectName('packageTable')
            table.verticalHeader().setVisible(False)
            lay.addWidget(table); self.tables.append(table)
            self.tabs.addTab(page, name)
        self.tables[0].itemChanged.connect(self.selection_changed)
        self.tables[0].itemSelectionChanged.connect(self.show_details)
        self.tables[1].itemSelectionChanged.connect(self.show_details)
        self.details = QLabel('Select a package to see details.'); self.details.setWordWrap(True)
        details_frame = QFrame(); details_frame.setObjectName('detailsPanel')
        details_layout = QVBoxLayout(details_frame)
        details_title = QLabel('PACKAGE DETAILS'); details_title.setObjectName('eyebrow'); details_layout.addWidget(details_title)
        details_layout.addWidget(self.details)
        outer.addWidget(details_frame)
        actions = QHBoxLayout(); actions.setSpacing(7); outer.addLayout(actions)
        self.buttons = {}
        for label, callback in [('Select all', self.select_all), ('Select none', self.select_none),
            ('Install selected', self.install), ('Hold / release', self.hold), ('Add rule', self.add_rule),
            ('Release rule', self.release), ('Remove safely', self.remove), ('Force remove', self.force_remove),
            ('Reinstall', self.reinstall)]:
            b = QPushButton(label); b.clicked.connect(callback); actions.addWidget(b); self.buttons[label] = b
            if label == 'Install selected': b.setObjectName('primaryButton')
        maintenance = QLabel('MAINTENANCE'); maintenance.setObjectName('eyebrow'); outer.addWidget(maintenance)
        tools = QHBoxLayout(); tools.setSpacing(7); outer.addLayout(tools)
        for label, callback in [('Sync repositories', self.sync), ('Depclean', self.depclean),
            ('Preserved rebuild', self.preserved), ('Config updates', self.config_updates),
            ('Technical output', self.show_log), ('Help', self.help)]:
            b = QPushButton(label); b.clicked.connect(callback); tools.addWidget(b)
        self.status = QLabel('Ready. No changes will be made without confirmation.'); outer.addWidget(self.status)
        self.tabs.currentChanged.connect(self.refresh)
        self.reload_installed(); self.refresh()
        self._theme_timer = QTimer(self); self._theme_timer.setInterval(1500)
        self._theme_timer.timeout.connect(self.apply_theme); self._theme_timer.start()
        self._last_theme = None; self.apply_theme()

    def apply_theme(self):
        # Qt receives palette changes when Plasma switches its color scheme.
        # Periodic palette checks also cover themes changed by external settings tools.
        pal = QApplication.palette()
        bg = pal.color(QPalette.ColorRole.Window)
        fg = pal.color(QPalette.ColorRole.WindowText)
        base = pal.color(QPalette.ColorRole.Base)
        accent = pal.color(QPalette.ColorRole.Highlight)
        muted = pal.color(QPalette.ColorRole.PlaceholderText)
        dark = bg.lightness() < 128
        key = (bg.name(), fg.name(), base.name(), accent.name(), muted.name())
        if key == self._last_theme: return
        self._last_theme = key
        self.theme_indicator.setText('● Dark mode' if dark else '○ Light mode')
        def rgb(c): return c.name()
        border = '#454b57' if dark else '#d9dfe8'
        surface = '#292d36' if dark else '#ffffff'
        hover = '#343b48' if dark else '#eef3fa'
        muted_text = '#abb5c5' if dark else '#657286'
        self.setStyleSheet(f'''
          QWidget#root {{ background: {rgb(bg)}; }}
          QLabel#pageTitle {{ font-size: 25px; font-weight: 700; }}
          QLabel#subtitle, QLabel#themeIndicator {{ color: {muted_text}; font-size: 12px; }}
          QLabel#summary {{ color: {rgb(accent)}; font-weight: 600; padding: 8px 12px; }}
          QLabel#eyebrow {{ color: {muted_text}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
          QFrame#detailsPanel {{ background: {surface}; border: 1px solid {border}; border-radius: 11px; }}
          QFrame#detailsPanel QLabel {{ border: none; background: transparent; }}
          QTabWidget::pane {{ border: 1px solid {border}; border-radius: 12px; background: {surface}; top: -1px; }}
          QTabBar {{ qproperty-drawBase: 0; }}
          QTabBar::tab {{ padding: 11px 22px; min-width: 125px; border: 1px solid transparent; border-radius: 9px; margin: 0 6px 8px 0; }}
          QTabBar::tab:selected {{ background: {hover}; color: {rgb(accent)}; border: 1px solid {border}; font-weight: 700; }}
          QTabBar::tab:hover:!selected {{ background: {hover}; }}
          QTableWidget#packageTable {{ background: {surface}; alternate-background-color: {hover}; border: none; selection-background-color: {rgb(accent)}; selection-color: {rgb(pal.color(QPalette.ColorRole.HighlightedText))}; }}
          QHeaderView::section {{ background: {surface}; padding: 11px 8px; border: none; border-bottom: 1px solid {border}; font-weight: 600; }}
          QLineEdit {{ padding: 9px 12px; border: 1px solid {border}; border-radius: 8px; background: {surface}; }}
          QLineEdit:focus {{ border: 1px solid {rgb(accent)}; }}
          QPushButton {{ border: 1px solid {border}; background: {surface}; padding: 9px 12px; border-radius: 8px; }}
          QPushButton:hover {{ background: {hover}; }}
          QPushButton:disabled {{ color: {muted_text}; }}
          QPushButton#primaryButton {{ background: {rgb(accent)}; color: {rgb(pal.color(QPalette.ColorRole.HighlightedText))}; border-color: {rgb(accent)}; font-weight: 700; }}
        ''')

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
        t = self.tabs.currentIndex()
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
    def run_portage(self, cmd, title):
        if not self.confirm(title, 'Run this Portage operation in a terminal?\n\n' + shlex.join(cmd) + '\n\nPortage will ask for approval before changes are made.'):
            return
        terminals = [('konsole', ['-e']), ('xterm', ['-e']), ('xfce4-terminal', ['--hold', '-x']), ('mate-terminal', ['--',]), ('gnome-terminal', ['--'])]
        found = next(((name, args) for name, args in terminals if shutil.which(name)), None)
        if not found:
            self.notify('Terminal required', 'Install Konsole, xterm, or another supported terminal emulator.'); return
        # Run a shell only for terminal presentation; every command argument is shell-quoted.
        prefix = '' if os.geteuid() == 0 else ('sudo ' if shutil.which('sudo') else 'doas ' if shutil.which('doas') else '')
        if os.geteuid() != 0 and not prefix:
            self.notify('Authentication required', 'Install and configure sudo or doas.'); return
        script = prefix + shlex.join(cmd) + '; rc=$?; printf "\\nExit code: %s\\nPress Enter to close…" "$rc"; read answer'
        name, args = found
        try: subprocess.Popen([name] + args + ['sh', '-c', script])
        except OSError as e: self.notify('Launch failed', str(e))
        self.status.setText('Transaction launched in a terminal. Refresh after it finishes.')
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
