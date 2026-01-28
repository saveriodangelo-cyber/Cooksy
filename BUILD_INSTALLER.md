# Cooksy - Building the Installer

## Prerequisites

### 1. NSIS Installation
Download and install NSIS from: https://nsis.sourceforge.io/Download

The installer will be located at:
- Windows 32-bit: `C:\Program Files\NSIS\makensis.exe`
- Windows 64-bit: `C:\Program Files (x86)\NSIS\makensis.exe`

### 2. Python Requirements
Ensure you have:
- Python 3.11+
- PyInstaller 6.0+
- All dependencies from `requirements.txt`

## Build Instructions

### Option 1: Automated Build (Recommended)

Simply run the build script:

```batch
build-installer.bat
```

This will:
1. Check for PyInstaller build (`dist\Cooksy\Cooksy.exe`)
2. Verify NSIS installation
3. Compile the NSIS script
4. Generate `Cooksy-1.0.0-Setup.exe` in the `releases\` folder

### Option 2: Manual Build

#### Step 1: Build PyInstaller executable
```bash
python -m PyInstaller Cooksy.spec --distpath dist --workpath build
```

This creates: `dist\Cooksy\Cooksy.exe` and all dependencies

#### Step 2: Build NSIS installer
```bash
"C:\Program Files (x86)\NSIS\makensis.exe" "Cooksy-Installer.nsi"
```

Or on 64-bit with 32-bit NSIS:
```bash
"C:\Program Files\NSIS\makensis.exe" "Cooksy-Installer.nsi"
```

This creates: `Cooksy-1.0.0-Setup.exe`

## Output

Your final installer will be:
- **Location**: `Cooksy-1.0.0-Setup.exe` (or in `releases\` if using automated script)
- **Size**: ~200-300 MB (depends on PyInstaller bundle size)
- **Installer Features**:
  - Professional NSIS installer UI
  - Start Menu shortcuts
  - Desktop shortcut (optional)
  - Windows Registry entries
  - Uninstaller with cleanup
  - Auto-launch application after installation

## Distribution

To distribute the installer:
1. Copy `Cooksy-1.0.0-Setup.exe` to your distribution server/location
2. Users can run it directly - no Python installation required
3. The app will install to `C:\Program Files\Cooksy\`

## Environment Variables

The installer/app will automatically load:
- `RICETTEPDF_OPENAI_KEY` from system environment (if set)
- `.env.local` from the application directory (for development)

To set the OpenAI key system-wide before distribution, run as Administrator:
```batch
setup_env.bat
```

## Troubleshooting

### "NSIS not found" error
- Install NSIS from the link above
- Ensure it's in the default installation path

### "PyInstaller build not found" error
- Run: `python -m PyInstaller Cooksy.spec --distpath dist --workpath build`
- Wait for the build to complete (can take 5-10 minutes)

### Installer won't create shortcuts
- Run as Administrator
- Check Windows Registry permissions

## File Structure

```
ricetta/
├── dist/Cooksy/           # PyInstaller output (all files needed)
├── Cooksy.spec            # PyInstaller configuration
├── Cooksy-Installer.nsi   # NSIS installer script
├── build-installer.bat    # Automated build script
├── releases/              # Final installer output (created after build)
└── setup_env.bat          # Set environment variables globally
```
