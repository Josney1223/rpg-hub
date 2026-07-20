"""Left-hand 'Bulbs' panel: scan, add, list, test, delete devices."""

import threading

import tkinter as tk
from tkinter import ttk, messagebox

from . import config
from .lights import tinytuya


class DevicesPanel(ttk.LabelFrame):
    def __init__(self, parent, app):
        super().__init__(parent, text="Bulbs", padding=6)
        self.app = app
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        btns = ttk.Frame(self)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(btns, text="Scan network", command=self._scan).pack(side="left")
        ttk.Button(btns, text="Add manually", command=self._add_manual).pack(side="left", padx=4)

        canvas = tk.Canvas(self, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.holder = ttk.Frame(canvas)
        self.holder.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.holder, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        self.refresh()

    def refresh(self):
        for w in self.holder.winfo_children():
            w.destroy()
        if not self.app.devices:
            ttk.Label(self.holder, foreground="#888",
                      text="No bulbs yet.\nUse 'Scan network' or 'Add manually'."
                      ).pack(anchor="w", pady=8, padx=4)
            return
        for dev in self.app.devices:
            name = dev["name"]
            self.app.active.setdefault(name, tk.BooleanVar(value=True))
            row = ttk.Frame(self.holder)
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(row, variable=self.app.active[name]).pack(side="left")
            ttk.Label(row, text=f"{name}  ({dev['ip']})", width=24, anchor="w").pack(side="left")
            ttk.Button(row, text="Test", width=5,
                       command=lambda d=dev: self.app.run_bg(self.app.ctl.blink_test, d)
                       ).pack(side="right")
            ttk.Button(row, text="Del", width=4,
                       command=lambda d=dev: self._delete(d)).pack(side="right", padx=2)

    # -- scan -------------------------------------------------------------- #
    def _scan(self):
        if tinytuya is None:
            messagebox.showerror("tinytuya missing", "Install tinytuya first.")
            return
        self.app.set_status("Scanning network (~6s)…")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            found = tinytuya.deviceScan(False, 6)
        except Exception as e:
            self.app.enqueue(("status", f"scan failed: {e}"))
            return
        results = [{"ip": info.get("ip", ip),
                    "id": info.get("gwId") or info.get("id", ""),
                    "version": str(info.get("version", "3.3"))}
                   for ip, info in (found or {}).items()]
        self.app.enqueue(("scan_results", results))

    def open_scan_results(self, results):
        known = {d["id"] for d in self.app.devices}
        new = [r for r in results if r["id"] not in known]
        if not new:
            self.app.set_status(f"Scan done — {len(results)} device(s), none new")
            return
        win = tk.Toplevel(self)
        win.title("Scan results")
        win.geometry("580x360")
        ttk.Label(win, padding=8,
                  text="Found these Tuya devices. Name each and paste its LOCAL KEY, "
                       "then Save. (Keys come from the tinytuya wizard — see README.)"
                  ).pack(fill="x")
        holder = ttk.Frame(win, padding=8)
        holder.pack(fill="both", expand=True)
        rows = []
        for r in new:
            fr = ttk.Frame(holder)
            fr.pack(fill="x", pady=2)
            chk = tk.BooleanVar(value=True)
            ttk.Checkbutton(fr, variable=chk).pack(side="left")
            ttk.Label(fr, text=r["ip"], width=15).pack(side="left", padx=2)
            name_e = ttk.Entry(fr, width=15)
            name_e.insert(0, f"Bulb {len(self.app.devices)+len(rows)+1}")
            name_e.pack(side="left", padx=2)
            key_e = ttk.Entry(fr, width=24)
            key_e.pack(side="left", padx=2)
            rows.append((r, chk, name_e, key_e))

        def do_save():
            added = 0
            for r, chk, name_e, key_e in rows:
                key, name = key_e.get().strip(), name_e.get().strip()
                if not (chk.get() and key and name):
                    continue
                self.app.devices.append({"name": name, "id": r["id"], "ip": r["ip"],
                                         "key": key, "version": r["version"]})
                self.app.active[name] = tk.BooleanVar(value=True)
                added += 1
            self.app.save_devices()
            self.refresh()
            self.app.set_status(f"Added {added} bulb(s)")
            win.destroy()

        ttk.Button(win, text="Save selected", command=do_save).pack(pady=8)

    def _add_manual(self):
        win = tk.Toplevel(self)
        win.title("Add bulb")
        fields = {}
        for i, (label, default) in enumerate(
                (("Name", ""), ("Device ID", ""), ("IP address", ""),
                 ("Local key", ""), ("Version", "3.3"))):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            e = ttk.Entry(win, width=30)
            e.insert(0, default)
            e.grid(row=i, column=1, padx=8, pady=4)
            fields[label] = e

        def do_add():
            name = fields["Name"].get().strip()
            dev = {"name": name, "id": fields["Device ID"].get().strip(),
                   "ip": fields["IP address"].get().strip(),
                   "key": fields["Local key"].get().strip(),
                   "version": fields["Version"].get().strip() or "3.3"}
            if not (dev["name"] and dev["id"] and dev["ip"] and dev["key"]):
                messagebox.showerror("Missing", "Name, ID, IP and key are required.")
                return
            self.app.devices.append(dev)
            self.app.active[name] = tk.BooleanVar(value=True)
            self.app.save_devices()
            self.refresh()
            self.app.set_status(f"Added {name}")
            win.destroy()

        ttk.Button(win, text="Add", command=do_add).grid(row=5, column=0, columnspan=2, pady=10)

    def _delete(self, dev):
        if not messagebox.askyesno("Delete", f"Remove {dev['name']}?"):
            return
        self.app.ctl.drop_bulb(dev["name"])
        self.app.devices = [d for d in self.app.devices if d["name"] != dev["name"]]
        self.app.active.pop(dev["name"], None)
        self.app.save_devices()
        self.refresh()
        self.app.set_status(f"Removed {dev['name']}")
