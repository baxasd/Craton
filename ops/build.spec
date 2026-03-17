import sys
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

# Paths

project_root = os.path.abspath(os.path.join(SPECPATH, '..')) #type: ignore
sys.path.insert(0, project_root)

MANIFEST = os.path.join(project_root, 'ops', 'manifest.xml')
block_cipher = None

# COLLECT EXTERNAL LIBRARIES

mp_datas, mp_binaries, mp_hidden = collect_all('mediapipe')
rs_datas, rs_binaries, rs_hidden = collect_all('pyrealsense2')
cv_datas, cv_binaries, cv_hidden = collect_all('cv2')
st_datas = copy_metadata('streamlit') + copy_metadata('plotly')

# SHARED DATA & Imports

shared_datas = [
    (os.path.join(project_root, 'assets'), 'assets'),
    (os.path.join(project_root, 'core'), 'core'),
    (os.path.join(project_root, 'settings-template.ini'), '.')
]

# Base hidden imports for hardware & network
base_hidden = mp_hidden + rs_hidden + cv_hidden + ['pyarrow.vendored.version', 'zmq']

#   BUILD 1: STREAM (PUBLISHER NODE)

a_stream = Analysis( #type: ignore
    [os.path.join(project_root, 'stream.py')],
    pathex=[project_root],
    datas=shared_datas + mp_datas + rs_datas + cv_datas,
    hiddenimports=base_hidden + ['sensors'],
    runtime_hooks=[]
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
    name='OSTStreamer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
    contents_directory='libs'
)

#   BUILD 2: VIEW (SUBSCRIBER NODE)

a_view = Analysis( #type: ignore
    [os.path.join(project_root, 'view.py')],
    pathex=[project_root],
    datas=shared_datas,
    hiddenimports=base_hidden + ['pyqtgraph'],
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
    name='OSTViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
    contents_directory='libs'
)


#   BUILD 3: STUDIO (LAUNCHER + LAB + KEY)
stu_datas = shared_datas + st_datas + [(os.path.join(project_root, '.streamlit'), '.streamlit')]

# Added zmq here so the keygen menu doesn't crash when imported
stu_hidden = ['streamlit', 'pandas', 'plotly', 'numpy', 'configparser', 'zmq']

a_stu = Analysis( #type: ignore
    [os.path.join(project_root, 'launcher.py')],
    pathex=[project_root],
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
    name='OSTStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
    contents_directory='libs'
)


#   FINAL MERGE & ORGANIZE
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
    
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OST Suite',
    contents_directory='libs' 
)