# Gentoo Update Manager

Run in an interactive terminal on Gentoo:

```sh
python3 gentoo-update-manager.py
```

Navigation: Up/Down selects rows; Page Up/Page Down scrolls; Home/End jumps;
Left/Right or 1/2/3 switches top tabs.
Tab focuses the first bottom button; further Tab presses move through buttons
and return to the list. Shift-Tab reverses this order. A focused button is
highlighted: Left/Right selects a button, Enter/Space activates it, and
Escape or Up/Down returns to the list. Use Space to select a package,
/ to search, Enter to finish searching, F1 for help and q to quit.
Dialogs use Left/Right or Tab/Shift-Tab to select buttons, Enter to confirm,
and Escape to cancel.

Keyboard fix: explicitly enable keypad decoding, accept both common terminal
navigation sequence formats, allow more time for escape sequences, and restore
keypad mode after external commands. No additional Python dependencies.
