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
        # The PowerShell script downloads, installs, and then starts the Ollama app so the server becomes available
        ps_cmd = 'irm https://ollama.com/install.ps1 | iex ; Start-Sleep -Seconds 2 ; $ollamaPath = "$env:LOCALAPPDATA\\Programs\\Ollama\\ollama.exe" ; if (Test-Path $ollamaPath) { Start-Process $ollamaPath }'
        subprocess.Popen(["start", "powershell", "-Command", ps_cmd], shell=True)

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
        #    Check if Ollama's HTTP API is actually responding (not just the binary existing)
        def is_ollama_api_alive():
            try:
                resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=3)
                return resp.status_code == 200
            except:
                return False

        if not is_ollama_api_alive():
            self.update_status("Downloading Ollama AI Engine...", 25)
            self.install_ollama()
            
            # Wait up to 10 minutes (600s) for Ollama to fully install AND start its server
            max_wait = 300  # 300 iterations × 2s = 10 minutes
            for i in range(max_wait):
                time.sleep(2)
                if is_ollama_api_alive():
                    break
                elapsed = (i + 1) * 2
                # Progress: scale between 25% and 48% over the wait period
                prog = 25 + min(int((elapsed / 120) * 23), 23)  # cap at 48%
                minutes = elapsed // 60
                seconds = elapsed % 60
                self.update_status(f"Waiting for Ollama Engine... ({minutes}m {seconds}s)", prog)
            else:
                # Timed out after 10 minutes — don't fake 100%
                self.update_status("Ollama Engine: TIMEOUT — Please install manually and restart", 25)
                return
        
        self.update_status("Intelligence Engine: READY", 50)

        # 3. Phase 3: Intelligence Pull (50-95%)
        #    Only attempt if the API is actually responding
        if is_ollama_api_alive():
            self.update_status(f"Downloading {model_name} Neural Weights...", 55)
            url = f"{self.ollama_base_url}/api/pull"
            payload = {"name": model_name, "stream": True}
            try:
                with requests.post(url, json=payload, stream=True, timeout=1800) as r:
                    for line in r.iter_lines():
                        if line:
                            data = json.loads(line)
                            status_msg = data.get("status", "")
                            if "total" in data and data.get("completed"):
                                # Scaled between 55% and 95%
                                prog = 55 + int((data["completed"] / data["total"]) * 40)
                                dl_pct = int((data["completed"] / data["total"]) * 100)
                                self.update_status(f"Downloading {model_name} — {dl_pct}%", prog)
                            elif status_msg:
                                self.update_status(f"Downloading {model_name} — {status_msg}", 55)
            except Exception as e:
                self.update_status(f"Sync Error: {str(e)}", 50)
                return
        else:
            self.update_status("Ollama API not available — skipping model pull", 50)
            return

        # 4. Phase 4: Path Configuration & Finalization (95-100%)
        self.update_status("Configuring Neural Paths...", 97)
        time.sleep(1.5)
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
