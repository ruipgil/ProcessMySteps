# -*- mode: python -*-

block_cipher = None

a = Analysis(
  ['server.py'],
  pathex=['.'],
  binaries=None,
  datas=None,
  hiddenimports=[
    "sklearn.neighbors.typedefs",
    "flask",
    "email.mime.multipart",
    "email.mime.message",
    "email.mime.image",
    "email.mime.audio",
    "email.mime.text"
  ],
  hookspath=[],
  runtime_hooks=[],
  excludes=["matplotlib"],
  win_no_prefer_redirects=False,
  win_private_assemblies=False,
  cipher=block_cipher
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
  pyz,
  a.scripts,
  exclude_binaries=True,
  name='server',
  debug=True,
  strip=False,
  upx=True,
  console=True
)
coll = COLLECT(
  exe,
  a.binaries,
  a.zipfiles,
  a.datas,
  strip=False,
  upx=True,
  name='processmysteps'
)
