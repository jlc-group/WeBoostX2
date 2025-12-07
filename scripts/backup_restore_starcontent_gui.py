#!/usr/bin/env python
"""
Simple GUI (Tkinter) สำหรับ Backup + Restore ฐานข้อมูล Starcontent

Workflow:
1) Backup จากระบบเก่า โดยอ่าน connection จากไฟล์ .env เดิม (เช่น old_ref/WeBoostX/.env)
2) Restore ไฟล์ backup เข้า PostgreSQL บน localhost (เช่น ฐาน starcontent)

การใช้งาน:
    python scripts/backup_restore_starcontent_gui.py

ข้อกำหนด:
- ต้องติดตั้ง PostgreSQL client และมีคำสั่ง `pg_dump` กับ `pg_restore` อยู่ใน PATH
- ไฟล์ .env ของระบบเก่าควรมี DATABASE_URL / SQLALCHEMY_DATABASE_URI /
  OLD_DATABASE_URL หรือชุดตัวแปร POSTGRES_* / DB_* ที่ใช้ต่อฐานเก่า
"""

import datetime
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from dotenv import load_dotenv


# -------------------------
# Helper functions
# -------------------------

def log(text_widget: scrolledtext.ScrolledText, msg: str) -> None:
    """Append log message to text widget (thread‑safe helper)."""
    def _append():
        text_widget.insert(tk.END, msg + "\n")
        text_widget.see(tk.END)

    text_widget.after(0, _append)


