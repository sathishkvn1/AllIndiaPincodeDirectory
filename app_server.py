import os
import sys
import json
import time
import csv
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import pymysql

PORT = 8000
cached_db_config = {
    'host': '',
    'port': 3306,
    'user': '',
    'password': '',
    'database': ''
}

# Thread-safe tracker for background import status
class ImportStatus:
    def __init__(self):
        self.running = False
        self.progress = 0
        self.status_text = "Ready"
        self.logs = []
        self.lock = threading.Lock()

    def log(self, text):
        with self.lock:
            # Prefix logs with a timestamp
            timestamp = time.strftime("[%H:%M:%S]")
            self.logs.append(f"{timestamp} {text}")
            print(f"{timestamp} {text}")

    def set_progress(self, progress, status_text):
        with self.lock:
            self.progress = int(progress)
            self.status_text = status_text

    def reset(self):
        with self.lock:
            self.running = True
            self.progress = 0
            self.status_text = "Starting..."
            self.logs = []

status_tracker = ImportStatus()

def get_db_connection(config):
    return pymysql.connect(
        host=config.get('host', ''),
        port=int(config.get('port', 3306)),
        user=config.get('user', ''),
        password=config.get('password', ''),
        database=config.get('database', ''),
        charset='utf8mb4',
        connect_timeout=6
    )

def inspect_table_schema(cur, table_name):
    try:
        cur.execute(f"SELECT * FROM `{table_name}` LIMIT 1")
        return [desc[0].lower() for desc in cur.description]
    except Exception:
        return []

