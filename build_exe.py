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
            
    # 2. Define PyInstaller command
    # Use sys.executable -m PyInstaller to ensure we use the local environment
    sep = ';' if sys.platform == 'win32' else ':'
    
    command = [
        sys.executable, '-m', 'PyInstaller',
        '--noconsole',
        '--name=JobMan',
        f'--add-data=templates{sep}templates',
        f'--add-data=static{sep}static',
        '--collect-all=chardet',   # Ensure chardet is fully included
        '--hidden-import=chardet',
        '--hidden-import=numpy._core', # Mandatory for NumPy 2.x on Python 3.13
    ]

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
