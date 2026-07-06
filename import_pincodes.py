import os
import sys
import csv
import time
import threading
import subprocess
from queue import Queue

# Try importing database connectors
db_library = None
try:
    import pymysql
    db_library = "pymysql"
except ImportError:
    try:
        import mysql.connector
        db_library = "mysql.connector"
    except ImportError:
        db_library = None

# Tkinter Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

class PincodeImporterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("All India Pincode Importer & Search Directory")
        self.root.geometry("950x750")
        self.root.minsize(850, 650)
        
        # Color Palette (Sleek Modern Dark Mode)
        self.bg_color = "#121214"
        self.card_color = "#1e1e24"
        self.accent_color = "#4f46e5"  # Premium indigo
        self.text_color = "#f3f4f6"
        self.muted_text = "#9ca3af"
        self.border_color = "#374151"
        self.success_color = "#10b981"
        self.error_color = "#ef4444"
        
        self.root.configure(bg=self.bg_color)
        
        # Grid weights
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)
        
        self.log_queue = Queue()
        self.import_running = False
        self.search_results_data = {}
        
        # Setup modern styles
        self.setup_styles()
        
        # Create UI Components
        self.create_header()
        self.create_body()
        
        # Auto-detect default CSV file in folder
        self.detect_default_csv()
        
        # Periodically check log queue
        self.root.after(100, self.process_logs)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # Configure frames and elements
        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_color, relief="flat")
        
        # Labels
        style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.card_color, foreground=self.text_color, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI Semibold", 16))
        style.configure("Sub.TLabel", background=self.bg_color, foreground=self.muted_text, font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=self.card_color, foreground=self.accent_color, font=("Segoe UI Semibold", 11))
        
        # Entries
        style.configure("TEntry", fieldbackground=self.bg_color, foreground=self.text_color, bordercolor=self.border_color, lightcolor=self.border_color, darkcolor=self.border_color)
        
        # Buttons
        style.configure("TButton", background=self.accent_color, foreground="#ffffff", font=("Segoe UI Semibold", 10), borderwidth=0, focuscolor=self.accent_color)
        style.map("TButton", background=[("active", "#6366f1"), ("disabled", "#374151")], foreground=[("disabled", "#9ca3af")])
        
        style.configure("Secondary.TButton", background="#374151", foreground=self.text_color, font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#4b5563")])
        
        style.configure("Danger.TButton", background=self.error_color, foreground="#ffffff", font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#dc2626")])
        
        # Checkbutton
        style.configure("TCheckbutton", background=self.card_color, foreground=self.text_color, focuscolor=self.card_color)
        style.map("TCheckbutton", background=[("active", self.card_color)], foreground=[("active", self.text_color)])
        
        # Progressbar
        style.configure("Custom.Horizontal.TProgressbar", thickness=12, troughcolor=self.border_color, background=self.accent_color)

        # Notebook styling
        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.card_color, foreground=self.muted_text, padding=(14, 6), font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.accent_color)], foreground=[("selected", "#ffffff")])

        # Treeview Styles - Styled as a high-contrast light grid for bulletproof visibility across all systems
        style.configure("Treeview", background="#FFFFFF", foreground="#111111", fieldbackground="#FFFFFF", borderwidth=0, font=("Segoe UI", 10), rowheight=28)
        style.configure("Treeview.Heading", background="#EAF2FF", foreground="#111111", font=("Segoe UI Semibold", 10), padding=5)
        
        # Explicitly map states to force dark text and override native Windows dark/light themes
        style.map("Treeview.Heading", 
                  background=[("active", "#C5DCFF"), ("", "#EAF2FF")],
                  foreground=[("active", "#111111"), ("", "#111111")])
                  
        style.map("Treeview", 
                  background=[("selected", "#2563EB"), ("", "#FFFFFF")],
                  foreground=[("selected", "#FFFFFF"), ("", "#111111")])

    def create_header(self):
        header_frame = ttk.Frame(self.root, padding=(20, 15, 20, 10))
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.columnconfigure(0, weight=1)
        
        title = ttk.Label(header_frame, text="All India Pincode Directory Importer", style="Header.TLabel")
        title.grid(row=0, column=0, sticky="w")
        
        sub = ttk.Label(header_frame, text="Extract, map, and import pincode CSV records into your MariaDB/MySQL database.", style="Sub.TLabel")
        sub.grid(row=1, column=0, sticky="w", pady=(2, 0))
        
        # Database Driver Status Badge
        self.status_label = ttk.Label(header_frame, font=("Segoe UI Semibold", 9))
        self.status_label.grid(row=0, column=1, rowspan=2, sticky="e")
        self.update_driver_badge()

    def update_driver_badge(self):
        global db_library
        if db_library:
            self.status_label.configure(text=f"Driver: {db_library}", foreground=self.success_color)
        else:
            self.status_label.configure(text="Missing MySQL Driver (pymysql)", foreground=self.error_color)

    def create_body(self):
        # Create Notebook for Tabs
        self.notebook = ttk.Notebook(self.root, style="TNotebook")
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=15, pady=(5, 15))
        
        # Tab 1: Import Directory Tab
        import_tab = ttk.Frame(self.notebook, padding=15)
        import_tab.columnconfigure(0, weight=1)
        import_tab.columnconfigure(1, weight=1)
        import_tab.rowconfigure(0, weight=1)
        self.notebook.add(import_tab, text=" Import Directory ")
        
        # Tab 2: Search Pincode Tab
        search_tab = ttk.Frame(self.notebook, padding=15)
        search_tab.columnconfigure(0, weight=1)
        search_tab.rowconfigure(2, weight=1)
        self.notebook.add(search_tab, text=" Search Pincode ")
        
        # Layout Tab 1: Import Controls
        # Left Panel: Settings
        left_panel = ttk.Frame(import_tab, padding=(0, 0, 10, 0))
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.columnconfigure(0, weight=1)
        
        # Database Card
        db_card = ttk.Frame(left_panel, padding=15, style="Card.TFrame")
        db_card.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        db_card.columnconfigure(1, weight=1)
        
        db_title = ttk.Label(db_card, text="CLOUD DATABASE CONFIGURATION", style="Section.TLabel")
        db_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        
        # Fields
        ttk.Label(db_card, text="Host / IP:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        self.db_host = ttk.Entry(db_card)
        self.db_host.insert(0, "14.192.17.185")
        self.db_host.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)
        
        ttk.Label(db_card, text="Port:", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        self.db_port = ttk.Entry(db_card)
        self.db_port.insert(0, "3306")
        self.db_port.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=6)
        
        ttk.Label(db_card, text="Username:", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        self.db_user = ttk.Entry(db_card)
        self.db_user.insert(0, "root")
        self.db_user.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=6)
        
        ttk.Label(db_card, text="Password:", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=6)
        self.db_pass = ttk.Entry(db_card, show="*")
        self.db_pass.insert(0, "brdb123")
        self.db_pass.grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=6)
        
        ttk.Label(db_card, text="Database:", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=6)
        self.db_name = ttk.Entry(db_card)
        self.db_name.insert(0, "caerp_db_master")
        self.db_name.grid(row=5, column=1, sticky="ew", padx=(10, 0), pady=6)
        
        # Test connection button
        self.btn_test = ttk.Button(db_card, text="Test Connection", command=self.test_connection, style="Secondary.TButton")
        self.btn_test.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        
        # File & Options Card
        opts_card = ttk.Frame(left_panel, padding=15, style="Card.TFrame")
        opts_card.grid(row=1, column=0, sticky="ew")
        opts_card.columnconfigure(1, weight=1)
        
        opts_title = ttk.Label(opts_card, text="IMPORT SOURCE & OPTIONS", style="Section.TLabel")
        opts_title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        
        ttk.Label(opts_card, text="CSV File Path:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        self.csv_path = ttk.Entry(opts_card)
        self.csv_path.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=6)
        
        self.btn_browse = ttk.Button(opts_card, text="...", width=3, command=self.browse_csv, style="Secondary.TButton")
        self.btn_browse.grid(row=1, column=2, sticky="e", pady=6)
        
        # Options
        self.truncate_var = tk.BooleanVar(value=True)
        self.chk_truncate = ttk.Checkbutton(opts_card, text="Truncate existing tables before import", variable=self.truncate_var)
        self.chk_truncate.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 4))
        
        self.create_tables_var = tk.BooleanVar(value=True)
        self.chk_create_tables = ttk.Checkbutton(opts_card, text="Create tables automatically if missing", variable=self.create_tables_var)
        self.chk_create_tables.grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        
        # Dependency card if missing pymysql
        self.dep_card = ttk.Frame(left_panel, padding=10, style="Card.TFrame")
        if not db_library:
            self.show_dependency_installer()
            
        # Right Panel: Operations Logs & Progress
        right_panel = ttk.Frame(import_tab, padding=(10, 0, 0, 0))
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)
        
        log_title = ttk.Label(right_panel, text="EXECUTION LOG & PROGRESS", font=("Segoe UI Semibold", 11))
        log_title.grid(row=0, column=0, sticky="w", pady=(0, 8))
        
        # Scrolled Text for Logs
        self.log_area = ScrolledText(
            right_panel, 
            bg="#18181b", 
            fg=self.text_color, 
            insertbackground=self.text_color,
            font=("Consolas", 10), 
            bd=0, 
            highlightthickness=1, 
            highlightcolor=self.border_color,
            highlightbackground=self.border_color,
            padx=10,
            pady=10
        )
        self.log_area.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        
        # Progress info
        self.progress_label = ttk.Label(right_panel, text="Progress: Ready", style="Sub.TLabel")
        self.progress_label.grid(row=2, column=0, sticky="w", pady=(0, 4))
        
        self.progress_bar = ttk.Progressbar(right_panel, mode="determinate", style="Custom.Horizontal.TProgressbar")
        self.progress_bar.grid(row=3, column=0, sticky="ew", pady=(0, 15))
        
        # Main action button
        self.btn_start = ttk.Button(right_panel, text="Start Extraction & Import", command=self.start_import)
        self.btn_start.grid(row=4, column=0, sticky="ew")

        # Layout Tab 2: Search Pincode
        # 1. Search Box Header
        search_box = ttk.Frame(search_tab, padding=12, style="Card.TFrame")
        search_box.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        search_box.columnconfigure(1, weight=1)
        
        ttk.Label(search_box, text="Enter Pincode:", style="Card.TLabel", font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w", padx=(5, 10))
        self.search_entry = ttk.Entry(search_box, font=("Segoe UI", 11))
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self.search_entry.bind("<Return>", lambda e: self.perform_search())
        
        self.btn_search = ttk.Button(search_box, text="Search Database", command=self.perform_search)
        self.btn_search.grid(row=0, column=2, sticky="e", padx=(0, 5))
        
        # 2. Search Status Text
        self.search_status = ttk.Label(search_tab, text="Enter a pincode to query details...", style="Sub.TLabel")
        self.search_status.grid(row=1, column=0, sticky="w", pady=(0, 6))
        
        # 3. Treeview results list
        tree_container = ttk.Frame(search_tab)
        tree_container.grid(row=2, column=0, sticky="nsew")
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)
        
        columns = ("office_name", "pincode", "type", "delivery", "taluk", "district", "state")
        self.search_tree = ttk.Treeview(tree_container, columns=columns, show="headings", style="Treeview")
        self.search_tree.grid(row=0, column=0, sticky="nsew")
        
        # Configure headings
        self.search_tree.heading("office_name", text="Post Office Name")
        self.search_tree.heading("pincode", text="Pincode")
        self.search_tree.heading("type", text="Office Type")
        self.search_tree.heading("delivery", text="Delivery Status")
        self.search_tree.heading("taluk", text="Taluk")
        self.search_tree.heading("district", text="District")
        self.search_tree.heading("state", text="State")
        
        # Configure column sizes
        self.search_tree.column("office_name", width=180, minwidth=150)
        self.search_tree.column("pincode", width=80, minwidth=70, anchor="center")
        self.search_tree.column("type", width=90, minwidth=80, anchor="center")
        self.search_tree.column("delivery", width=110, minwidth=90, anchor="center")
        self.search_tree.column("taluk", width=120, minwidth=100)
        self.search_tree.column("district", width=130, minwidth=110)
        self.search_tree.column("state", width=130, minwidth=110)
        
        # Scrollbar
        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.search_tree.yview)
        self.search_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        
        self.search_tree.bind("<<TreeviewSelect>>", self.on_search_select)
        
        self.search_tree.tag_configure("even", background="#FFFFFF", foreground="#111111")
        self.search_tree.tag_configure("odd", background="#EAF2FF", foreground="#111111")
        # 4. Detailed Card View at bottom
        self.detail_card = ttk.Frame(search_tab, padding=15, style="Card.TFrame")
        self.detail_card.grid(row=3, column=0, sticky="ew", pady=(15, 0))
        self.detail_card.columnconfigure((0, 1, 2, 3), weight=1)
        
        self.lbl_circle = self.create_detail_item(self.detail_card, "Circle:", "-", 0, 0)
        self.lbl_region = self.create_detail_item(self.detail_card, "Region:", "-", 0, 1)
        self.lbl_division = self.create_detail_item(self.detail_card, "Division:", "-", 0, 2)
        self.lbl_contact = self.create_detail_item(self.detail_card, "Contact Number:", "-", 0, 3)
        
        self.lbl_lat = self.create_detail_item(self.detail_card, "Latitude:", "-", 1, 0)
        self.lbl_lon = self.create_detail_item(self.detail_card, "Longitude:", "-", 1, 1)
        self.lbl_gps = self.create_detail_item(self.detail_card, "Maps Link:", "No Coordinates Available", 1, 2)

    def show_dependency_installer(self):
        self.dep_card.grid(row=2, column=0, sticky="ew", pady=(15, 0))
        self.dep_card.columnconfigure(0, weight=1)
        
        lbl_info = ttk.Label(self.dep_card, text="Neither 'pymysql' nor 'mysql-connector-python' is installed.\nYou need one of them to connect to MySQL/MariaDB.", style="Card.TLabel", foreground=self.error_color)
        lbl_info.grid(row=0, column=0, sticky="w", pady=(0, 8))
        
        self.btn_install = ttk.Button(self.dep_card, text="Auto-Install PyMySQL via pip", command=self.install_dependency)
        self.btn_install.grid(row=1, column=0, sticky="ew")

    def detect_default_csv(self):
        default_name = "all-india-pincode-html-csv-Ver-2026.csv"
        # Search in current script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        potential_path = os.path.join(script_dir, default_name)
        if os.path.exists(potential_path):
            self.csv_path.insert(0, potential_path)
            self.log(f"Auto-detected CSV file: {default_name}")
        else:
            # Check current working directory
            cwd_path = os.path.join(os.getcwd(), default_name)
            if os.path.exists(cwd_path):
                self.csv_path.insert(0, cwd_path)
                self.log(f"Auto-detected CSV file: {default_name}")
            else:
                self.log("Pincode CSV not found in workspace. Please select it manually.", is_error=True)

    def browse_csv(self):
        filepath = filedialog.askopenfilename(
            title="Select Pincode CSV File",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if filepath:
            self.csv_path.delete(0, tk.END)
            self.csv_path.insert(0, filepath)
            self.log(f"Selected CSV file: {os.path.basename(filepath)}")

    def log(self, message, is_error=False, is_success=False):
        timestamp = time.strftime("[%H:%M:%S] ")
        self.log_queue.put((timestamp + message + "\n", is_error, is_success))

    def process_logs(self):
        while not self.log_queue.empty():
            msg, is_error, is_success = self.log_queue.get()
            self.log_area.configure(state='normal')
            
            # Setup tags
            self.log_area.tag_config("error", foreground=self.error_color)
            self.log_area.tag_config("success", foreground=self.success_color)
            
            if is_error:
                self.log_area.insert(tk.END, msg, "error")
            elif is_success:
                self.log_area.insert(tk.END, msg, "success")
            else:
                self.log_area.insert(tk.END, msg)
                
            self.log_area.see(tk.END)
            self.log_area.configure(state='disabled')
            
        self.root.after(100, self.process_logs)

    def get_db_connection(self):
        host = self.db_host.get().strip()
        port = int(self.db_port.get().strip())
        user = self.db_user.get().strip()
        password = self.db_pass.get()
        database = self.db_name.get().strip()
        
        global db_library
        if db_library == "pymysql":
            return pymysql.connect(
                host=host, port=port, user=user, password=password, database=database,
                charset='utf8mb4', cursorclass=pymysql.cursors.Cursor
            )
        elif db_library == "mysql.connector":
            return mysql.connector.connect(
                host=host, port=port, user=user, password=password, database=database,
                charset='utf8mb4'
            )
        else:
            raise ImportError("No MySQL drivers available. Please install 'pymysql'.")

    def test_connection(self):
        def worker():
            self.log("Testing connection to database...")
            try:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()
                self.log(f"Connection successful! MySQL Server Version: {version[0]}", is_success=True)
                cursor.close()
                conn.close()
            except Exception as e:
                self.log(f"Connection failed: {str(e)}", is_error=True)
                
        threading.Thread(target=worker, daemon=True).start()

    def install_dependency(self):
        self.btn_install.configure(state="disabled", text="Installing...")
        self.log("Running 'pip install pymysql' in background...")
        
        def worker():
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pymysql"])
                global db_library
                import pymysql
                db_library = "pymysql"
                self.log("pymysql successfully installed!", is_success=True)
                
                # Update UI thread
                self.root.after(0, self.on_install_success)
            except Exception as e:
                self.log(f"Failed to install pymysql: {str(e)}", is_error=True)
                self.root.after(0, lambda: self.btn_install.configure(state="normal", text="Auto-Install PyMySQL via pip"))

        threading.Thread(target=worker, daemon=True).start()

    def on_install_success(self):
        self.dep_card.grid_forget()
        self.update_driver_badge()

    def start_import(self):
        if self.import_running:
            return
            
        csv_file = self.csv_path.get().strip()
        if not csv_file or not os.path.exists(csv_file):
            messagebox.showerror("Error", "CSV file not found! Please select a valid file.")
            return
            
        if not db_library:
            messagebox.showerror("Error", "No MySQL driver installed. Install 'pymysql' first.")
            return
            
        self.import_running = True
        self.btn_start.configure(state="disabled", text="Importing Data... Please Wait")
        self.btn_test.configure(state="disabled")
        self.progress_bar["value"] = 0
        
        threading.Thread(target=self.import_worker, args=(csv_file,), daemon=True).start()

    def import_worker(self, csv_file_path):
        conn = None
        try:
            start_time = time.time()
            self.log("Establishing database connection...")
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Disable autocommit for fast bulk inserts
            conn.autocommit = False
            
            if self.create_tables_var.get():
                self.log("Checking and creating necessary tables...")
                self.create_tables_if_missing(cursor)
                conn.commit()
                
            if self.truncate_var.get():
                self.log("Truncating existing tables to avoid duplicates...")
                # Order matters due to foreign keys if present, but since there are none, we can truncate cleanly
                tables = [
                    "app_post_offices", "app_postoffices", 
                    "app_postal_division", "app_postal_region", "app_postal_circle",
                    "app_post_office_type", "app_postal_delivery_status"
                ]
                # Try truncating. If tables don't exist yet, ignore
                for table in tables:
                    try:
                        cursor.execute(f"TRUNCATE TABLE `{table}`")
                    except Exception:
                        pass
                conn.commit()
                self.log("Tables truncated successfully.")

            # Stage 1: Read CSV into memory & extract unique relational items
            self.log("Phase 1: Scanning CSV file and extracting unique entities...")
            self.progress_label.configure(text="Progress: Scanning CSV...")
            
            # Quantify lines
            with open(csv_file_path, mode='r', encoding='utf-8') as f:
                total_rows = sum(1 for _ in f) - 1 # exclude header
            
            self.log(f"Found {total_rows:,} records in CSV. Loading data...")
            
            circles = set()
            states = set()
            districts = set()     # Set of (state_name, district_name)
            office_types = set()
            delivery_statuses = set()
            regions = set()       # Set of (circle_name, region_name)
            divisions = set()     # Set of (circle_name, region_name, division_name)
            
            raw_rows = []
            
            with open(csv_file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Clean and standardize string data
                    c_name = row['circlename'].strip()
                    r_name = row['regionname'].strip()
                    d_name = row['divisionname'].strip()
                    o_name = row['officename'].strip()
                    pincode = row['pincode'].strip()
                    o_type = row['officetype'].strip()
                    delivery = row['delivery'].strip()
                    dist = row['district'].strip()
                    state = row['statename'].strip()
                    lat = row['latitude'].strip()
                    lon = row['longitude'].strip()
                    
                    circles.add(c_name)
                    states.add(state)
                    districts.add((state, dist))
                    office_types.add(o_type)
                    delivery_statuses.add(delivery)
                    regions.add((c_name, r_name))
                    divisions.add((c_name, r_name, d_name))
                    
                    raw_rows.append({
                        'circle': c_name, 'region': r_name, 'division': d_name,
                        'office_name': o_name, 'pincode': pincode, 'office_type': o_type,
                        'delivery': delivery, 'district': dist, 'state': state,
                        'latitude': None if lat in ('NA', '', 'NULL') else lat,
                        'longitude': None if lon in ('NA', '', 'NULL') else lon
                    })

            self.log("Unique entities extracted:")
            self.log(f" - Circles: {len(circles)}")
            self.log(f" - Regions: {len(regions)}")
            self.log(f" - Divisions: {len(divisions)}")
            self.log(f" - States: {len(states)}")
            self.log(f" - Districts: {len(districts)}")
            self.log(f" - Office Types: {len(office_types)}")
            self.log(f" - Delivery Statuses: {len(delivery_statuses)}")
            
            # Phase 2: Insert unique entities and cache IDs
            self.log("Phase 2: Inserting relational master data...")
            self.progress_label.configure(text="Progress: Inserting lookup tables...")
            


            # Check if database has plural tables (app_states, app_districts, app_taluks) 
            # or singular tables (app_state, app_district, app_taluk)
            cursor.execute("SHOW TABLES LIKE 'app_states'")
            has_plural_states = cursor.fetchone() is not None
            state_table = "app_states" if has_plural_states else "app_state"

            cursor.execute("SHOW TABLES LIKE 'app_districts'")
            has_plural_districts = cursor.fetchone() is not None
            district_table = "app_districts" if has_plural_districts else "app_district"

            cursor.execute("SHOW TABLES LIKE 'app_taluks'")
            has_plural_taluks = cursor.fetchone() is not None
            taluk_table = "app_taluks" if has_plural_taluks else "app_taluk"

            # Determine column names dynamically
            state_cols = self.inspect_table_schema(cursor, state_table)
            state_name_col = next((c for c in ["state_name", "name", "state", "statename"] if c in state_cols), None)
            if not state_name_col and state_cols:
                state_name_col = [c for c in state_cols if c != "id"][0]

            dist_cols = self.inspect_table_schema(cursor, district_table)
            dist_name_col = next((c for c in ["district_name", "name", "district", "districtname"] if c in dist_cols), None)
            if not dist_name_col and dist_cols:
                dist_name_col = [c for c in dist_cols if c != "id" and "state" not in c][0]
            dist_state_col = next((c for c in ["state_id", "state"] if c in dist_cols), None)

            taluk_cols = self.inspect_table_schema(cursor, taluk_table)
            taluk_name_col = next((c for c in ["taluk_name", "name", "taluk", "talukname"] if c in taluk_cols), None)
            if not taluk_name_col and taluk_cols:
                taluk_name_col = [c for c in taluk_cols if c != "id" and "district" not in c and "state" not in c][0]
            taluk_dist_col = next((c for c in ["district_id", "district"] if c in taluk_cols), None)
            taluk_state_col = next((c for c in ["state_id", "state"] if c in taluk_cols), None)

            # Load existing States
            state_cache = {}
            if state_name_col:
                self.log(f"Reading existing states from `{state_table}`...")
                cursor.execute(f"SELECT `id`, `{state_name_col}` FROM `{state_table}`")
                for row in cursor.fetchall():
                    if row[1]:
                        state_cache[row[1].lower().strip()] = row[0]

            # Load existing Districts
            district_cache = {}
            if dist_name_col:
                self.log(f"Reading existing districts from `{district_table}`...")
                if dist_state_col:
                    cursor.execute(f"SELECT `id`, `{dist_name_col}`, `{dist_state_col}` FROM `{district_table}`")
                    for row in cursor.fetchall():
                        if row[1]:
                            district_cache[(row[2], row[1].lower().strip())] = row[0]
                else:
                    cursor.execute(f"SELECT `id`, `{dist_name_col}` FROM `{district_table}`")
                    for row in cursor.fetchall():
                        if row[1]:
                            district_cache[row[1].lower().strip()] = row[0]

            # Load existing Taluks
            district_to_taluks = {}
            if taluk_name_col:
                self.log(f"Reading existing taluks from `{taluk_table}`...")
                if taluk_dist_col:
                    cursor.execute(f"SELECT `id`, `{taluk_dist_col}` FROM `{taluk_table}`")
                    for row in cursor.fetchall():
                        dt_id = row[1]
                        if dt_id not in district_to_taluks:
                            district_to_taluks[dt_id] = []
                        district_to_taluks[dt_id].append(row[0])

            # Resolve country_id if country_id is present in state, district, or taluk tables
            country_id = 1
            if "country_id" in state_cols or "country_id" in dist_cols or "country_id" in taluk_cols:
                # Check if app_countries or app_country exists
                cursor.execute("SHOW TABLES LIKE 'app_countries'")
                has_plural_countries = cursor.fetchone() is not None
                cursor.execute("SHOW TABLES LIKE 'app_country'")
                has_singular_countries = cursor.fetchone() is not None
                
                country_table = "app_countries" if has_plural_countries else ("app_country" if has_singular_countries else None)
                
                if country_table:
                    try:
                        cursor.execute(f"SELECT * FROM `{country_table}` LIMIT 1")
                        country_cols = [desc[0].lower() for desc in cursor.description]
                        name_col = next((c for c in ["country_name", "name", "country"] if c in country_cols), None)
                        if name_col:
                            cursor.execute(f"SELECT `id` FROM `{country_table}` WHERE `{name_col}` LIKE %s", ('%India%',))
                            row = cursor.fetchone()
                            if row:
                                country_id = row[0]
                            else:
                                cursor.execute(f"SELECT `id` FROM `{country_table}` LIMIT 1")
                                row = cursor.fetchone()
                                if row:
                                    country_id = row[0]
                        else:
                            cursor.execute(f"SELECT `id` FROM `{country_table}` LIMIT 1")
                            row = cursor.fetchone()
                            if row:
                                country_id = row[0]
                    except Exception as ex:
                        self.log(f"Warning: Could not fetch country_id from {country_table}: {ex}")

            # Populate missing States, Districts, and Taluks while generating the mappings
            # 1. State
            for st in sorted(states):
                st_lower = st.lower().strip()
                if st_lower not in state_cache:
                    if "country_id" in state_cols:
                        cursor.execute(f"INSERT INTO `{state_table}` (`{state_name_col}`, `country_id`) VALUES (%s, %s)", (st, country_id))
                    else:
                        cursor.execute(f"INSERT INTO `{state_table}` (`{state_name_col}`) VALUES (%s)", (st,))
                    st_id = cursor.lastrowid
                    state_cache[st_lower] = st_id

            # 2. District & Taluk mapping
            taluk_cache = {} # maps district_id -> taluk_id
            for st, dt in sorted(districts):
                st_id = state_cache[st.lower().strip()]
                dt_lower = dt.lower().strip()
                key = (st_id, dt_lower) if dist_state_col else dt_lower

                if key not in district_cache:
                    if dist_state_col:
                        if "country_id" in dist_cols:
                            cursor.execute(f"INSERT INTO `{district_table}` (`{dist_name_col}`, `{dist_state_col}`, `country_id`) VALUES (%s, %s, %s)", (dt, st_id, country_id))
                        else:
                            cursor.execute(f"INSERT INTO `{district_table}` (`{dist_name_col}`, `{dist_state_col}`) VALUES (%s, %s)", (dt, st_id))
                    else:
                        if "country_id" in dist_cols:
                            cursor.execute(f"INSERT INTO `{district_table}` (`{dist_name_col}`, `country_id`) VALUES (%s, %s)", (dt, country_id))
                        else:
                            cursor.execute(f"INSERT INTO `{district_table}` (`{dist_name_col}`) VALUES (%s)", (dt,))
                    dt_id = cursor.lastrowid
                    district_cache[key] = dt_id
                else:
                    dt_id = district_cache[key]

                # Dynamic Taluk parent-child mapping
                if dt_id in district_to_taluks and district_to_taluks[dt_id]:
                    taluk_id = district_to_taluks[dt_id][0]
                else:
                    # No taluk for this district, insert NA
                    if taluk_dist_col:
                        if taluk_state_col:
                            if "country_id" in taluk_cols:
                                cursor.execute(f"INSERT INTO `{taluk_table}` (`{taluk_name_col}`, `{taluk_dist_col}`, `{taluk_state_col}`, `country_id`) VALUES (%s, %s, %s, %s)", ("NA", dt_id, st_id, country_id))
                            else:
                                cursor.execute(f"INSERT INTO `{taluk_table}` (`{taluk_name_col}`, `{taluk_dist_col}`, `{taluk_state_col}`) VALUES (%s, %s, %s)", ("NA", dt_id, st_id))
                        else:
                            if "country_id" in taluk_cols:
                                cursor.execute(f"INSERT INTO `{taluk_table}` (`{taluk_name_col}`, `{taluk_dist_col}`, `country_id`) VALUES (%s, %s, %s)", ("NA", dt_id, country_id))
                            else:
                                cursor.execute(f"INSERT INTO `{taluk_table}` (`{taluk_name_col}`, `{taluk_dist_col}`) VALUES (%s, %s)", ("NA", dt_id))
                    else:
                        if "country_id" in taluk_cols:
                            cursor.execute(f"INSERT INTO `{taluk_table}` (`{taluk_name_col}`, `country_id`) VALUES (%s, %s)", ("NA", country_id))
                        else:
                            cursor.execute(f"INSERT INTO `{taluk_table}` (`{taluk_name_col}`) VALUES (%s)", ("NA",))
                    taluk_id = cursor.lastrowid
                    if dt_id not in district_to_taluks:
                        district_to_taluks[dt_id] = []
                    district_to_taluks[dt_id].append(taluk_id)

                taluk_cache[dt_id] = taluk_id
                
            # 3. Post Office Types
            type_cache = {}
            for ot in sorted(office_types):
                cursor.execute("INSERT INTO `app_post_office_type` (`office_type`) VALUES (%s)", (ot,))
                type_cache[ot] = cursor.lastrowid
                
            # 4. Delivery Statuses
            status_cache = {}
            for ds in sorted(delivery_statuses):
                cursor.execute("INSERT INTO `app_postal_delivery_status` (`delivery_status`) VALUES (%s)", (ds,))
                status_cache[ds] = cursor.lastrowid
                
            # 5. Postal Circles
            circle_cache = {}
            for cc in sorted(circles):
                cursor.execute("INSERT INTO `app_postal_circle` (`circle_name`) VALUES (%s)", (cc,))
                circle_cache[cc] = cursor.lastrowid
                
            # 6. Postal Regions (Needs circle_id)
            region_cache = {}
            for cc, rg in sorted(regions):
                cc_id = circle_cache[cc]
                cursor.execute(
                    "INSERT INTO `app_postal_region` (`circle_id`, `region_name`) VALUES (%s, %s)", 
                    (cc_id, rg)
                )
                region_cache[(cc, rg)] = cursor.lastrowid
                
            # 7. Postal Divisions (Needs circle_id, region_id)
            division_cache = {}
            for cc, rg, dv in sorted(divisions):
                cc_id = circle_cache[cc]
                rg_id = region_cache[(cc, rg)]
                cursor.execute(
                    "INSERT INTO `app_postal_division` (`circle_id`, `region_id`, `division_name`) VALUES (%s, %s, %s)", 
                    (cc_id, rg_id, dv)
                )
                division_cache[(cc, rg, dv)] = cursor.lastrowid
                
            conn.commit()
            self.log("Relational master data successfully inserted & cached.", is_success=True)
            
            # Phase 3: Insert Post Offices in Batches
            self.log("Phase 3: Inserting post offices in bulk...")
            
            sql_post_offices = """
                INSERT INTO `app_post_offices` (
                    `post_office_name`, `pin_code`, `post_office_type_id`, 
                    `postal_delivery_status_id`, `postal_division_id`, `postal_region_id`, 
                    `postal_circle_id`, `taluk_id`, `district_id`, `state_id`, 
                    `contact_number`, `latitude`, `longitude`
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            sql_postoffices_legacy = """
                INSERT INTO `app_postoffices` (
                    `post_office_name`, `pin_code`, `taluk_id`, `district_id`, `state_id`
                ) VALUES (%s, %s, %s, %s, %s)
            """
            
            batch_offices = []
            batch_offices_legacy = []
            batch_size = 2000
            inserted_count = 0
            
            for idx, r in enumerate(raw_rows):
                # Retrieve IDs from caches
                circle_id = circle_cache[r['circle']]
                region_id = region_cache[(r['circle'], r['region'])]
                division_id = division_cache[(r['circle'], r['region'], r['division'])]
                type_id = type_cache[r['office_type']]
                status_id = status_cache[r['delivery']]
                state_id = state_cache[r['state'].lower().strip()]
                dt_lower = r['district'].lower().strip()
                key = (state_id, dt_lower) if dist_state_col else dt_lower
                district_id = district_cache[key]
                taluk_id = taluk_cache[district_id]
                
                # app_post_offices details
                batch_offices.append((
                    r['office_name'], r['pincode'], type_id, status_id, division_id,
                    region_id, circle_id, taluk_id, district_id, state_id,
                    None, r['latitude'], r['longitude'] # contact number is default None
                ))
                
                # app_postoffices details
                batch_offices_legacy.append((
                    r['office_name'], r['pincode'], taluk_id, district_id, state_id
                ))
                
                # Exec batch insert
                if len(batch_offices) >= batch_size:
                    cursor.executemany(sql_post_offices, batch_offices)
                    cursor.executemany(sql_postoffices_legacy, batch_offices_legacy)
                    conn.commit()
                    inserted_count += len(batch_offices)
                    
                    batch_offices = []
                    batch_offices_legacy = []
                    
                    # Update progress
                    percent = (inserted_count / total_rows) * 100
                    self.update_progress(percent, f"Progress: Imported {inserted_count:,} / {total_rows:,} records")
            
            # Final remaining batch
            if batch_offices:
                cursor.executemany(sql_post_offices, batch_offices)
                cursor.executemany(sql_postoffices_legacy, batch_offices_legacy)
                conn.commit()
                inserted_count += len(batch_offices)
                
            self.update_progress(100, f"Progress: Completed {inserted_count:,} records!")
            
            elapsed = time.time() - start_time
            speed = inserted_count / elapsed if elapsed > 0 else inserted_count
            
            self.log("----------------------------------------", is_success=True)
            self.log(f"SUCCESS: Import completed successfully!", is_success=True)
            self.log(f"Total Records Imported: {inserted_count:,}", is_success=True)
            self.log(f"Elapsed Time: {elapsed:.2f} seconds", is_success=True)
            self.log(f"Average Import Speed: {speed:.1f} records/second", is_success=True)
            self.log("----------------------------------------", is_success=True)
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            self.log(f"ERROR OCCURRED during import: {str(e)}", is_error=True)
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
        finally:
            self.import_running = False
            self.root.after(0, self.reset_buttons)

    def update_progress(self, percent, text):
        self.root.after(0, lambda: self._ui_update_progress(percent, text))

    def _ui_update_progress(self, percent, text):
        self.progress_bar["value"] = percent
        self.progress_label.configure(text=text)

    def reset_buttons(self):
        self.btn_start.configure(state="normal", text="Start Extraction & Import")
        self.btn_test.configure(state="normal")

    def create_tables_if_missing(self, cursor):
        # Definitions matching user's pin_code.sql table definitions and Django conventions
        queries = [
            """
            CREATE TABLE IF NOT EXISTS `app_postal_circle` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `circle_name` varchar(50) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_postal_region` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `circle_id` int(11) NOT NULL,
              `region_name` varchar(50) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_postal_division` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `circle_id` int(11) NOT NULL,
              `region_id` int(11) NOT NULL,
              `division_name` varchar(50) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_post_office_type` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `office_type` varchar(50) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_postal_delivery_status` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `delivery_status` varchar(50) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_state` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `state_name` varchar(100) NOT NULL UNIQUE,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_district` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `district_name` varchar(100) NOT NULL,
              `state_id` int(11) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_taluk` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `taluk_name` varchar(100) NOT NULL,
              `district_id` int(11) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_post_offices` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `post_office_name` varchar(255) NOT NULL,
              `pin_code` varchar(20) NOT NULL,
              `post_office_type_id` int(11) NOT NULL,
              `postal_delivery_status_id` int(11) NOT NULL,
              `postal_division_id` int(11) NOT NULL,
              `postal_region_id` int(11) NOT NULL,
              `postal_circle_id` int(11) NOT NULL,
              `taluk_id` int(11) NOT NULL,
              `district_id` int(11) NOT NULL,
              `state_id` int(11) NOT NULL,
              `contact_number` varchar(50) DEFAULT NULL,
              `latitude` varchar(50) DEFAULT NULL,
              `longitude` varchar(50) DEFAULT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS `app_postoffices` (
              `id` int(11) NOT NULL AUTO_INCREMENT,
              `post_office_name` varchar(255) NOT NULL,
              `pin_code` varchar(20) NOT NULL,
              `taluk_id` int(11) NOT NULL,
              `district_id` int(11) NOT NULL,
              `state_id` int(11) NOT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """
        ]
        
        for q in queries:
            cursor.execute(q)

    def inspect_table_schema(self, cur, table_name):
        try:
            cur.execute(f"SELECT * FROM `{table_name}` LIMIT 1")
            return [desc[0].lower() for desc in cur.description]
        except Exception:
            return []

    def create_detail_item(self, parent, label_text, default_val, row, col):
        container = ttk.Frame(parent, style="Card.TFrame")
        container.grid(row=row, column=col, sticky="w", padx=10, pady=5)
        
        lbl_title = ttk.Label(container, text=label_text, style="Card.TLabel", font=("Segoe UI Semibold", 8), foreground=self.accent_color)
        lbl_title.grid(row=0, column=0, sticky="w")
        
        lbl_val = ttk.Label(container, text=default_val, style="Card.TLabel", font=("Segoe UI", 10))
        lbl_val.grid(row=1, column=0, sticky="w")
        return lbl_val

    def perform_search(self):
        pincode = self.search_entry.get().strip()
        if not pincode:
            messagebox.showwarning("Warning", "Please enter a pincode to search.")
            return
            
        # Clear previous items
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
            
        # Clear detail panel
        self.lbl_circle.configure(text="-")
        self.lbl_region.configure(text="-")
        self.lbl_division.configure(text="-")
        self.lbl_contact.configure(text="-")
        self.lbl_lat.configure(text="-")
        self.lbl_lon.configure(text="-")
        self.lbl_gps.configure(text="No Coordinates Available", cursor="", foreground=self.text_color)
        self.lbl_gps.unbind("<Button-1>")
        
        self.search_status.configure(text="Searching database...")
        
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Inspect tables dynamically to check plural/singular and columns
            cursor.execute("SHOW TABLES LIKE 'app_states'")
            has_plural_states = cursor.fetchone() is not None
            state_table = "app_states" if has_plural_states else "app_state"

            cursor.execute("SHOW TABLES LIKE 'app_districts'")
            has_plural_districts = cursor.fetchone() is not None
            district_table = "app_districts" if has_plural_districts else "app_district"

            cursor.execute("SHOW TABLES LIKE 'app_taluks'")
            has_plural_taluks = cursor.fetchone() is not None
            taluk_table = "app_taluks" if has_plural_taluks else "app_taluk"
            
            # Get table columns
            state_cols = self.inspect_table_schema(cursor, state_table)
            state_name_col = next((c for c in ["state_name", "name", "state", "statename"] if c in state_cols), "state_name")
            
            dist_cols = self.inspect_table_schema(cursor, district_table)
            dist_name_col = next((c for c in ["district_name", "name", "district", "districtname"] if c in dist_cols), "district_name")
            
            taluk_cols = self.inspect_table_schema(cursor, taluk_table)
            taluk_name_col = next((c for c in ["taluk_name", "name", "taluk", "talukname"] if c in taluk_cols), "taluk_name")
            
            # Dynamic JOIN query
            query = f"""
                SELECT 
                    po.post_office_name,
                    po.pin_code,
                    ot.office_type,
                    ds.delivery_status,
                    pdiv.division_name,
                    reg.region_name,
                    cir.circle_name,
                    t.`{taluk_name_col}` AS taluk_name,
                    d.`{dist_name_col}` AS district_name,
                    s.`{state_name_col}` AS state_name,
                    po.contact_number,
                    po.latitude,
                    po.longitude
                FROM `app_post_offices` po
                LEFT JOIN `app_post_office_type` ot ON po.post_office_type_id = ot.id
                LEFT JOIN `app_postal_delivery_status` ds ON po.postal_delivery_status_id = ds.id
                LEFT JOIN `app_postal_division` pdiv ON po.postal_division_id = pdiv.id
                LEFT JOIN `app_postal_region` reg ON po.postal_region_id = reg.id
                LEFT JOIN `app_postal_circle` cir ON po.postal_circle_id = cir.id
                LEFT JOIN `{state_table}` s ON po.state_id = s.id
                LEFT JOIN `{district_table}` d ON po.district_id = d.id
                LEFT JOIN `{taluk_table}` t ON po.taluk_id = t.id
                WHERE po.pin_code = %s
            """
            
            cursor.execute(query, (pincode,))
            rows = cursor.fetchall()
            
            self.search_results_data = {} # Maps item ID in tree to full details
            
            for idx, row in enumerate(rows):
                po_name, pin, p_type, delivery, division, region, circle, taluk, district, state, contact, lat, lon = row
                
                # Check for None values and convert to string representation
                contact = contact if contact else "NA"
                lat_str = lat if lat else "NA"
                lon_str = lon if lon else "NA"
                
                # Insert to tree with tags for high contrast readability
                tag = "even" if idx % 2 == 0 else "odd"
                item_id = self.search_tree.insert("", tk.END, values=(
                    po_name, pin, p_type, delivery, taluk, district, state
                ), tags=(tag,))
                
                # Cache full details for click handler
                self.search_results_data[item_id] = {
                    'circle': circle,
                    'region': region,
                    'division': division,
                    'contact': contact,
                    'latitude': lat_str,
                    'longitude': lon_str
                }
                
            count = len(rows)
            if count > 0:
                self.search_status.configure(text=f"Found {count} matching records in database.", foreground=self.success_color)
            else:
                self.search_status.configure(text="No matching records found for this pincode.", foreground=self.error_color)
                
            cursor.close()
            conn.close()
            
        except Exception as e:
            err_msg = f"Database query error: {str(e)}"
            self.search_status.configure(text=err_msg, foreground=self.error_color)
            # Log the query to the execution logs to inspect the SQL syntax
            self.log("--- SEARCH DATABASE ERROR ---", is_error=True)
            self.log(err_msg, is_error=True)
            try:
                self.log(f"Generated Query:\n{query}\nParameters: pincode={pincode}", is_error=True)
            except NameError:
                pass

    def on_search_select(self, event):
        selected = self.search_tree.selection()
        if not selected:
            return
            
        item_id = selected[0]
        data = self.search_results_data.get(item_id)
        if not data:
            return
            
        self.lbl_circle.configure(text=data['circle'] if data['circle'] else "NA")
        self.lbl_region.configure(text=data['region'] if data['region'] else "NA")
        self.lbl_division.configure(text=data['division'] if data['division'] else "NA")
        self.lbl_contact.configure(text=data['contact'])
        
        lat = data['latitude']
        lon = data['longitude']
        self.lbl_lat.configure(text=lat)
        self.lbl_lon.configure(text=lon)
        
        if lat != "NA" and lon != "NA":
            self.lbl_gps.configure(text="Open in Google Maps ↗", cursor="hand2", foreground=self.accent_color)
            self.lbl_gps.bind("<Button-1>", lambda e: self.open_maps(lat, lon))
        else:
            self.lbl_gps.configure(text="No Coordinates Available", cursor="", foreground=self.muted_text)
            self.lbl_gps.unbind("<Button-1>")

    def open_maps(self, lat, lon):
        import webbrowser
        url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        webbrowser.open(url)

if __name__ == "__main__":
    root = tk.Tk()
    app = PincodeImporterApp(root)
    root.mainloop()
