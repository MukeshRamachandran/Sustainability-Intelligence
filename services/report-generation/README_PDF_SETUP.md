# PDF Export Module Setup Guide

This guide explains how to set up the environment required to run the PDF export module from scratch on a Windows machine. The core dependency for generating PDFs is **WeasyPrint**, which requires GTK3 and related libraries to be installed at the system level.

## 1. Prerequisites
- **Python 3.8+** installed on your system.
- **MSYS2** installed (for providing GTK3 binaries on Windows). You can download it from [msys2.org](https://www.msys2.org/).

## 2. Installing GTK3 Dependencies (via MSYS2)
WeasyPrint relies on Pango, Cairo, and GTK3 to render HTML to PDF. On Windows, the most reliable way to install these is using MSYS2.

1. Open the **MSYS2 MinGW 64-bit** terminal (search for "MSYS2 MinGW x64" in your start menu).
2. Run the following commands to update the package database and core system packages:
   ```bash
   pacman -Syu
   ```
   *(If it asks to close the terminal, do so, reopen it, and run `pacman -Su` to finish the update).*

3. Install GTK3 and its dependencies by running:
   ```bash
   pacman -S mingw-w64-x86_64-gtk3 mingw-w64-x86_64-pango mingw-w64-x86_64-libffi
   ```

4. **Critical Step: Update System PATH**
   You must add the MSYS2 MinGW `bin` folder to your Windows System Environment Variables `PATH` so Python can find the GTK DLLs.
   - Open Start Menu and search for "Environment Variables" -> "Edit the system environment variables".
   - Click "Environment Variables..."
   - Under "System variables" (or "User variables"), find `Path`, and click "Edit".
   - Click "New" and add the path to the MSYS2 mingw64 bin directory. Usually, this is:
     `C:\msys64\mingw64\bin`
   - Click OK and close all dialogs.
   - **Restart your terminal/IDE** (VS Code, PowerShell, etc.) to ensure the new PATH is loaded.

## 3. Python Dependencies

Once GTK3 is installed and in your PATH, you can install the required Python libraries.

1. Open a standard terminal or PowerShell in your project directory.
2. (Optional but recommended) Create and activate a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install WeasyPrint and Jinja2:
   ```bash
   pip install weasyprint jinja2
   ```

## 4. Module Directory Structure

This `pdf_export_module` folder contains everything needed to run the PDF generation standalone:

```
pdf_export_module/
├── assets/                  # Fonts and images required for the report layout
│   └── report/
│       └── fonts/           # Public Sans, Archivo TTF files
├── data/                    # JSON data files (e.g., test_report_data.json)
├── report_engine/           # Core logic and templates
│   ├── exports/             # Output directory where PDFs are saved
│   ├── generators/
│   │   ├── asset_manager.py # Handles absolute paths for assets (WeasyPrint needs absolute file:/// URIs)
│   │   ├── data_provider.py # Formats data before passing to templates
│   │   └── pdf_generator.py # Jinja2 -> HTML rendering and WeasyPrint PDF generation
│   └── templates/
│       ├── components/      # Partial HTML components (header, footer, etc.)
│       ├── pages/           # Page specific templates (cover, toc, etc.)
│       ├── report_assembler.html # Master layout bringing it all together
│       └── report_template.html  # CSS and structure definitions
└── test_pdf_gen.py          # Entry point to test the generation
```

## 5. Running the PDF Generator

To test the setup and generate a sample PDF report, simply run:

```bash
python test_pdf_gen.py
```

- It will load sample data (or generate dummy data if the file is missing).
- It will render the HTML via Jinja2 (saving a `debug.html` in `report_engine/exports/`).
- It will convert the HTML to a PDF using WeasyPrint and save it in `report_engine/exports/`.
- The console will output the path to the generated PDF.
