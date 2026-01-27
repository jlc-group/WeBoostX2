#!/usr/bin/env python3
"""
Sales Out CSV Upload Script
อัปโหลดข้อมูล Sale Out จากไฟล์ CSV เข้าตาราง sales_out

Features:
- รองรับหลายรูปแบบวันที่ (DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, etc.)
- Auto-detect columns จาก CSV
- Validation ข้อมูลก่อนบันทึก
- รองรับ encoding ภาษาไทย
- Batch insert สำหรับความเร็ว

Usage:
    python upload_sales_out_csv.py sales_data.csv
    python upload_sales_out_csv.py sales_data.csv --skip-duplicates
    python upload_sales_out_csv.py sales_data.csv --dry-run  # ทดสอบก่อน
"""

import os
import sys
import csv
import psycopg2
import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

class SalesOutCSVUploader:
    def __init__(self, dry_run=False, skip_duplicates=False):
        """Initialize uploader"""
        self.conn = None
        self.dry_run = dry_run
        self.skip_duplicates = skip_duplicates
        self.stats = {
            'total_rows': 0,
            'success': 0,
            'skipped': 0,
            'errors': 0,
            'error_details': []
        }
        
        # รูปแบบวันที่ที่รองรับ (เรียงตามความนิยม)
        self.date_formats = [
            '%d/%m/%Y',      # 06/01/2025 (Thai style)
            '%d-%m-%Y',      # 06-01-2025
            '%Y-%m-%d',      # 2025-01-06 (ISO)
            '%d/%m/%y',      # 06/01/25
            '%d-%m-%y',      # 06-01-25
            '%Y/%m/%d',      # 2025/01/06
            '%d.%m.%Y',      # 06.01.2025
            '%Y%m%d',        # 20250106
            '%d %b %Y',      # 06 Jan 2025
            '%d %B %Y',      # 06 January 2025
            '%m/%d/%Y',      # 01/06/2025 (US style)
            '%Y.%m.%d',      # 2025.01.06
        ]
    
    def connect_db(self):
        """Connect to PostgreSQL database"""
        try:
            self.conn = psycopg2.connect(
                host=PG_HOST,
                port=PG_PORT,
                dbname=PG_DB,
                user=PG_USER,
                password=PG_PASSWORD
            )
            self.conn.autocommit = not self.dry_run  # Use transaction for dry-run
            print(f"✅ Connected to database: {PG_DB}@{PG_HOST}:{PG_PORT}")
            return True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False
    
    def parse_date(self, date_str):
        """
        Parse date string with multiple format support
        Returns: date object (YYYY-MM-DD format) to match PostgreSQL DATE type
        
        Note: Facebook tables use TIMESTAMP WITH TIME ZONE for created_time
              To join with sales data, use: DATE(facebook_posts.created_time) = sales_out.sale_date
        """
        if not date_str or str(date_str).strip() == '':
            return None
        
        date_str = str(date_str).strip()
        
        # ลองแต่ละรูปแบบ
        for fmt in self.date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                # Return as date object (will be stored as DATE in PostgreSQL)
                # Format: YYYY-MM-DD (standard SQL DATE format)
                return parsed_date
            except ValueError:
                continue
        
        # ถ้าไม่ตรงรูปแบบไหนเลย
        raise ValueError(
            f"Cannot parse date: '{date_str}'. "
            f"Supported formats: DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, etc."
        )
    
    def parse_decimal(self, value_str, field_name=""):
        """Parse decimal/float value safely"""
        if not value_str or str(value_str).strip() == '':
            return None
        
        try:
            # ลบ comma, space, currency symbols
            cleaned = str(value_str).replace(',', '').replace(' ', '').replace('฿', '').strip()
            if cleaned == '' or cleaned == '-':
                return None
            return Decimal(cleaned)
        except (ValueError, InvalidOperation) as e:
            raise ValueError(f"Invalid number format for {field_name}: '{value_str}'")
    
    def parse_integer(self, value_str, field_name=""):
        """Parse integer value safely"""
        if not value_str or str(value_str).strip() == '':
            return None
        
        try:
            # ลบ comma และ space ออก
            cleaned = str(value_str).replace(',', '').replace(' ', '').strip()
            if cleaned == '' or cleaned == '-':
                return None
            # ลบทศนิยมถ้ามี (เช่น 10.0 -> 10)
            if '.' in cleaned:
                cleaned = cleaned.split('.')[0]
            return int(cleaned)
        except ValueError as e:
            raise ValueError(f"Invalid integer format for {field_name}: '{value_str}'")
    
    def read_csv(self, csv_file):
        """Read CSV file with multiple encoding support"""
        encodings = ['utf-8-sig', 'utf-8', 'tis-620', 'windows-874', 'cp874', 'latin1']
        
        for encoding in encodings:
            try:
                with open(csv_file, 'r', encoding=encoding) as f:
                    # อ่าน 1 บรรทัดเพื่อทดสอบ
                    sample = f.readline()
                    
                # ถ้าสำเร็จ อ่านทั้งไฟล์
                with open(csv_file, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    
                    # Clean BOM from fieldnames
                    cleaned_fieldnames = [name.lstrip('\ufeff').strip() for name in reader.fieldnames]
                    
                    rows = list(reader)
                    print(f"✅ Successfully read CSV with encoding: {encoding}")
                    print(f"📊 Found {len(rows)} rows, {len(cleaned_fieldnames)} columns")
                    print(f"📋 Columns detected:")
                    for i, col in enumerate(cleaned_fieldnames, 1):
                        print(f"   {i}. '{col}'")
                    
                    # Remap rows with cleaned fieldnames
                    cleaned_rows = []
                    for row in rows:
                        cleaned_row = {}
                        for old_name, new_name in zip(reader.fieldnames, cleaned_fieldnames):
                            cleaned_row[new_name] = row[old_name]
                        cleaned_rows.append(cleaned_row)
                    
                    return cleaned_rows, cleaned_fieldnames
                    
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"⚠️  Error with encoding {encoding}: {e}")
                continue
        
        raise Exception(f"Cannot read CSV file with any supported encoding: {encodings}")
    
    def detect_column_mapping(self, csv_columns):
        """Auto-detect column mapping from CSV to database schema"""
        
        # Column mapping with multiple possible names (case-insensitive)
        field_patterns = {
            'sale_date': [
                'sale_date', 'date', 'วันที่', 'transaction_date', 'txn_date', 
                'sale date', 'วันที่ขาย', 'ว/ด/ป', 'ว/ด/ป ขาย', 'saledate'
            ],
            'distributor_code': [
                'distributor_code', 'dist_code', 'รหัสดิส', 'รหัสผู้จัดจำหน่าย',
                'distributor code', 'dist code'
            ],
            'distributor_name': [
                'distributor_name', 'distributor', 'ชื่อดิส', 'ชื่อผู้จัดจำหน่าย',
                'dist_name', 'distributor name', 'dist name'
            ],
            'customer_name': [
                'customer_name', 'customer', 'ชื่อลูกค้า', 'ร้าน',
                'customer name', 'shop', 'shop_name'
            ],
            'product_code': [
                'product_code', 'prod_code', 'รหัสสินค้า', 'item_code',
                'product code', 'prod code'
            ],
            'product_name': [
                'product_name', 'product', 'ชื่อสินค้า', 'item_name', 'item',
                'product name', 'prod name'
            ],
            'pack_type_name': [
                'pack_type_name', 'pack_type', 'ประเภทแพ็ค', 'pack', 'packaging',
                'pack type name', 'pack type'
            ],
            'sale_quantity': [
                'sale_quantity', 'quantity', 'qty', 'จำนวน', 'amount', 'sale',
                'sale qty', 'sale quantity', 'salequantity'
            ],
            'sku_code': [
                'sku_code', 'sku', 'รหัส sku', 'sku code'
            ],
            'unit_price': [
                'unit_price', 'price', 'ราคา', 'unit_cost', 'ราคาต่อหน่วย',
                'unit price', 'unitprice', 'unit_price'
            ],
            'grand_sale': [
                'grand_sale', 'total', 'รวม', 'total_amount', 'amount', 'ยอดรวม',
                'grand sale', 'total sale', 'sale amount', 'grandsale', 'grand_sale'
            ],
            'sku_code_jlc': [
                'sku_code_jlc', 'sku_jlc', 'jlc_sku', 'รหัส jlc',
                'sku code jlc', 'jlc sku'
            ]
        }
        
        detected = {}
        unmatched_cols = []
        
        for csv_col in csv_columns:
            matched = False
            csv_col_lower = csv_col.lower().strip()
            
            for db_field, patterns in field_patterns.items():
                # Check each pattern
                for pattern in patterns:
                    if csv_col_lower == pattern.lower().strip():
                        detected[db_field] = csv_col
                        matched = True
                        break
                if matched:
                    break
            
            if not matched:
                unmatched_cols.append(csv_col)
        
        print(f"\n🔍 Column Mapping:")
        for db_field, csv_col in detected.items():
            print(f"   {db_field:<20} ← '{csv_col}'")
        
        if unmatched_cols:
            print(f"\n⚠️  Unmatched columns (will be ignored):")
            for col in unmatched_cols:
                print(f"   - '{col}'")
        
        # Check required fields
        required = ['sale_date']
        missing = [f for f in required if f not in detected]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        
        return detected
    
    def check_duplicate(self, sale_date, product_code, customer_name, sale_quantity, cursor):
        """Check if record already exists"""
        cursor.execute("""
            SELECT id FROM sales_out 
            WHERE sale_date = %s 
              AND product_code = %s 
              AND customer_name = %s 
              AND sale_quantity = %s
            LIMIT 1
        """, (sale_date, product_code, customer_name, sale_quantity))
        
        return cursor.fetchone() is not None
    
    def insert_row(self, row_data, cursor):
        """Insert a single row to database"""
        query = """
        INSERT INTO sales_out (
            sale_date, distributor_code, distributor_name, customer_name,
            product_code, product_name, pack_type_name, sale_quantity,
            sku_code, unit_price, grand_sale, sku_code_jlc, created_at
        ) VALUES (
            %(sale_date)s, %(distributor_code)s, %(distributor_name)s, %(customer_name)s,
            %(product_code)s, %(product_name)s, %(pack_type_name)s, %(sale_quantity)s,
            %(sku_code)s, %(unit_price)s, %(grand_sale)s, %(sku_code_jlc)s, NOW()
        )
        """
        
        cursor.execute(query, row_data)
    
    def upload_csv(self, csv_file):
        """Main upload process"""
        print("\n" + "="*60)
        print("🚀 Sales Out CSV Upload")
        print("="*60)
        
        if self.dry_run:
            print("⚠️  DRY-RUN MODE: No data will be saved")
        
        # Check file exists
        if not os.path.exists(csv_file):
            print(f"❌ File not found: {csv_file}")
            return False
        
        # Connect to database
        if not self.connect_db():
            return False
        
        try:
            # Read CSV
            print(f"\n📂 Reading file: {csv_file}")
            rows, columns = self.read_csv(csv_file)
            
            if not rows:
                print("⚠️  No data found in CSV file")
                return False
            
            self.stats['total_rows'] = len(rows)
            
            # Detect column mapping
            try:
                column_map = self.detect_column_mapping(columns)
            except ValueError as e:
                print(f"❌ Column mapping error: {e}")
                return False
            
            # Validate and prepare data
            print(f"\n📝 Processing {len(rows)} rows...")
            valid_rows = []
            
            with self.conn.cursor() as cursor:
                for i, row in enumerate(rows, start=2):  # Start from 2 (row 1 is header)
                    try:
                        # Parse sale_date
                        sale_date_str = row.get(column_map.get('sale_date', ''), '').strip()
                        if not sale_date_str:
                            self.stats['errors'] += 1
                            error_msg = f"Row {i}: Empty sale_date"
                            self.stats['error_details'].append(error_msg)
                            if i <= 5:  # Show first 5 errors
                                print(f"  ⚠️  {error_msg}")
                            continue
                        
                        try:
                            sale_date = self.parse_date(sale_date_str)
                        except ValueError as e:
                            self.stats['errors'] += 1
                            error_msg = f"Row {i}: {str(e)}"
                            self.stats['error_details'].append(error_msg)
                            if i <= 5:
                                print(f"  ⚠️  {error_msg}")
                            continue
                        
                        # Prepare row data
                        row_data = {
                            'sale_date': sale_date,
                            'distributor_code': row.get(column_map.get('distributor_code', ''), '').strip() or None,
                            'distributor_name': row.get(column_map.get('distributor_name', ''), '').strip() or None,
                            'customer_name': row.get(column_map.get('customer_name', ''), '').strip() or None,
                            'product_code': row.get(column_map.get('product_code', ''), '').strip() or None,
                            'product_name': row.get(column_map.get('product_name', ''), '').strip() or None,
                            'pack_type_name': row.get(column_map.get('pack_type_name', ''), '').strip() or None,
                            'sale_quantity': self.parse_integer(
                                row.get(column_map.get('sale_quantity', ''), ''), 'sale_quantity'
                            ),
                            'sku_code': row.get(column_map.get('sku_code', ''), '').strip() or None,
                            'unit_price': self.parse_decimal(
                                row.get(column_map.get('unit_price', ''), ''), 'unit_price'
                            ),
                            'grand_sale': self.parse_decimal(
                                row.get(column_map.get('grand_sale', ''), ''), 'grand_sale'
                            ),
                            'sku_code_jlc': row.get(column_map.get('sku_code_jlc', ''), '').strip() or None
                        }
                        
                        # Check duplicate
                        if self.skip_duplicates:
                            if self.check_duplicate(
                                row_data['sale_date'],
                                row_data['product_code'],
                                row_data['customer_name'],
                                row_data['sale_quantity'],
                                cursor
                            ):
                                self.stats['skipped'] += 1
                                continue
                        
                        valid_rows.append(row_data)
                        
                    except Exception as e:
                        self.stats['errors'] += 1
                        error_msg = f"Row {i}: {str(e)}"
                        self.stats['error_details'].append(error_msg)
                        if i <= 5:
                            print(f"  ⚠️  {error_msg}")
            
            print(f"✅ Validation complete: {len(valid_rows)} valid rows")
            
            if self.stats['errors'] > 5:
                print(f"⚠️  {self.stats['errors']} total errors (showing first 5)")
            
            # Insert data
            if valid_rows and not self.dry_run:
                print(f"\n💾 Inserting {len(valid_rows)} rows...")
                
                with self.conn.cursor() as cursor:
                    batch_size = 100
                    for idx, row_data in enumerate(valid_rows, 1):
                        try:
                            self.insert_row(row_data, cursor)
                            self.stats['success'] += 1
                            
                            if idx % batch_size == 0:
                                print(f"   ✓ Inserted {idx}/{len(valid_rows)} rows...")
                                
                        except Exception as e:
                            self.stats['errors'] += 1
                            error_msg = f"Insert error (row {idx}): {str(e)}"
                            self.stats['error_details'].append(error_msg)
                            continue
                
                self.conn.commit()
                print(f"✅ Successfully inserted {self.stats['success']} rows")
                
            elif self.dry_run and valid_rows:
                print(f"\n✅ Dry-run complete: {len(valid_rows)} rows would be inserted")
                print(f"\n📋 Sample data (first 2 rows):")
                for i, row in enumerate(valid_rows[:2], 1):
                    print(f"\n  Row {i}:")
                    for key, value in row.items():
                        if value is not None:
                            # Handle Thai text display
                            display_value = value
                            if isinstance(value, str) and len(value) > 50:
                                display_value = value[:50] + '...'
                            try:
                                print(f"    {key:<20} = {display_value}")
                            except UnicodeEncodeError:
                                # Fallback for encoding errors
                                print(f"    {key:<20} = [Thai text - {len(str(value))} chars]")
            
            # Summary
            self.print_summary()
            return self.stats['errors'] == 0 or self.stats['success'] > 0
            
        except Exception as e:
            print(f"\n❌ Upload failed: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            if self.conn:
                self.conn.close()
    
    def print_summary(self):
        """Print upload summary"""
        print("\n" + "="*60)
        print("📊 Upload Summary")
        print("="*60)
        print(f"Total rows in CSV:      {self.stats['total_rows']}")
        print(f"✅ Successfully saved:  {self.stats['success']}")
        print(f"⏭️  Skipped (duplicates): {self.stats['skipped']}")
        print(f"❌ Errors:              {self.stats['errors']}")
        
        if self.stats['errors'] > 0 and self.stats['error_details']:
            print(f"\n⚠️  Error summary (first 10):")
            for error in self.stats['error_details'][:10]:
                print(f"   - {error}")
            if len(self.stats['error_details']) > 10:
                print(f"   ... and {len(self.stats['error_details']) - 10} more errors")
        
        print("="*60)

def main():
    """Main function"""
    # Fix Windows encoding for PowerShell
    if sys.platform.startswith('win'):
        import codecs
        # Use 'replace' instead of 'strict' to handle encoding errors gracefully
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')
        
        # Set console to UTF-8 mode
        try:
            import subprocess
            subprocess.run(['chcp', '65001'], shell=True, capture_output=True)
        except:
            pass
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='Upload Sales Out data from CSV to database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python upload_sales_out_csv.py sales_data.csv
  python upload_sales_out_csv.py sales_data.csv --skip-duplicates
  python upload_sales_out_csv.py sales_data.csv --dry-run

Required CSV columns (auto-detected, case-insensitive):
  - sale_date / date / วันที่ (Required)
  
Optional columns (will be matched automatically):
  - distributor_code / รหัสดิส
  - distributor_name / ชื่อดิส
  - customer_name / ชื่อลูกค้า
  - product_code / รหัสสินค้า
  - product_name / ชื่อสินค้า
  - pack_type_name / ประเภทแพ็ค
  - sale_quantity / จำนวน
  - sku_code / รหัส sku
  - unit_price / ราคา
  - grand_sale / ยอดรวม
  - sku_code_jlc / รหัส jlc

Supported date formats:
  - 06/01/2025 (DD/MM/YYYY) ← Thai style
  - 2025-01-06 (YYYY-MM-DD)
  - 06-01-2025 (DD-MM-YYYY)
  - 01/06/2025 (MM/DD/YYYY)
  - And more...

Note: Script will auto-detect column names and date formats
        """
    )
    
    parser.add_argument('csv_file', help='Path to CSV file')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Test run without saving to database (recommended first)')
    parser.add_argument('--skip-duplicates', action='store_true',
                       help='Skip duplicate records based on date+product+customer+quantity')
    
    args = parser.parse_args()
    
    # Run upload
    uploader = SalesOutCSVUploader(
        dry_run=args.dry_run,
        skip_duplicates=args.skip_duplicates
    )
    
    success = uploader.upload_csv(args.csv_file)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
