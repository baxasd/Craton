import sys
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

project_root = os.path.abspath(os.path.join(SPECPATH, '..')) #type: ignore
sys.path.insert(0, project_root)

ICON =  os.path.join(project_root, 'assets', 'icon.ico')
COMMAND_ICON = os.path.join(project_root, 'assets', 'command.ico')

MANIFEST = os.path.join(project_root, 'manifest.xml')
FIX = os.path.join(project_root, 'src', 'utils', 'fix.py')
block_cipher = None

mp_datas, mp_binaries, mp_hidden = collect_all('mediapipe')
rs_datas, rs_binaries, rs_hidden = collect_all('pyrealsense2')
cv_datas, cv_binaries, cv_hidden = collect_all('cv2')
st_all_datas, st_all_binaries, st_all_hidden = collect_all('streamlit')
st_datas = st_all_datas + copy_metadata('plotly')

shared_datas = [
    (os.path.join(project_root, 'assets'), 'assets'),
    (os.path.join(project_root, 'src'), 'src'),
]

base_hidden = mp_hidden + rs_hidden + cv_hidden + ['pyarrow.vendored.version', 'zmq']


# =============================================================================
#   BUILD 1: STREAM
# =============================================================================
a_stream = Analysis( #type: ignore
    [os.path.join(project_root, 'stream.py')],
    pathex=[project_root, os.path.join(project_root, 'src')],
    datas=shared_datas + mp_datas + rs_datas + cv_datas,
    hiddenimports=base_hidden + ['src', 'mediapipe'],
    runtime_hooks=[FIX], 
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_stream = PYZ(a_stream.pure, a_stream.zipped_data, cipher=block_cipher) #type: ignore

exe_stream = EXE( #type: ignore
    pyz_stream,
    a_stream.scripts,
    [],
    exclude_binaries=True,
    name='Stream',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=COMMAND_ICON,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
    contents_directory='libs'
)

# =============================================================================
#   BUILD 2: VIEW
# =============================================================================
a_view = Analysis( #type: ignore
    [os.path.join(project_root, 'view.py')],
    pathex=[project_root, os.path.join(project_root, 'src')],
    datas=shared_datas,
    hiddenimports=base_hidden + ['src', 'pyqtgraph'],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_view = PYZ(a_view.pure, a_view.zipped_data, cipher=block_cipher) #type: ignore

exe_view = EXE( #type: ignore
    pyz_view,
    a_view.scripts,
    [],
    exclude_binaries=True,
    name='Viewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=COMMAND_ICON,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
    contents_directory='libs'
)

# =============================================================================
#   BUILD 3: STUDIO
# =============================================================================
stu_datas = shared_datas + st_datas + [(os.path.join(project_root, '.streamlit'), '.streamlit')]
stu_hidden = ['src', 'streamlit', 'pandas', 'plotly', 'numpy', 'configparser', 'zmq', 'charset_normalizer'] + st_all_hidden

a_stu = Analysis( #type: ignore
    [os.path.join(project_root, 'app.py')],
    pathex=[project_root, os.path.join(project_root, 'src')],
    datas=stu_datas,
    hiddenimports=stu_hidden,
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_stu = PYZ(a_stu.pure, a_stu.zipped_data, cipher=block_cipher) #type: ignore

exe_stu = EXE( #type: ignore
    pyz_stu,
    a_stu.scripts,
    [],
    exclude_binaries=True,
    name='Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=ICON,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
    contents_directory='libs'
)


# =============================================================================
#   BUILD 4: KEYGEN
# =============================================================================
a_keygen = Analysis( #type: ignore
    [os.path.join(project_root, 'keys.py')],
    pathex=[project_root, os.path.join(project_root, 'src')],
    datas=[], # No special data needed for keygen
    hiddenimports=['src', 'configparser'],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_keygen = PYZ(a_keygen.pure, a_keygen.zipped_data, cipher=block_cipher) #type: ignore

exe_keygen = EXE( #type: ignore
    pyz_keygen,
    a_keygen.scripts,
    [],
    exclude_binaries=True,
    name='Keygen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=COMMAND_ICON,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
    contents_directory='libs'
)

# =============================================================================
#   FINAL MERGE & ORGANIZE
# =============================================================================
coll = COLLECT( #type: ignore
    exe_stream,
    a_stream.binaries,
    a_stream.zipfiles,
    a_stream.datas,
    
    exe_view,
    a_view.binaries,
    a_view.zipfiles,
    a_view.datas,
    
    exe_stu,
    a_stu.binaries,
    a_stu.zipfiles,
    a_stu.datas,

    exe_keygen,
    a_keygen.binaries,
    a_keygen.zipfiles,
    a_keygen.datas,
    
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OST Suite',
    contents_directory='libs' 
)