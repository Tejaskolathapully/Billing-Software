import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from tkinter import ttk as tkttk
from tkinter import StringVar, END, Toplevel, VERTICAL, RIGHT, Y, W, E
from tkinter.ttk import Combobox
import random, os, threading, time
import psycopg2
import cv2
from pyzbar import pyzbar

# --- Configuration Constant ---
# Resolve the invoice folder from configuration or use a user-writable default.
INVOICE_DIRECTORY = os.environ.get(
    "INVOICE_DIRECTORY",
    os.path.join(os.path.expanduser("~"), "Downloads", "KTMall", "Invoice"),
)
# ------------------------------

# PostgreSQL connection. Credentials can be supplied through environment variables.
try:
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD"),
        dbname=os.environ.get("PGDATABASE", "KTMall"),
        port=int(os.environ.get("PGPORT", "5432")),
    )
    c = conn.cursor()
except psycopg2.OperationalError as e:
    print(f"Database Connection Error: {e}")
    exit(1)

def info_by_barcode(barcode):
    """Fetches product info by barcode from the database."""
    try:
        global c 
        c.execute("SELECT product_name, category, mrp_inr FROM products WHERE barcode_ean13 = %s", (barcode,))
        return c.fetchone()
    except Exception as e:
        print(f"Database query error in info_by_barcode: {e}")
        return None

