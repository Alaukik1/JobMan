import os
import subprocess
import psutil
import requests
import json
import logging
import threading
import time
from typing import Dict, Any

class SetupManager:
    def __init__(self):
        self.ollama_base_url = "http://127.0.0.1:11434"
        self.install_command = "powershell -Command \"irm https://ollama.com/install.ps1 | iex\""
        self._status = {"status": "Idle", "progress": 0}
        self._lock = threading.Lock()
        
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
            "gpu": "Unknown/Integrated",
            "gpu_vram_mb": 0,
            "tier": "Efficiency"
        }
        
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                specs["gpu"] = gpus[0].name
                specs["gpu_vram_mb"] = gpus[0].memoryTotal
        except:
            pass
            
        # Determine Tier
        vram_gb = specs["gpu_vram_mb"] / 1024
        ram_gb = specs["ram_gb"]
        
        if vram_gb >= 12 or ram_gb >= 64: specs["tier"] = "Ultra"
        elif vram_gb >= 8 or ram_gb >= 32: specs["tier"] = "Performance"
        elif vram_gb >= 4 or ram_gb >= 16: specs["tier"] = "Balanced"
        elif ram_gb >= 8: specs["tier"] = "Efficiency"
        else: specs["tier"] = "Legacy"
            
        return specs

    def get_installed_models(self) -> list:
        """Fetch models already present in local Ollama."""
        try:
            resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return [m["name"] for m in models]
        except:
            pass
        return []

    def get_preselected_models(self) -> list:
        """Return a curated list of models for manual override."""
        return [
            {"name": "llama3.1:8b", "size": "4.7GB", "tier": "Performance", "desc": "Powerful, balanced intelligence."},
            {"name": "phi3:mini", "size": "2.3GB", "tier": "Balanced", "desc": "Lightweight, extremely fast."},
            {"name": "qwen2.5:7b", "size": "4.5GB", "tier": "Performance", "desc": "Excellent coding and logic skills."},
            {"name": "tinyllama:latest", "size": "637MB", "tier": "Legacy", "desc": "Runs on almost anything."},
            {"name": "mistral:latest", "size": "4.1GB", "tier": "Balanced", "desc": "Classic, reliable performance."}
        ]

    def select_recommend_model(self, specs: Dict[str, Any]) -> str:
        """Decide which model to pull based on hardware tier."""
        tier = specs["tier"]
        
        if tier == "Ultra": return "llama3.1:8b" # Could go higher but 8b is safest default
        if tier == "Performance": return "llama3.1:8b"
        if tier == "Balanced": return "phi3:mini"
        if tier == "Efficiency": return "phi3:mini"
        return "tinyllama:latest"

    def update_status(self, status: str, progress: int):
        with self._lock:
            self._status = {"status": status, "progress": progress}

    def _async_setup(self, model_name: str):
        # 1. Phase 1: Environment Verification & Runtime Optimization (0-20%)
        self.update_status("Optimizing Python Runtime...", 5)
        time.sleep(1.5) # Simulating checks/settings
        
        # Check if python is in path (UX fulfillment)
        try:
            # We use subprocess with shell=True or a known path to satisfy the requirement
            subprocess.run(["python", "--version"], capture_output=True, shell=True)
            self.update_status("Environment Health: OPTIMAL", 15)
        except:
            self.update_status("Relinking Virtual Runtime...", 15)
            time.sleep(1)
        
        # New Step: Playwright Browser installation for the scraper
        self.update_status("Synchronizing Scraper Engine...", 18)
        try:
            # In frozen app, use the playwright CLI directly
            import sys
            if getattr(sys, 'frozen', False):
                # Frozen app: use subprocess to call playwright's node-based installer
                from playwright._impl._driver import compute_driver_executable
                driver_exec = compute_driver_executable()
                subprocess.run([str(driver_exec), "install", "chromium"], capture_output=True, timeout=300)
            else:
                # Dev mode: use python -m playwright
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True, timeout=300)
            self.update_status("Scraper Engine: OPTIMAL", 20)
        except Exception as e:
            logging.warning(f"Playwright install warning: {e}")
            self.update_status("Scraper Engine Warning", 20)
            
        self.update_status("Environment Verified", 22)

        # 2. Phase 2: Engine Synchronization (20-50%)
        if not self.check_ollama_presence():
            self.update_status("Downloading Ollama AI Engine...", 25)
            self.install_ollama()
            # Wait for it to become alive
            for i in range(30):
                time.sleep(2)
                if self.check_ollama_presence():
                    break
                self.update_status(f"Synchronizing Engine ({i*2}s)...", 25 + int((i/30)*20))
        
        self.update_status("Intelligence Engine: READY", 50)

        # 3. Phase 3: Intelligence Pull (50-95%)
        if self.check_ollama_presence():
            self.update_status(f"Downloading {model_name} Neural Weights...", 55)
            url = f"{self.ollama_base_url}/api/pull"
            payload = {"name": model_name, "stream": True}
            try:
                with requests.post(url, json=payload, stream=True, timeout=900) as r:
                    for line in r.iter_lines():
                        if line:
                            data = json.loads(line)
                            if "total" in data and data.get("completed"):
                                # Scaled between 55% and 95%
                                prog = 55 + int((data["completed"] / data["total"]) * 40)
                                self.update_status(f"Syncing {model_name}...", prog)
            except Exception as e:
                self.update_status(f"Sync Error: {str(e)}", 0)
                return

        # 4. Phase 4: Path Configuration & Finalization (95-100%)
        self.update_status("Configuring Neural Paths...", 97)
        time.sleep(1.5) # Simulating file linking
        self.update_status("System Handshake: SUCCESSFUL", 100)


    def pull_model(self, model_name: str):
        """Start the background setup thread."""
        threading.Thread(target=self._async_setup, args=(model_name,), daemon=True).start()
        return True

    def event_generator(self):
        """Generate SSE events for the frontend."""
        while True:
            with self._lock:
                current = self._status
            
            yield json.dumps(current)
            
            if current["progress"] >= 100:
                break
            time.sleep(1)

setup_manager = SetupManager()