def resolve_db_url_from_env() -> Optional[str]:
    """
    หา connection string ของฐานข้อมูลเก่า จากตัวแปรใน .env / environment ปัจจุบัน
    ลองตามลำดับ:
    - DATABASE_URL
    - SQLALCHEMY_DATABASE_URI
    - OLD_DATABASE_URL
    - หรือประกอบจาก POSTGRES_* / DB_* ถ้ามี
    """
    for key in ["DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "OLD_DATABASE_URL"]:
        val = os.getenv(key)
        if val:
            return val

    host = (
        os.getenv("POSTGRES_HOST")
        or os.getenv("DB_HOST")
        or os.getenv("PGHOST")
        or "localhost"
    )
    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or os.getenv("PGPORT") or "5432"
    name = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME") or "starcontent"
    user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres"
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD") or ""

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"
    return f"postgresql://{user}@{host}:{port}/{name}"


def run_pg_dump(db_url: str, output_path: str, log_fn) -> None:
    cmd = ["pg_dump", db_url, "-Fc", "-f", output_path]
    log_fn(f"[pg_dump] Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        log_fn("[pg_dump] สำเร็จ")
    except FileNotFoundError:
        log_fn("ERROR: ไม่พบคำสั่ง 'pg_dump' ใน PATH\nโปรดติดตั้ง PostgreSQL client และเพิ่ม bin เข้าสู่ PATH")
        raise
    except subprocess.CalledProcessError as e:
        log_fn(f"ERROR: pg_dump ล้มเหลว (exit code {e.returncode})")
        raise


def run_pg_restore(db_url: str, dump_path: str, log_fn) -> None:
    cmd = ["pg_restore", "-c", "-d", db_url, dump_path]
    log_fn(f"[pg_restore] Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        log_fn("[pg_restore] สำเร็จ")
    except FileNotFoundError:
        log_fn("ERROR: ไม่พบคำสั่ง 'pg_restore' ใน PATH\nโปรดติดตั้ง PostgreSQL client และเพิ่ม bin เข้าสู่ PATH")
        raise
    except subprocess.CalledProcessError as e:
        log_fn(f"ERROR: pg_restore ล้มเหลว (exit code {e.returncode})")
        raise


# -------------------------
# GUI Application
# -------------------------

class BackupRestoreApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Starcontent Backup & Restore")
        self.geometry("820x600")

        # Default paths
        self.default_env_path = str(Path("old_ref") / "WeBoostX" / ".env")

        # Widgets
        self._build_ui()

    # UI Layout
    def _build_ui(self):
        # Backup frame
        backup_frame = tk.LabelFrame(self, text="ขั้นตอนที่ 1: Backup จากระบบเก่า", padx=10, pady=10)
        backup_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(backup_frame, text="ไฟล์ .env ของระบบเก่า:").grid(row=0, column=0, sticky="w")
        self.env_path_var = tk.StringVar(value=self.default_env_path)
        tk.Entry(backup_frame, textvariable=self.env_path_var, width=80).grid(row=1, column=0, sticky="w")
        tk.Button(backup_frame, text="เลือกไฟล์...", command=self.browse_env).grid(row=1, column=1, padx=5)

        tk.Label(backup_frame, text="ไฟล์ backup ที่จะสร้าง (ปล่อยว่างให้ตั้งชื่ออัตโนมัติ):").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.backup_output_var = tk.StringVar()
        tk.Entry(backup_frame, textvariable=self.backup_output_var, width=80).grid(row=3, column=0, sticky="w")

        tk.Button(
            backup_frame,
            text="รัน Backup จากระบบเก่า",
            command=self.on_backup_click,
            bg="#111827",
            fg="white",
            padx=10,
            pady=5,
        ).grid(row=4, column=0, sticky="w", pady=10)

        # Restore frame
        restore_frame = tk.LabelFrame(self, text="ขั้นตอนที่ 2: Restore เข้า localhost", padx=10, pady=10)
        restore_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(restore_frame, text="Local DB URL (ปลายทาง):").grid(row=0, column=0, sticky="w")
        self.local_db_url_var = tk.StringVar(
            value="postgresql://postgres:password@localhost:5432/starcontent"
        )
        tk.Entry(restore_frame, textvariable=self.local_db_url_var, width=80).grid(row=1, column=0, sticky="w")

        tk.Label(restore_frame, text="ไฟล์ backup (.dump) ที่จะใช้ restore:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.restore_dump_var = tk.StringVar()
        tk.Entry(restore_frame, textvariable=self.restore_dump_var, width=80).grid(row=3, column=0, sticky="w")
        tk.Button(restore_frame, text="เลือกไฟล์...", command=self.browse_dump).grid(row=3, column=1, padx=5)

        tk.Button(
            restore_frame,
            text="รัน Restore เข้า localhost",
            command=self.on_restore_click,
            bg="#047857",
            fg="white",
            padx=10,
            pady=5,
        ).grid(row=4, column=0, sticky="w", pady=10)

        # Log output
        log_frame = tk.LabelFrame(self, text="Log", padx=5, pady=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_widget = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15)
        self.log_widget.pack(fill="both", expand=True)

    # Event handlers
    def browse_env(self):
        path = filedialog.askopenfilename(
            title="เลือกไฟล์ .env ของระบบเก่า",
            filetypes=[("Env files", ".env"), ("All files", ".*")],
        )
        if path:
            self.env_path_var.set(path)

    def browse_dump(self):
        path = filedialog.askopenfilename(
            title="เลือกไฟล์ backup (.dump)",
            filetypes=[("Dump files", ".dump .sql"), ("All files", ".*")],
        )
        if path:
            self.restore_dump_var.set(path)

    def on_backup_click(self):
        threading.Thread(target=self._do_backup, daemon=True).start()

    def on_restore_click(self):
        threading.Thread(target=self._do_restore, daemon=True).start()

    # Actual operations
    def _do_backup(self):
        env_path = self.env_path_var.get().strip()
        output_path = self.backup_output_var.get().strip()

        if env_path and os.path.isfile(env_path):
            log(self.log_widget, f"[backup] โหลด .env จาก {env_path}")
            load_dotenv(env_path)
        else:
            log(self.log_widget, f"[backup] ไม่พบ .env ที่ {env_path} จะลองใช้ environment ปัจจุบันแทน")

        db_url = resolve_db_url_from_env()
        if not db_url:
            log(self.log_widget, "ERROR: หา connection string ของฐานเก่าไม่เจอ (DATABASE_URL / SQLALCHEMY_DATABASE_URI / OLD_DATABASE_URL)")
            messagebox.showerror("Backup ล้มเหลว", "หา DB URL ของระบบเก่าไม่เจอ\nกรุณาเช็คค่าใน .env")
            return

        if not output_path:
            today = datetime.datetime.now().strftime("%Y%m%d")
            output_path = f"starcontent_backup_{today}.dump"
            self.backup_output_var.set(output_path)

        log(self.log_widget, f"[backup] DB URL: {db_url}")
        log(self.log_widget, f"[backup] จะสร้างไฟล์: {output_path}")

        try:
            run_pg_dump(db_url, output_path, lambda m: log(self.log_widget, m))
            abs_path = os.path.abspath(output_path)
            log(self.log_widget, f"[backup] เสร็จสิ้น → {abs_path}")
            # auto-fill ให้ restore ใช้ไฟล์เดียวกันได้เลย
            self.restore_dump_var.set(abs_path)
            messagebox.showinfo("Backup สำเร็จ", f"สร้างไฟล์ backup แล้วที่\n{abs_path}")
        except Exception as e:
            messagebox.showerror("Backup ล้มเหลว", str(e))

    def _do_restore(self):
        db_url = self.local_db_url_var.get().strip()
        dump_path = self.restore_dump_var.get().strip()

        if not db_url:
            messagebox.showerror("Restore ล้มเหลว", "กรุณาใส่ Local DB URL")
            return
        if not dump_path or not os.path.isfile(dump_path):
            messagebox.showerror("Restore ล้มเหลว", "ไม่พบไฟล์ backup ที่ระบุ")
            return

        log(self.log_widget, f"[restore] DB URL: {db_url}")
        log(self.log_widget, f"[restore] ไฟล์ backup: {dump_path}")

        try:
            run_pg_restore(db_url, dump_path, lambda m: log(self.log_widget, m))
            messagebox.showinfo("Restore สำเร็จ", "Restore เข้า localhost สำเร็จแล้ว")
        except Exception as e:
            messagebox.showerror("Restore ล้มเหลว", str(e))


def main():
    app = BackupRestoreApp()
    app.mainloop()


if __name__ == "__main__":
    # ให้ script ทำงานได้แม้จะถูกเรียกจากโฟลเดอร์อื่น โดยอิงจาก path ของไฟล์นี้
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))

    main()