def import_worker(db_config, csv_path, truncate, create_tables):
    try:
        status_tracker.log("Starting background extraction and import process...")
        
        # 1. Read CSV File and validate
        if not os.path.exists(csv_path):
            status_tracker.log(f"ERROR: CSV file not found at '{csv_path}'")
            status_tracker.set_progress(0, "Error: CSV not found")
            status_tracker.running = False
            return
            
        status_tracker.log(f"Parsing CSV file: {os.path.basename(csv_path)}...")
        status_tracker.set_progress(2, "Parsing CSV...")
        
        states = set()
        districts = set() # set of tuples: (state, district)
        delivery_statuses = set()
        office_types = set()
        circles = set()
        regions = set()
        divisions = set()
        records = []
        
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # Normalize column names by lowercasing and removing spaces
            reader.fieldnames = [name.lower().replace(" ", "").strip() for name in reader.fieldnames]
            
            required_fields = ['officename', 'pincode', 'officetype', 'delivery', 'district', 'statename']
            missing = [f for f in required_fields if f not in reader.fieldnames]
            if missing:
                status_tracker.log(f"ERROR: Missing required columns in CSV: {', '.join(missing)}")
                status_tracker.set_progress(0, "Error: CSV missing columns")
                status_tracker.running = False
                return
                
            for idx, row in enumerate(reader):
                st = row['statename'].strip()
                dt = row['district'].strip()
                ot = row['officetype'].strip()
                ds = row['delivery'].strip()
                circle = row.get('circlename', '').strip()
                region = row.get('regionname', '').strip()
                division = row.get('divisionname', '').strip()
                
                if st: states.add(st)
                if st and dt: districts.add((st, dt))
                if ot: office_types.add(ot)
                if ds: delivery_statuses.add(ds)
                if circle: circles.add(circle)
                if region: regions.add((circle, region))
                if circle and region and division: divisions.add((circle, region, division))
                
                records.append(row)
                
        total_records = len(records)
        status_tracker.log(f"Successfully loaded {total_records} records from CSV.")
        status_tracker.log(f"Found: {len(states)} States, {len(districts)} Districts, {len(office_types)} Office Types, {len(delivery_statuses)} Delivery Statuses.")
        
        # Connect to DB
        status_tracker.set_progress(5, "Connecting to database...")
        conn = get_db_connection(db_config)
        cursor = conn.cursor()
        
        # Helper: Create tables if missing
        if create_tables:
            status_tracker.log("Checking and creating missing database tables...")
            create_tables_if_missing(cursor)
            conn.commit()

        # Helper: Truncate tables if checked
        # Excludes: app_states, app_districts, app_taluks (pre-existing tables requested to not truncate)
        if truncate:
            status_tracker.log("Truncating post office transactional tables...")
            trunc_tables = [
                "app_post_offices", "app_postoffices", "app_post_office_type", 
                "app_postal_delivery_status", "app_postal_division", 
                "app_postal_region", "app_postal_circle"
            ]
            for t in trunc_tables:
                cursor.execute(f"SHOW TABLES LIKE '{t}'")
                if cursor.fetchone():
                    cursor.execute(f"TRUNCATE TABLE `{t}`")
            conn.commit()
            
        # Phase 2: Insert lookup tables and cache IDs
        status_tracker.log("Phase 2: Inserting relational master data...")
        status_tracker.set_progress(10, "Inserting master lookups...")
        
        # Check if database uses plural or singular lookup tables
        cursor.execute("SHOW TABLES LIKE 'app_states'")
        has_plural_states = cursor.fetchone() is not None
        state_table = "app_states" if has_plural_states else "app_state"

        cursor.execute("SHOW TABLES LIKE 'app_districts'")
        has_plural_districts = cursor.fetchone() is not None
        district_table = "app_districts" if has_plural_districts else "app_district"

        cursor.execute("SHOW TABLES LIKE 'app_taluks'")
        has_plural_taluks = cursor.fetchone() is not None
        taluk_table = "app_taluks" if has_plural_taluks else "app_taluk"

        state_cols = inspect_table_schema(cursor, state_table)
        state_name_col = next((c for c in ["state_name", "name", "state", "statename"] if c in state_cols), None)
        if not state_name_col and state_cols:
            state_name_col = [c for c in state_cols if c != "id"][0]

        dist_cols = inspect_table_schema(cursor, district_table)
        dist_name_col = next((c for c in ["district_name", "name", "district", "districtname"] if c in dist_cols), None)
        if not dist_name_col and dist_cols:
            dist_name_col = [c for c in dist_cols if c != "id" and "state" not in c][0]
        dist_state_col = next((c for c in ["state_id", "state"] if c in dist_cols), None)

        taluk_cols = inspect_table_schema(cursor, taluk_table)
        taluk_name_col = next((c for c in ["taluk_name", "name", "taluk", "talukname"] if c in taluk_cols), None)
        if not taluk_name_col and taluk_cols:
            taluk_name_col = [c for c in taluk_cols if c != "id" and "district" not in c and "state" not in c][0]
        taluk_dist_col = next((c for c in ["district_id", "district"] if c in taluk_cols), None)
        taluk_state_col = next((c for c in ["state_id", "state"] if c in taluk_cols), None)

        # Load existing States
        state_cache = {}
        if state_name_col:
            status_tracker.log(f"Reading existing states from `{state_table}`...")
            cursor.execute(f"SELECT `id`, `{state_name_col}` FROM `{state_table}`")
            for row in cursor.fetchall():
                if row[1]:
                    state_cache[row[1].lower().strip()] = row[0]

        # Load existing Districts
        district_cache = {}
        if dist_name_col:
            status_tracker.log(f"Reading existing districts from `{district_table}`...")
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
            status_tracker.log(f"Reading existing taluks from `{taluk_table}`...")
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
                    status_tracker.log(f"Warning: Could not fetch country_id: {ex}")

        # 1. State Insertion
        for st in sorted(states):
            st_lower = st.lower().strip()
            if st_lower not in state_cache:
                if "country_id" in state_cols:
                    cursor.execute(f"INSERT INTO `{state_table}` (`{state_name_col}`, `country_id`) VALUES (%s, %s)", (st, country_id))
                else:
                    cursor.execute(f"INSERT INTO `{state_table}` (`{state_name_col}`) VALUES (%s)", (st,))
                st_id = cursor.lastrowid
                state_cache[st_lower] = st_id

        # 2. District & Taluk Insertion
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

            # Dynamic Taluk lookup or NA default fallback
            if dt_id in district_to_taluks and district_to_taluks[dt_id]:
                taluk_id = district_to_taluks[dt_id][0]
            else:
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

        # 5. Circle / Region / Division hierarchies
        circle_cache = {}
        for cir in sorted(circles):
            cursor.execute("INSERT INTO `app_postal_circle` (`circle_name`) VALUES (%s)", (cir,))
            circle_cache[cir] = cursor.lastrowid

        region_cache = {}
        for cir, reg in sorted(regions):
            cir_id = circle_cache[cir]
            cursor.execute("INSERT INTO `app_postal_region` (`circle_id`, `region_name`) VALUES (%s, %s)", (cir_id, reg))
            region_cache[(cir, reg)] = cursor.lastrowid

        division_cache = {}
        for cir, reg, div in sorted(divisions):
            cir_id = circle_cache[cir]
            reg_id = region_cache[(cir, reg)]
            cursor.execute("INSERT INTO `app_postal_division` (`circle_id`, `region_id`, `division_name`) VALUES (%s, %s, %s)", (cir_id, reg_id, div))
            division_cache[(cir, reg, div)] = cursor.lastrowid

        conn.commit()
        status_tracker.log("Master lookups populated successfully.")
        
        # Check transaction table schema
        cursor.execute("SHOW TABLES LIKE 'app_post_offices'")
        has_post_offices = cursor.fetchone() is not None
        post_office_table = "app_post_offices" if has_post_offices else "app_postoffices"
        po_cols = inspect_table_schema(cursor, post_office_table)

        # Batch transaction inserts (Phase 3)
        status_tracker.log(f"Phase 3: Performing bulk inserts to `{post_office_table}` in batches of 2000...")
        
        batch_size = 2000
        batch_records = []
        
        # Pre-compile the dynamic insert queries
        if post_office_table == "app_post_offices":
            query = """
                INSERT INTO `app_post_offices` (
                    `post_office_name`, `pin_code`, `post_office_type_id`, `postal_delivery_status_id`, 
                    `postal_division_id`, `postal_region_id`, `postal_circle_id`, 
                    `taluk_id`, `district_id`, `state_id`, `contact_number`, `latitude`, `longitude`
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        else:
            query = """
                INSERT INTO `app_postoffices` (
                    `post_office_name`, `pin_code`, `taluk_id`, `district_id`, `state_id`
                ) VALUES (%s, %s, %s, %s, %s)
            """

        for idx, row in enumerate(records):
            po_name = row['officename'].strip()
            pin = row['pincode'].strip()
            ot = row['officetype'].strip()
            ds = row['delivery'].strip()
            dt = row['district'].strip()
            st = row['statename'].strip()
            
            circle = row.get('circlename', '').strip()
            region = row.get('regionname', '').strip()
            division = row.get('divisionname', '').strip()
            
            contact = row.get('telephone', '').strip()
            lat = row.get('latitude', '').strip()
            lon = row.get('longitude', '').strip()
            
            # Look up IDs
            st_id = state_cache[st.lower().strip()]
            
            dt_key = (st_id, dt.lower().strip()) if dist_state_col else dt.lower().strip()
            dt_id = district_cache[dt_key]
            
            taluk_id = district_to_taluks[dt_id][0]
            
            if post_office_table == "app_post_offices":
                ot_id = type_cache[ot]
                ds_id = status_cache[ds]
                cir_id = circle_cache.get(circle, 1)
                reg_id = region_cache.get((circle, region), 1)
                div_id = division_cache.get((circle, region, division), 1)
                
                # Check for empty numeric coordinates
                lat_val = lat if lat else None
                lon_val = lon if lon else None
                
                batch_records.append((
                    po_name, pin, ot_id, ds_id, div_id, reg_id, cir_id, taluk_id, dt_id, st_id, contact, lat_val, lon_val
                ))
            else:
                batch_records.append((
                    po_name, pin, taluk_id, dt_id, st_id
                ))
                
            # Execute batch insert when batch limit is reached
            if len(batch_records) >= batch_size:
                cursor.executemany(query, batch_records)
                conn.commit()
                batch_records = []
                
                # Calculate and update progress
                percent = int(10 + (idx / total_records) * 85)
                status_tracker.set_progress(percent, f"Importing records: {idx}/{total_records} ({percent}%)")
                
        # Insert any remaining records
        if batch_records:
            cursor.executemany(query, batch_records)
            conn.commit()
            
        status_tracker.log("Database transaction completed successfully.")
        status_tracker.set_progress(100, "Import completed successfully.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        status_tracker.log(f"ERROR OCCURRED during import: {e}")
        status_tracker.set_progress(0, f"Error: {e}")
    finally:
        status_tracker.running = False

def create_tables_if_missing(cursor):
    queries = [
        """
        CREATE TABLE IF NOT EXISTS `app_countries` (
          `id` int(11) NOT NULL AUTO_INCREMENT,
          `country_name` varchar(100) NOT NULL,
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

class AppRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Prevent standard HTTP access log outputs in console for readability
        pass

    def send_json(self, data, status=200):
        try:
            body = json.dumps(data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            # CORS headers to make local file testing easy
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"Error sending json: {e}")

    def do_OPTIONS(self):
        # Support CORS pre-flight
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.serve_file('index.html', 'text/html')
        elif self.path.startswith('/api/import-status'):
            self.send_json({
                'running': status_tracker.running,
                'progress': status_tracker.progress,
                'status_text': status_tracker.status_text,
                'logs': status_tracker.logs
            })
        elif self.path.startswith('/api/search'):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            pincode = params.get('pincode', [''])[0].strip()
            
            if not pincode:
                self.send_json({'success': False, 'error': 'No pincode provided'}, status=400)
                return
                
            self.handle_search(pincode)
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
        except Exception:
            self.send_json({'success': False, 'error': 'Invalid JSON'}, status=400)
            return

        if self.path == '/api/test-connection':
            self.handle_test_connection(payload)
        elif self.path == '/api/start-import':
            self.handle_start_import(payload)
        else:
            self.send_error(404, "Endpoint not found")

    def serve_file(self, filename, content_type):
        try:
            if not os.path.exists(filename):
                self.send_error(404, f"File {filename} not found")
                return
            with open(filename, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Internal server error: {e}")

    def handle_test_connection(self, payload):
        try:
            conn = get_db_connection(payload)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            
            # Cache the connection credentials globally on successful test connection!
            global cached_db_config
            cached_db_config = payload
            
            self.send_json({'success': True})
        except Exception as e:
            self.send_json({'success': False, 'error': str(e)})

    def handle_start_import(self, payload):
        global cached_db_config
        db_config = payload.get('db_config', {})
        cached_db_config = db_config
        
        csv_path = payload.get('csv_path', '').strip()
        truncate = payload.get('truncate', True)
        create_tables = payload.get('create_tables', True)
        
        if not csv_path:
            self.send_json({'success': False, 'error': "CSV path cannot be empty!"})
            return
            
        if not os.path.exists(csv_path):
            self.send_json({'success': False, 'error': f"CSV file not found at: {csv_path}"})
            return
            
        if status_tracker.running:
            self.send_json({'success': False, 'error': "An import job is already running!"})
            return
            
        status_tracker.reset()
        thread = threading.Thread(
            target=import_worker,
            args=(db_config, csv_path, truncate, create_tables)
        )
        thread.daemon = True
        thread.start()
        
        self.send_json({'success': True})

    def handle_search(self, pincode):
        global cached_db_config
        try:
            conn = get_db_connection(cached_db_config)
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
            
            state_cols = inspect_table_schema(cursor, state_table)
            state_name_col = next((c for c in ["state_name", "name", "state", "statename"] if c in state_cols), "state_name")
            
            dist_cols = inspect_table_schema(cursor, district_table)
            dist_name_col = next((c for c in ["district_name", "name", "district", "districtname"] if c in dist_cols), "district_name")
            
            taluk_cols = inspect_table_schema(cursor, taluk_table)
            taluk_name_col = next((c for c in ["taluk_name", "name", "taluk", "talukname"] if c in taluk_cols), "taluk_name")
            
            # Dynamic JOIN query (using pdiv instead of reserved 'div')
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
            
            results = []
            for row in rows:
                po_name, pin, p_type, delivery, division, region, circle, taluk, district, state, contact, lat, lon = row
                results.append({
                    'post_office_name': po_name,
                    'pin_code': pin,
                    'office_type': p_type,
                    'delivery_status': delivery,
                    'division_name': division if division else "NA",
                    'region_name': region if region else "NA",
                    'circle_name': circle if circle else "NA",
                    'taluk_name': taluk if taluk else "NA",
                    'district_name': district if district else "NA",
                    'state_name': state if state else "NA",
                    'contact_number': contact if contact else "NA",
                    'latitude': lat if lat else "NA",
                    'longitude': lon if lon else "NA"
                })
                
            cursor.close()
            conn.close()
            self.send_json({'success': True, 'results': results})
        except Exception as e:
            self.send_json({'success': False, 'error': str(e)})

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, AppRequestHandler)
    print(f"Server running at http://localhost:{PORT}")
    
    # Auto-open browser
    def open_browser():
        time.sleep(1)
        webbrowser.open(f"http://localhost:{PORT}")
        
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == '__main__':
    run_server()
