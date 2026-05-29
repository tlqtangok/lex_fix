# Wubi .lex Dictionary Editor

> 📖 [中文版](README.md)

A viewer / search / editor for Microsoft Wubi IME `.lex` dictionary files.  
Supports both GUI and command-line usage.  
Special support for auto-refreshing **`now` (current time)** and **`date` (current date)** shortcut entries.

---

## Features

- Supports two `.lex` formats: `mschxudp` (user dictionary `user.lex`) and `imscwubi` (main dictionary `ChsWubiNew.lex`)
- GUI: browse, search, add, edit, delete entries
- CLI: batch edit, delete, add entries
- Recent files menu with auto-restore of last opened file on startup
- Perl script for automatic time/date entry refresh

---

## Quick Start

### Option A: Run the prebuilt exe (recommended, no Python required)

Download `lex_editor.exe` from the [release/](release/) folder and double-click to run.

### Option B: Run the Python script

```bash
# Requires Python 3.8+, no third-party dependencies
python lex_editor.py
```

---

## GUI Usage

1. **Open a dictionary**: `File → Open…`, choose a `.lex` file; or use `File → Open Recent`
2. **Search entries**: type in the toolbar search box; filter by `All / Word / Code` mode
3. **Add entry**: `Edit → Add Entry` (or `Ctrl+N`), fill in code and word, then save
4. **Edit entry**: double-click a row, or `Edit → Edit Entry` (or `F2`)
5. **Delete entry**: select a row and press `Del`, or `Edit → Delete Entry`
6. **Save**: `Ctrl+S` to save in place; `File → Save As…` to save a copy
7. A `*` in the title bar means there are unsaved changes

---

## CLI Usage

```
python lex_editor.py --input <file> [--output <file>] --op <operation> [options]
```

### Help

```bash
python lex_editor.py --help
```

### Search

```bash
# Search by code
python lex_editor.py --input user.lex --op search --query now --by code

# Search by word
python lex_editor.py --input user.lex --op search --query 今天 --by word
```

### Edit (multiple keys at once)

```bash
# Edit a single entry
python lex_editor.py --input user.lex --output user.lex --op edit --key now --value "2024-01-01 12:00:00"

# Edit multiple entries in one command (repeat --key / --value)
python lex_editor.py --input user.lex --output user.lex ^
  --op edit ^
  --key now   --value "2024-01-01 12:00:00" ^
  --key date  --value "2024-01-01"
```

### Delete

```bash
# Delete a single entry by code
python lex_editor.py --input user.lex --output user.lex --op del --key now

# Delete multiple entries
python lex_editor.py --input user.lex --output user.lex --op del --key now --key date
```

### Add

```bash
python lex_editor.py --input user.lex --output user.lex --op add --key aaaa --value 工
```

---

## Setting Up `now` / `date` Time Shortcuts

The Microsoft Wubi IME supports custom shortcut entries, but **does not update time automatically**.  
This project includes the Perl script `loop_now_data_lex.PL` which runs in the background and  
refreshes the `now` and `date` entries every 30 seconds so they always show the current time/date.

### How it works

| Code | Example value | Description |
|------|---------------|-------------|
| `now` | `2024-05-29 19:10:00` | Current date and time |
| `date` | `2024-05-29` | Current date |

### Setup steps

**1. Confirm the dictionary path** (default in the script):
```
C:\Users\<YourName>\AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex
```
To change it, edit line 26 (`$lex_file`) in `loop_now_data_lex.PL`.

**2. Add placeholder entries via the GUI first**:  
Open the dictionary → `Edit → Add Entry` → Code: `now`, Word: any placeholder → Save.  
Repeat for `date`.

**3. Start the background refresh script** (requires [Perl / Strawberry Perl](https://strawberryperl.com/)):
```bash
perl loop_now_data_lex.PL
```
The script prints `OK` each time it refreshes. It updates every ~30 seconds.

**4. Auto-start on login (optional)**:  
Save the following as `start_lex_loop.bat` and place it in your Windows Startup folder  
(press `Win+R`, type `shell:startup`):
```bat
@echo off
start /min perl "D:\path\to\loop_now_data_lex.PL"
```

### Using the shortcuts in Wubi IME

Type `now` → commit → the current date and time appears.  
Type `date` → commit → the current date appears.

---

## Building the Installer

```bash
# Double-click or run from cmd — automatically packages into a single exe
deploy.bat
```

Output: `release\lex_editor.exe` (also zipped as `release\WubiLexEditor.zip`).

---

## Project Structure

```
lex_reader/
├── lex_editor.py          # Main program (GUI + CLI)
├── loop_now_data_lex.PL   # Perl background refresh script
├── deploy.bat             # Build/package script
├── user.lex               # Sample user dictionary
└── release/
    ├── lex_editor.exe     # Standalone exe (no Python needed)
    └── WubiLexEditor.zip  # Zipped version
```

---

## Author

- **Author**: tlqtangok  
- **Email**: tlqtangok@126.com  
- **Source**: https://github.com/tlqtangok/lex_fix
