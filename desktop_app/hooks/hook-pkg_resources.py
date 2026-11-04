# hooks/hook-pkg_resources.py
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all pkg_resources submodules
hiddenimports = collect_submodules('pkg_resources')

# Collect data files for pkg_resources
datas = collect_data_files('pkg_resources')