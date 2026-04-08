import os
import subprocess
import psutil
import requests
import json
import logging
from typing import Dict, Any

class SetupManager:
    def __init__(self):
        self.ollama_base_url = "http://127.0.0.1:11434"
        self.install_command = "powershell -Command \"irm https://ollama.com/install.ps1 | iex\""
        
    def check_ollama_presence(self) -> bool:
        """Check if ollama is reachable on the local port."""
        try:
            resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            return resp.status_code == 200
        except:
            # Check if the process is in the path at least
            try:
                subprocess.run(["ollama", "--version"], capture_output=True, check=True)
                return True
            except:
                return False

    def install_ollama(self):
        """Execute the PowerShell installation command."""
        # Use shell=True and start a new terminal window for visibility as requested
        subprocess.Popen(["start", "powershell", "-NoExit", "-Command", "irm https://ollama.com/install.ps1 | iex"], shell=True)

    def get_hardware_specs(self) -> Dict[str, Any]:
        """Audit the system RAM and GPU."""
        specs = {
            "ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "gpu": None,
            "gpu_vram_mb": 0
        }
        
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                specs["gpu"] = gpus[0].name
                specs["gpu_vram_mb"] = gpus[0].memoryTotal
        except ImportError:
            pass # GPUtil not installed yet
            
        return specs

    def select_recommend_model(self, specs: Dict[str, Any]) -> str:
        """Decide which model to pull based on hardware."""
        ram = specs["ram_gb"]
        vram = specs["gpu_vram_mb"] / 1024 # Convert to GB
        
        # Priority 1: High VRAM GPU
        if vram >= 8:
            return "llama3.1:8b"
        
        # Priority 2: Decent System RAM
        if ram >= 16:
            return "llama3:8b"
        
        # Priority 3: Mid Range
        if ram >= 8:
            return "phi3:mini"
            
        # Priority 4: Low Spec
        return "tinyllama"

    def pull_model(self, model_name: str):
        """Trigger an Ollama pull for the specific model."""
        url = f"{self.ollama_base_url}/api/pull"
        payload = {"name": model_name}
        try:
            # Use streaming request to capture progress if needed, 
            # but for now we just fire and forget or check status
            requests.post(url, json=payload, timeout=5)
            return True
        except:
            return False

setup_manager = SetupManager()