class BillApp:
    def __init__(self, root):
        self.root = root
        self.root.title("KTMALL Billing Software")
        self.root.geometry("1350x780+0+0")
        
        self.root.protocol("WM_DELETE_WINDOW", self.exit_program)

        # Initialize variables
        self.bill_total = 0.0
        self.bill_no = str(random.randint(1000, 9999))
        self.customer_name = ttk.StringVar()
        self.customer_phone = ttk.StringVar()
        self.search_bill_number = ttk.StringVar()
        self.manual_name = StringVar()
        self.manual_category = ttk.StringVar()
        self.manual_quantity = ttk.StringVar(value="1")
        self.manual_price = ttk.StringVar()
        self.sr_no = 1

        self.scanning = False
        self.scanning_thread = None
        self.edit_quantity_entry = None
        self.all_product_names = [] 

        # Title Label
        ttk.Label(root, text="KTMALL Billing Software", font=("Segoe UI", 24, "bold"),
                  bootstyle="primary").pack(fill="x", pady=10)

        # Customer Details Frame
        frame = ttk.Labelframe(root, text="Customer Details", bootstyle="info")
        frame.place(x=0, y=80, relwidth=1, height=60)
        
        # Customer Name and Phone
        ttk.Label(frame, text="Customer:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(frame, textvariable=self.customer_name, width=20).grid(row=0, column=1)
        ttk.Label(frame, text="Phone:").grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(frame, textvariable=self.customer_phone, width=15).grid(row=0, column=3)
        
        # Search Bill Elements 
        ttk.Label(frame, text="Search Bill No:").grid(row=0, column=4, padx=(20, 5), pady=5)
        ttk.Entry(frame, textvariable=self.search_bill_number, width=10).grid(row=0, column=5)
        ttk.Button(frame, text="Search Bill", command=self.search_bill, bootstyle="secondary").grid(row=0, column=6, padx=5)

        # Configure columns in frame to ensure spacing
        frame.grid_columnconfigure(7, weight=1)

        # Load products lookup
        self.product_lookup = self.load_products_lookup()
        self.all_product_names = sorted(self.product_lookup.keys()) 

        # Manual Entry Frame
        manualf = ttk.Labelframe(root, text="Add Item Manually", bootstyle="warning")
        manualf.place(x=0, y=145, relwidth=1.25, height=80)

        ttk.Label(manualf, text="Product Name:").grid(row=0, column=0, padx=5, pady=5)
        self.manual_name_combo = Combobox(manualf, textvariable=self.manual_name, width=25)
        
        self.manual_name_combo['values'] = self.all_product_names
        
        self.manual_name_combo.grid(row=0, column=1)
        
        self.manual_name_combo.bind("<KeyRelease>", self.filter_combobox)
        self.manual_name_combo.bind("<<ComboboxSelected>>", self.on_manual_name_selected)

        ttk.Label(manualf, text="Category:").grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(manualf, textvariable=self.manual_category, width=20).grid(row=0, column=3)

        ttk.Label(manualf, text="Quantity:").grid(row=1, column=0, padx=5, pady=5)
        ttk.Entry(manualf, textvariable=self.manual_quantity, width=10).grid(row=1, column=1)

        ttk.Label(manualf, text="Price (₹):").grid(row=1, column=2, padx=5, pady=5)
        ttk.Entry(manualf, textvariable=self.manual_price, width=15).grid(row=1, column=3)

        ttk.Button(manualf, text="Add Item", bootstyle="success", command=self.add_manual_item).grid(row=0, column=4, rowspan=2, padx=10)

        # =========================================================================
        # Bill Summary and Totals Layout 
        # =========================================================================
        billf = ttk.Frame(root)
        billf.place(x=1000, y=230, width=350, height=520) 
        ttk.Label(billf, text="Bill Summary", bootstyle="secondary", font=("Segoe UI", 15, "bold")).pack(fill="x")

        # 1. Treeview Frame
        tree_frame = ttk.Frame(billf)
        tree_frame.pack(fill='x', padx=5, pady=5) 
        
        columns = ("Name", "Category", "Quantity", "Price")
        self.bill_summary = tkttk.Treeview(tree_frame, columns=columns, show="headings", height=20) 
        for col in columns:
            self.bill_summary.heading(col, text=col)
            if col == "Name":
                self.bill_summary.column(col, width=140, anchor='w')
            elif col == "Category":
                self.bill_summary.column(col, width=80, anchor='center')
            elif col == "Quantity":
                self.bill_summary.column(col, width=50, anchor='center')
            else:
                self.bill_summary.column(col, width=60, anchor='e')
        self.bill_summary.pack(fill='x', expand=True) 
        self.bill_summary.bind("<Double-1>", self.on_double_click_quantity)
        
        # 2. Totals Frame - Using grid for horizontal layout
        self.totals_frame = ttk.Frame(billf, bootstyle="light")
        self.totals_frame.pack(fill='x', pady=(0, 5)) 

        # Total Items Label (Left side)
        self.total_items_label = ttk.Label(self.totals_frame, text="Total Items: 0", font=("Segoe UI", 12, "bold"))
        self.total_items_label.grid(row=0, column=0, padx=5, pady=5, sticky=W)
        
        # Total Price Label (Right side)
        self.total_price_label = ttk.Label(self.totals_frame, text="Total Price: ₹0.00", font=("Segoe UI", 14, "bold"), bootstyle="success")
        self.total_price_label.grid(row=0, column=1, padx=5, pady=5, sticky=E)

        # Configure the grid columns to expand
        self.totals_frame.grid_columnconfigure(0, weight=1) 
        self.totals_frame.grid_columnconfigure(1, weight=1) 
        # =========================================================================

        # Product Details Treeview
        self.Product_Details()

        # Buttons
        btnf = ttk.Frame(root)
        btnf.place(x=0, y=680, width=990, height=40) 
        ttk.Button(btnf, text="Start Scanning", command=self.start_scanning, bootstyle="info").pack(side="left", padx=20)
        ttk.Button(btnf, text="Generate Bill", command=self.generate_bill, bootstyle="success").pack(side="left", padx=20)
        ttk.Button(btnf, text="Exit", command=self.exit_program, bootstyle="danger").pack(side="left", padx=20)
        
    # =========================================================================
    # Bill Search Methods 
    # =========================================================================
    def display_bill_window(self, bill_num, content):
        """
        Creates a new Toplevel window to display the full bill content.
        Note: Removed bootstyle from ttk.Text as it's not supported.
        """
        bill_window = Toplevel(self.root)
        bill_window.title(f"Bill #{bill_num} Details")
        bill_window.geometry("500x600")
        bill_window.transient(self.root)
        bill_window.grab_set()

        # Frame for the Text widget and Scrollbar
        text_frame = ttk.Frame(bill_window, padding=10)
        text_frame.pack(fill='both', expand=True)

        # Scrollbar
        yscrollbar = ttk.Scrollbar(text_frame, orient=VERTICAL)
        yscrollbar.pack(side=RIGHT, fill=Y)

        # Text Widget - FIX: Removed bootstyle
        bill_text = ttk.Text(text_frame, wrap='none', font=("Courier", 10),
                             yscrollcommand=yscrollbar.set)
        
        bill_text.insert(END, content)
        bill_text.config(state='disabled') # Make it read-only
        bill_text.pack(fill='both', expand=True)

        yscrollbar.config(command=bill_text.yview)

        # Add a Close button
        ttk.Button(bill_window, text="Close", command=bill_window.destroy, bootstyle="primary").pack(pady=10)


    def search_bill(self):
        """Searches for a bill file by number and displays its full content in a new window."""
        bill_num = self.search_bill_number.get().strip()
        
        if not bill_num:
            messagebox.showwarning("Input Required", "Please enter a Bill Number to search.")
            return

        # --- PATH CHANGE HERE (Uses the configured absolute path) ---
        filename = os.path.join(INVOICE_DIRECTORY, f"{bill_num}.txt")
        # -----------------------------------------------------------
        
        if not os.path.exists(filename):
            messagebox.showerror("Bill Not Found", f"Bill No. {bill_num} was not found at the location:\n{INVOICE_DIRECTORY}")
            self.search_bill_number.set("")
            return

        try:
            # Attempt to read the file using UTF-8 encoding
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Display the full bill content
            self.display_bill_window(bill_num, content)
            
        except PermissionError:
            messagebox.showerror("File Error", "Permission denied. Try running the application as administrator.")
        except Exception as e:
            messagebox.showerror("File Error", f"Could not process bill: {e}")
            
        # Clear the search box regardless of success/failure
        self.search_bill_number.set("")

    # =========================================================================

    def load_products_lookup(self):
        """Loads product names, categories, and prices from the database for manual entry lookup."""
        try:
            c.execute("SELECT product_name, category, mrp_inr FROM products")
            return {name: (category, float(price)) for name, category, price in c.fetchall()}
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load products: {e}")
            return {}

    def filter_combobox(self, event):
        """Dynamically filters the combobox values based on user input."""
        current_text = self.manual_name.get().strip().lower()
        
        if not current_text:
            self.manual_name_combo['values'] = self.all_product_names
            return

        filtered_list = [
            name for name in self.all_product_names 
            if name.lower().startswith(current_text)
        ]
        
        self.manual_name_combo['values'] = filtered_list

        if filtered_list:
            self.manual_name_combo.event_generate('<Down>')
        else:
            self.manual_name_combo['values'] = ["No matches found"]
            
        self.manual_name_combo.icursor(END)
        self.manual_name_combo.focus()


    def on_manual_name_selected(self, event):
        """Populates category and price fields when a product is selected manually."""
        name = self.manual_name.get().strip()
        self.manual_name_combo['values'] = self.all_product_names
        
        if name in self.product_lookup:
            category, price = self.product_lookup[name]
            self.manual_category.set(category)
            self.manual_price.set(f"{price:.2f}")
        else:
            self.manual_category.set("")
            self.manual_price.set("")

    def Product_Details(self):
        """Creates the frame and Treeview for detailed product listing."""
        frame = ttk.Frame(self.root)
        frame.place(x=10, y=230, width=980, height=420)
        ttk.Label(frame, text="Product Details", bootstyle="secondary", font=("Segoe UI", 15, "bold")).pack(fill='x')
        columns = ("Sr No.", "Title", "Category", "Quantity", "Price")
        self.product_table = tkttk.Treeview(frame, columns=columns, show='headings', height=18)
        for col in columns:
            self.product_table.heading(col, text=col)
        self.product_table.column("Sr No.", width=80, anchor='center')
        self.product_table.column("Title", width=280, anchor='w')
        self.product_table.column("Category", width=180, anchor='center')
        self.product_table.column("Quantity", width=100, anchor='center')
        self.product_table.column("Price", width=120, anchor='e')
        self.product_table.pack(fill='both', expand=True)

    def add_manual_item(self):
        """Adds a manually entered item to the bill summary."""
        name = self.manual_name.get().strip()
        category = self.manual_category.get().strip()
        try:
            qty = int(self.manual_quantity.get())
            price = float(self.manual_price.get())
        except ValueError:
            messagebox.showerror("Input Error", "Enter valid numeric quantity and price.")
            return
        if not name or not category or qty < 1 or price <= 0:
            messagebox.showerror("Input Error", "Fill all fields correctly.")
            return
        
        subtotal = round(qty * price, 2)
        
        updated = self.update_quantity_in_treeview(self.bill_summary, name, category, qty, price)
        if not updated:
            self.bill_summary.insert("", "end", values=(name, category, qty, f"₹{subtotal:.2f}"))
            
        if not self.product_exists_in_product_table(name):
            self.product_table.insert("", "end", values=(
                self.sr_no, name, category, 1, f"₹{price:.2f}"))
            self.sr_no += 1
            
        self.update_totals()
        
        self.manual_name.set("")
        self.manual_category.set("")
        self.manual_quantity.set("1")
        self.manual_price.set("")

    def start_scanning(self):
        """Starts the barcode scanning thread if not already running."""
        if not self.scanning:
            self.scanning = True
            if self.scanning_thread and self.scanning_thread.is_alive():
                self.scanning_thread.join(timeout=0.1)
            
            self.scanning_thread = threading.Thread(target=self.scan_barcode_loop, daemon=True)
            self.scanning_thread.start()

    def scan_barcode_loop(self):
        """Background thread for capturing and decoding barcodes from DroidCam."""
        ip_url = "http://192.168.0.100:4747/video"
        cap = cv2.VideoCapture(ip_url)
        
        if not cap.isOpened():
            self.root.after(0, lambda: messagebox.showerror("Camera Error", "Cannot open DroidCam stream"))
            self.scanning = False
            return
        
        cooldown = 2.0
        last_code, last_time = None, 0
        
        while self.scanning:
            ret, frame = cap.read()
            if not ret:
                break
                
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            barcodes = pyzbar.decode(gray)
            
            if barcodes:
                code = barcodes[0].data.decode("utf-8")
                now = time.time()
                
                if code != last_code or (now - last_time) > cooldown:
                    last_code, last_time = code, now
                    
                    try:
                        self.root.after(0, self.handle_scanned_barcode, code)
                    except RuntimeError:
                        break 
                        
                (x, y, w, h) = barcodes[0].rect
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, code, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            cv2.imshow("DroidCam Barcode Scanner", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.scanning = False
                break
                
        cap.release()
        cv2.destroyAllWindows()
        self.scanning = False

    def update_quantity_in_treeview(self, tree, product_name, category, increase_qty, price_per_unit):
        """Increments the quantity of an item in the bill summary Treeview."""
        for item in tree.get_children():
            vals = tree.item(item, "values")
            if tree == self.bill_summary:
                title = vals[0]
                qty_idx, price_idx = 2, 3
                if title == product_name:
                    old_qty = int(vals[qty_idx])
                    new_qty = old_qty + increase_qty
                    new_price = round(new_qty * price_per_unit, 2)
                    
                    vals = list(vals)
                    vals[qty_idx] = new_qty
                    vals[price_idx] = f"₹{new_price:.2f}"
                    tree.item(item, values=vals)
                    self.update_totals()
                    return True
        return False

    def product_exists_in_product_table(self, product_name):
        """Checks if a product is already listed in the product details table."""
        for item in self.product_table.get_children():
            vals = self.product_table.item(item, "values")
            if vals[1] == product_name:
                return True
        return False

    def handle_scanned_barcode(self, barcode):
        """Processes a scanned barcode and updates the GUI."""
        record = info_by_barcode(barcode)
        if record:
            title, category, price_str = record
            price_float = float(price_str)
            qty = 1
            
            updated = self.update_quantity_in_treeview(
                self.bill_summary, title, category, 1, price_float
            )
            
            if not updated:
                subtotal = round(qty * price_float, 2)
                self.bill_summary.insert("", "end", values=(title, category, qty, f"₹{subtotal:.2f}"))
            
            if not self.product_exists_in_product_table(title):
                self.product_table.insert("", "end", values=(
                    self.sr_no, title, category, 1, f"₹{price_float:.2f}"))
                self.sr_no += 1
                
            self.update_totals()
        else:
            messagebox.showwarning("Product Not Found", f"Barcode {barcode} not found in database.")

    def on_double_click_quantity(self, event):
        """Handles double-click event to edit item quantity in bill summary."""
        region = self.bill_summary.identify("region", event.x, event.y)
        if region != "cell": return
        col_id = self.bill_summary.identify_column(event.x)
        
        if self.bill_summary.heading(col_id, "text") != "Quantity": return
        
        rowid = self.bill_summary.identify_row(event.y)
        if not rowid: return
        
        x, y, width, height = self.bill_summary.bbox(rowid, col_id)
        val = self.bill_summary.set(rowid, "Quantity")
        
        if self.edit_quantity_entry:
            self.edit_quantity_entry.destroy()
            
        self.edit_quantity_entry = ttk.Entry(self.bill_summary, width=5)
        self.edit_quantity_entry.place(x=x, y=y, width=width, height=height)
        self.edit_quantity_entry.insert(0, val)
        self.edit_quantity_entry.focus()

        def finish_edit(event=None):
            self.save_edited_quantity(rowid)

        self.edit_quantity_entry.bind("<FocusOut>", finish_edit)
        self.edit_quantity_entry.bind("<Return>", finish_edit)

    def save_edited_quantity(self, item_id):
        """Saves the manually edited quantity and updates the price."""
        if not self.edit_quantity_entry:
            return
        
        try:
            qty_new = int(self.edit_quantity_entry.get())
            if qty_new < 1:
                qty_new = 1
        except ValueError:
            messagebox.showwarning("Input Error", "Quantity must be an integer.")
            self.edit_quantity_entry.destroy()
            self.edit_quantity_entry = None
            return

        vals = list(self.bill_summary.item(item_id, "values"))
        qty_old = int(vals[2])
        
        # Calculate price per unit from old total price
        try:
            old_total_price = float(vals[3].replace('₹', '').strip())
            price_per_unit = old_total_price / qty_old
        except ZeroDivisionError:
            price_per_unit = 0.0
        except ValueError:
            messagebox.showwarning("Data Error", "Invalid price format in bill summary.")
            self.edit_quantity_entry.destroy()
            self.edit_quantity_entry = None
            return
        
        vals[2] = qty_new
        new_subtotal = qty_new * price_per_unit
        vals[3] = f"₹{new_subtotal:.2f}"
        
        self.bill_summary.item(item_id, values=vals)
        
        self.edit_quantity_entry.destroy()
        self.edit_quantity_entry = None
        self.update_totals()

    def update_totals(self):
        """Recalculates and updates the total items and total price."""
        items = 0
        total = 0.0
        for item in self.bill_summary.get_children():
            vals = self.bill_summary.item(item)["values"]
            q = int(vals[2])
            # Ensure price parsing is robust
            try:
                p = float(vals[3].replace('₹', '').strip())
            except ValueError:
                p = 0.0
                
            items += q
            total += p
            
        self.bill_total = total
        self.total_items_label.config(text=f"Total Items: {items}")
        self.total_price_label.config(text=f"Total Price: ₹{total:.2f}")

    def generate_bill(self):
        """Stops scanning, checks for data, and generates the bill file in the specified absolute path."""
        self.scanning = False
        if self.scanning_thread and self.scanning_thread.is_alive():
            self.scanning_thread.join(timeout=1)
            
        cust = self.customer_name.get().strip()
        phone = self.customer_phone.get().strip()
        
        if not cust or not phone:
            messagebox.showerror("Input Error", "Enter customer name and phone")
            return
        if not self.bill_summary.get_children():
            messagebox.showerror("No Products", "Scan or add products before generating bills.")
            return
            
        # --- PATH CHANGE IMPLEMENTED HERE ---
        # Ensure the specified absolute Invoice directory exists
        if not os.path.exists(INVOICE_DIRECTORY):
            try:
                os.makedirs(INVOICE_DIRECTORY)
            except PermissionError:
                 messagebox.showerror("Folder Error", f"Permission denied to create folder at: {INVOICE_DIRECTORY}")
                 return
            except Exception as e:
                 messagebox.showerror("Folder Error", f"Failed to create directory: {e}")
                 return
            
        filename = os.path.join(INVOICE_DIRECTORY, f"{self.bill_no}.txt")
        # ------------------------------------
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("="*30 + " KTMALL " + "="*30 + "\n")
                f.write(f"Bill No: {self.bill_no:<50}\n")
                f.write(f"Customer Name: {cust}\n")
                f.write(f"Customer Phone: {phone}\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*68 + "\n")
                f.write(f"{'Product':25} {'Category':15} {'Qty':>5} {'Price':>12}\n")
                f.write("-"*68 + "\n")
                
                for item in self.bill_summary.get_children():
                    vals = self.bill_summary.item(item)["values"]
                    t, c, q, pr = vals
                    pr_num = pr.replace('₹', '').strip()
                    f.write(f"{t[:25]:25} {c[:15]:15} {q:>5} {pr_num:>12}\n")
                    
                f.write("="*68 + "\n")
                
                items_text = self.total_items_label.cget('text').split(':')[1].strip()
                f.write(f"{'Total Items':>46} : {items_text}\n")
                f.write(f"{'Total Price':>46} : ₹{self.bill_total:.2f}\n")
                
                f.write("="*68 + "\n")
                f.write("         Thank you for shopping at KTMALL!         \n")

            messagebox.showinfo("Bill Generated", f"Bill saved successfully at:\n{filename}")
        
        except PermissionError:
            messagebox.showerror("File Write Error", f"Permission denied. Could not save the bill file to:\n{INVOICE_DIRECTORY}")
            return
        except Exception as e:
            messagebox.showerror("File Write Error", f"An unexpected error occurred while saving the bill: {e}")
            return

        # Reset the UI for a new bill
        self.bill_no = str(random.randint(1000, 9999))
        self.customer_name.set("")
        self.customer_phone.set("")
        self.bill_summary.delete(*self.bill_summary.get_children())
        self.product_table.delete(*self.product_table.get_children())
        self.sr_no = 1
        self.update_totals()

    def exit_program(self):
        """Safely stops all threads, closes resources, and exits the application."""
        self.scanning = False
        
        if self.scanning_thread and self.scanning_thread.is_alive():
            print("Waiting for scanning thread to close...")
            self.scanning_thread.join(timeout=1) 
        
        try:
            cv2.destroyAllWindows()
        except:
            pass
            
        try:
            # Ensure to close the cursor before the connection
            c.close() 
            conn.close()
        except Exception as e:
            print(f"Error during DB close: {e}") 
        
        self.root.destroy()

if __name__ == "__main__":
    root = ttk.Window(themename="superhero")
    app = BillApp(root)
    root.mainloop()
