import subprocess
import sys
import os
import shutil

def build_jobman():
    print("🚀 Initializing JobMan Build Process...")
    
    # 1. Clean previous builds
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            
    # 2. Locate pkg_resources for brute-force bundling
    # Direct import fails in MS Store Python, so we find it via setuptools path
    pkg_path = None
    try:
        import setuptools
        site_packages_dir = os.path.dirname(os.path.dirname(setuptools.__file__))
        candidate = os.path.join(site_packages_dir, 'pkg_resources')
        if os.path.isdir(candidate):
            pkg_path = candidate
            print(f"📍 Located pkg_resources at: {pkg_path}")
        else:
            print(f"⚠️  pkg_resources folder not found at: {candidate}")
    except ImportError:
        pass
    
    if not pkg_path:
        # Fallback: search all site-packages directories
        import site
        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            candidate = os.path.join(sp, 'pkg_resources')
            if os.path.isdir(candidate):
                pkg_path = candidate
                print(f"📍 Located pkg_resources (fallback) at: {pkg_path}")
                break
    
    if not pkg_path:
        print("⚠️  Warning: pkg_resources not found anywhere. Build may fail on target.")

    # 3. Define PyInstaller command
    sep = ';' if sys.platform == 'win32' else ':'
    
    command = [
        sys.executable, '-m', 'PyInstaller',
        '--noconsole',
        '--name=JobMan',
        f'--add-data=templates{sep}templates',
        f'--add-data=static{sep}static',
    ]

    # Brute-force include the pkg_resources folder if found
    if pkg_path:
        command.append(f'--add-data={pkg_path}{sep}pkg_resources')
        command.append('--hidden-import=pkg_resources')

    command.extend([
        '--collect-all=setuptools',
        '--collect-all=crawl4ai',
        '--collect-all=playwright_stealth', # Bundle JS data files (generate.magic.arrays.js etc.)
        '--collect-all=chardet',
        '--copy-metadata=setuptools',
        '--copy-metadata=crawl4ai',
        '--hidden-import=chardet',
        '--hidden-import=numpy._core',
    ])

    # Optional assets
    if os.path.exists('config.json'):
        command.append(f'--add-data=config.json{sep}.')
        
    icon_path = 'static/favicon.ico'
    if os.path.exists(icon_path):
        command.append(f'--icon={icon_path}')
    else:
        print("⚠️  Warning: static/favicon.ico not found. Building without icon.")
    
    command.append('app.py')
    
    print(f"📦 Running command: {' '.join(command)}")
    
    try:
        subprocess.run(command, check=True)
        print("\n✅ Build Successful! Check the 'dist/JobMan' folder.")
        print("Note: In your final installer, make sure to include the 'output' and 'stitch' folders if they are required for persistent data.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build Failed: {e}")

if __name__ == "__main__":
    # Ensure dependencies are installed for the build
    print("Checking build dependencies...")
    # These versions are critical for Python 3.13 stability
    subprocess.run([sys.executable, "-m", "pip", "install", 
                   "pyinstaller==6.11.0", 
                   "chardet==6.0.0", 
                   "numpy==2.1.0", 
                   "psutil==6.1.1", 
                   "pydantic==2.10.0", 
                   "rich==13.9.4",
                   "beautifulsoup4==4.12.3"])
        
    build_jobman()
