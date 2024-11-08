import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import subprocess
from crontab import CronTab
import json

class SyncManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Správce synchronizace")
        self.root.geometry("650x550")  
        
        # Initialize status variable first
        self.status_var = tk.StringVar(value="Připraveno")
        
        # Define schedule options with Czech names
        self.schedule_options = {
            "Nikdy": "",
            "Každou hodinu": "0 * * * *",
            "Jednou denně": "0 0 * * *",
            "Jednou týdně": "0 0 * * 0",
            "Jednou měsíčně": "0 0 1 * *",
            "Jednou ročně": "0 0 1 1 *"
        }
        
        # Define script locations with Czech display names
        self.scripts = [
            {
                'name': 'contacts_to_app.py',
                'subfolder': 'contacts-app',
                'display_name': 'Synchronizace kontaktů do aplikace'
            },
            {
                'name': 'contacts_to_portal_obcana_API.py',
                'subfolder': 'contacts-portal-obcana',
                'display_name': 'Synchronizace kontaktů na portál občana'
            },
            {
                'name': 'newspapers_to_app_API.py',
                'subfolder': 'zpravodaj-app',
                'display_name': 'Synchronizace zpravodaje'
            },
            {
                'name': 'documents_to_portal-obcana_API.py',
                'subfolder': 'documents-portal-obcana',
                'display_name': 'Synchronizace dokumentů na portál občana'
            }
        ]
        
        # Load config if exists
        self.config_file = os.path.expanduser("~/.sync_manager_config.json")
        self.load_config()
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scripts folder section with last used path
        ttk.Label(main_frame, text="Základní složka:").grid(row=0, column=0, sticky=tk.W)
        self.folder_path = tk.StringVar(value=self.get_last_folder_path())
        path_entry = ttk.Entry(main_frame, textvariable=self.folder_path, width=50)
        path_entry.grid(row=0, column=1, padx=5)
        
        ttk.Button(main_frame, text="Procházet", command=self.browse_folder).grid(row=0, column=2)
        
        # Scripts list section
        ttk.Label(main_frame, text="Synchronizační skripty:", padding=(0, 10, 0, 5)).grid(row=1, column=0, sticky=tk.W)
        
        # Create script frames
        self.script_frames = []
        for i, script in enumerate(self.scripts):
            frame = ttk.LabelFrame(main_frame, text=script['display_name'], padding="5")
            frame.grid(row=i+2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
            
            # Add status indicator
            status_var = tk.StringVar(value="Nenalezeno")
            status_label = ttk.Label(frame, textvariable=status_var, width=15)
            status_label.grid(row=0, column=0, padx=5)
            
            # Run button
            run_button = ttk.Button(frame, text="Spustit", 
                                  command=lambda s=script: self.run_script(s))
            run_button.grid(row=0, column=1, padx=5)
            
            ttk.Label(frame, text="Plán:").grid(row=0, column=2, padx=5)
            
            # Create schedule dropdown
            schedule_var = tk.StringVar()
            schedule_dropdown = ttk.Combobox(frame, 
                                          textvariable=schedule_var,
                                          values=list(self.schedule_options.keys()),
                                          state="readonly",
                                          width=15)
            schedule_dropdown.grid(row=0, column=3, padx=5)
            
            # Set initial value based on saved config
            saved_cron = self.config.get(f'schedule_{script["name"]}', '')
            initial_schedule = "Nikdy"
            for schedule_name, cron_expr in self.schedule_options.items():
                if cron_expr == saved_cron:
                    initial_schedule = schedule_name
                    break
            schedule_var.set(initial_schedule)
            
            # Save schedule button
            ttk.Button(frame, text="Uložit plán", 
                      command=lambda s=script, v=schedule_var: 
                          self.save_schedule(s, self.schedule_options[v.get()])
                      ).grid(row=0, column=4, padx=5)
            
            self.script_frames.append({
                'frame': frame,
                'status_var': status_var,
                'run_button': run_button,
                'schedule_var': schedule_var,
                'script_info': script
            })
        
        # Status section with better visibility
        status_label = ttk.Label(main_frame, textvariable=self.status_var, wraplength=550)
        status_label.grid(row=len(self.scripts)+2, column=0, columnspan=3, pady=10)
        
        # Now that everything is initialized, validate the folder if we have one
        if self.folder_path.get():
            self.validate_folder_path(self.folder_path.get())

    def validate_folder_path(self, path):
        """Validate the folder path and check for all scripts"""
        if not os.path.exists(path):
            self.status_var.set(f"Varování: Vybraná složka neexistuje: {path}")
            return False
        
        # Check each script
        missing_scripts = []
        found_scripts = []
        
        for frame_info in self.script_frames:
            script_info = frame_info['script_info']
            script_path, exists = self.get_script_path(script_info)
            
            if exists:
                frame_info['status_var'].set("Nalezeno")
                frame_info['run_button'].state(['!disabled'])
                found_scripts.append(script_info['display_name'])
            else:
                frame_info['status_var'].set("Nenalezeno")
                frame_info['run_button'].state(['disabled'])
                missing_scripts.append(f"{script_info['display_name']} (očekáváno v {script_info['subfolder']})")
        
        # Update status
        if missing_scripts:
            self.status_var.set(f"Chybějící skripty:\n" + "\n".join(missing_scripts))
            return False
        else:
            self.status_var.set(f"Všechny skripty byly nalezeny")
            return True

    def save_schedule(self, script_info, schedule):
        """Save schedule with predefined options"""
        try:
            cron = CronTab(user=True)
            script_path, exists = self.get_script_path(script_info)
            
            # Always remove existing jobs for this script first
            for job in cron:
                if script_path in str(job.command):
                    cron.remove(job)
            
            # Only create new job if schedule is not empty (not "Never")
            if schedule.strip():
                if not exists:
                    messagebox.showerror("Chyba", "Nelze nastavit plán: Skript nebyl nalezen")
                    return
                    
                job = cron.new(command=f'/usr/bin/python3 {script_path}',
                             comment=f'sync_manager_{script_info["name"]}')
                job.setall(schedule)
                cron.write()
                
                # Show success message with human-readable schedule
                schedule_name = self.get_schedule_display(schedule)
                self.status_var.set(f"Plán nastaven na {schedule_name} pro {script_info['display_name']}")
            else:
                # If schedule is empty (Never selected), just write the crontab after removal
                cron.write()
                self.status_var.set(f"Plán odstraněn pro {script_info['display_name']}")
            
            # Save to config
            self.config[f'schedule_{script_info["name"]}'] = schedule
            self.save_config()
                
        except Exception as e:
            messagebox.showerror("Chyba plánu", f"Chyba při nastavování plánu: {str(e)}")
            self.status_var.set(f"Chyba při nastavování plánu: {str(e)}")

    def run_script(self, script_info):
        """Run script with improved error handling"""
        script_path, exists = self.get_script_path(script_info)
        if not exists:
            messagebox.showerror("Chyba", f"Skript nebyl nalezen: {script_info['name']}")
            self.status_var.set(f"Chyba: Skript {script_info['name']} nebyl nalezen!")
            return
            
        try:
            self.status_var.set(f"Spouštím {script_info['display_name']}...")
            self.root.update()
            
            process = subprocess.run(['python3', script_path], 
                                   check=True,
                                   capture_output=True,
                                   text=True)
            
            if process.returncode == 0:
                self.status_var.set(f"Úspěšně spuštěno {script_info['display_name']}")
            else:
                # Show error from stderr if available
                error_message = process.stderr if process.stderr else "Neznámá chyba"
                messagebox.showerror("Chyba synchronizace", error_message)
                # self.status_var.set(error_message)
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else "Neznámá chyba při spuštění skriptu"
            messagebox.showerror("Chyba skriptu", error_msg)
            self.status_var.set(error_msg)

    # Helper methods remain the same as they don't contain user-facing strings
    def get_script_path(self, script_info):
        """Get full path for a script and check if it exists"""
        full_path = os.path.join(self.folder_path.get(), 
                           script_info['subfolder'], 
                           script_info['name'])
        exists = os.path.exists(full_path)
        return full_path, exists
    
    def get_last_folder_path(self):
        return self.config.get('scripts_folder', os.path.expanduser("~"))
    
    def get_schedule_display(self, cron_expression):
        for name, expr in self.schedule_options.items():
            if expr == cron_expression:
                return name
        return "Nikdy"

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            else:
                self.config = {}
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        except Exception as e:
            self.config = {}
            messagebox.showwarning("Chyba načtení konfigurace", 
                                 f"Nelze načíst konfigurační soubor: {str(e)}\nPoužívám výchozí nastavení.")

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            messagebox.showerror("Chyba uložení konfigurace", 
                               f"Nelze uložit konfigurační soubor: {str(e)}")

    def browse_folder(self):
        initial_dir = self.folder_path.get() if os.path.exists(self.folder_path.get()) else os.path.expanduser("~")
        folder = filedialog.askdirectory(initialdir=initial_dir)
        
        if folder:
            self.folder_path.set(folder)
            self.config['scripts_folder'] = folder
            self.save_config()
            self.validate_folder_path(folder)

def main():
    root = tk.Tk()
    app = SyncManagerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()