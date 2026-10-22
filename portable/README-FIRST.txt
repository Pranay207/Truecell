TRUECELL PORTABLE FOR WINDOWS 10/11 x64
======================================

1. Keep this entire folder together. Do not move Truecell.exe by itself.
2. Double-click Truecell.exe.
3. Your browser opens the local Truecell workspace automatically.
4. Close the Truecell console window to stop the local application.

Python, Node.js, an API key and internet access are not required.
Bundled RapidOCR handles scanned documents offline. The portable build does not
depend on or invoke a separately installed Tesseract; the source and Docker
versions can use Tesseract and its installed language packs.

Saved documents and review history stay inside the TruecellData folder created
beside Truecell.exe. Delete that folder only when you intend to remove those
local workspaces.

Optional same-Wi-Fi phone demo:
  Truecell.exe --lan
Use this only on a trusted private network. LAN mode has no authentication;
never expose it to the public internet.

Windows may show a SmartScreen warning because this portable build is not
code-signed. Use only the archive supplied from the official Truecell project
and compare its SHA-256 value with the sibling
Truecell-Portable-Windows-x64.zip.sha256 file. After extraction, use the bundled
SHA256SUMS.txt file to verify the extracted files.

Source code, setup instructions and licence:
https://github.com/Pranay207/Truecell

Truecell is licensed AGPL-3.0-or-later. Third-party notices are supplied in
THIRD_PARTY.md and inside the bundled dependency distributions.
