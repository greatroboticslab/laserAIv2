import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from process_raw import get_downloads_dir, select_folder_native, open_folder_native


class RecordDataFrame(ttk.Frame):
    def __init__(self, parent, moku_tab, display_tab):
        super().__init__(parent, padding=16)
        self.moku_tab = moku_tab
        self.display_tab = display_tab

        # UI vars
        self.base_folder = tk.StringVar(value=get_downloads_dir())
        self.folder_name = tk.StringVar(value="umd_logs")
        self.test_duration = tk.DoubleVar(value=15.0)
        self.num_runs = tk.IntVar(value=10)

        # Manual waveform metadata (used for the log header/filename now
        # that Moku is not used to drive or report the signal).
        self.manual_wave_type = tk.StringVar(value="Sine")
        self.manual_channel = tk.StringVar(value="1")
        self.manual_amplitude = tk.DoubleVar(value=1.0)
        self.manual_frequency = tk.DoubleVar(value=1.0)
        self.manual_offset = tk.DoubleVar(value=0.0)
        self.manual_phase = tk.DoubleVar(value=0.0)

        self.sample_freq = tk.IntVar(value=1000)

        self.status = tk.StringVar(value="Status: idle")

        # Worker control
        self._stop_flag = threading.Event()
        self._worker = None

        # Snapshot of waveform config taken at start of recording
        self._run_waveform_config = None

        # Progress modal state
        self._progress_win = None
        self._progress_bar = None
        self._progress_label = None
        self._progress_sub = None
        self._progress_eta = None
        self._progress_btn_stop = None

        # Progress bookkeeping
        self._run_started_at = None
        self._total_seconds = None
        self._current_file = ""

        self._build_ui()
        self._start_condition_monitor()

    # ---------- UI ----------
    def _build_ui(self):
        ttk.Label(self, text="Record Data", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")

        # Manual waveform info (Moku is not used - you fill this in for the
        # log header/filename; it does not drive any hardware).
        self.summary_frame = ttk.LabelFrame(self, text="Waveform info (manual entry - Moku not used)", padding=8)
        self.summary_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        ttk.Label(self.summary_frame, text="Type:").grid(row=0, column=0, sticky="e")
        ttk.Entry(self.summary_frame, textvariable=self.manual_wave_type, width=10).grid(row=0, column=1, sticky="w", padx=(4, 16))

        ttk.Label(self.summary_frame, text="Channel:").grid(row=0, column=2, sticky="e")
        ttk.Entry(self.summary_frame, textvariable=self.manual_channel, width=6).grid(row=0, column=3, sticky="w", padx=(4, 0))

        ttk.Label(self.summary_frame, text="Amplitude (Vpp):").grid(row=1, column=0, sticky="e", pady=(4, 0))
        ttk.Entry(self.summary_frame, textvariable=self.manual_amplitude, width=10).grid(row=1, column=1, sticky="w", padx=(4, 16), pady=(4, 0))

        ttk.Label(self.summary_frame, text="Frequency (Hz):").grid(row=1, column=2, sticky="e", pady=(4, 0))
        ttk.Entry(self.summary_frame, textvariable=self.manual_frequency, width=10).grid(row=1, column=3, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(self.summary_frame, text="Offset (V):").grid(row=2, column=0, sticky="e", pady=(4, 0))
        ttk.Entry(self.summary_frame, textvariable=self.manual_offset, width=10).grid(row=2, column=1, sticky="w", padx=(4, 16), pady=(4, 0))

        ttk.Label(self.summary_frame, text="Phase (deg):").grid(row=2, column=2, sticky="e", pady=(4, 0))
        ttk.Entry(self.summary_frame, textvariable=self.manual_phase, width=10).grid(row=2, column=3, sticky="w", padx=(4, 0), pady=(4, 0))

        # Save folder
        ttk.Label(self, text="Save to folder:").grid(row=2, column=0, sticky="e", pady=(10, 0))
        ttk.Entry(self, textvariable=self.base_folder, width=60).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(self, text="Change...", command=self._pick_folder).grid(row=2, column=2, padx=(8, 0), pady=(10, 0))

        ttk.Label(self, text="Subfolder name:").grid(row=3, column=0, sticky="e", pady=(6, 0))
        ttk.Entry(self, textvariable=self.folder_name, width=25).grid(row=3, column=1, sticky="w", pady=(6, 0))

        ttk.Label(self, text="Seconds per run:").grid(row=4, column=0, sticky="e", pady=(10, 0))
        ttk.Entry(self, textvariable=self.test_duration, width=10).grid(row=4, column=1, sticky="w", pady=(10, 0))

        ttk.Label(self, text="Number of recordings:").grid(row=5, column=0, sticky="e", pady=(6, 0))
        ttk.Entry(self, textvariable=self.num_runs, width=10).grid(row=5, column=1, sticky="w", pady=(6, 0))

        ttk.Label(self, text="Sample Frequency (Hz):").grid(row=6, column=0, sticky="e", pady=(6, 0))
        ttk.Entry(self, textvariable=self.sample_freq, width=10).grid(row=6, column=1, sticky="w", pady=(6, 0))

        btns = ttk.Frame(self)
        btns.grid(row=7, column=0, columnspan=3, sticky="w", pady=(14, 0))
        self.start_btn = ttk.Button(btns, text="Start Recording", command=self.start_recording)
        self.start_btn.pack(side="left")

        ttk.Label(self, textvariable=self.status).grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.columnconfigure(1, weight=1)

    def _pick_folder(self):
        p = select_folder_native("Select output folder")
        if p:
            self.base_folder.set(p)

    # ---------- Conditions ----------
    def _conditions_ok(self) -> bool:
        # Moku is optional: recording can run without it (single run, no
        # frequency sweep, placeholder waveform metadata in the header).
        if not getattr(self.display_tab, "is_mqtt_connected", lambda: False)():
            return False
        if not getattr(self.display_tab, "is_umd_running", lambda: False)():
            return False
        if not getattr(self.display_tab, "is_streaming", lambda: False)():
            return False
        return True

    def _start_condition_monitor(self):
        mqtt_ok = getattr(self.display_tab, "is_mqtt_connected", lambda: False)()
        umd_ok = getattr(self.display_tab, "is_umd_running", lambda: False)()
        stream_ok = getattr(self.display_tab, "is_streaming", lambda: False)()

        ok = mqtt_ok and umd_ok and stream_ok

        self.start_btn.config(state=("normal" if ok else "disabled"))

        self.status.set(
            ("Status: ready ✅ " if ok else "Status: waiting ❌ ")
            + f"| MQTT={mqtt_ok} uMD={umd_ok} Stream={stream_ok}"
        )

        self.after(300, self._start_condition_monitor)

    # ---------- Recording lifecycle ----------
    def start_recording(self):
        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Already running", "Recording is already in progress.")
            return
        if not self._conditions_ok():
            messagebox.showerror("Not ready", "Conditions not met yet.")
            return

        try:
            cfg = {
                "type": self.manual_wave_type.get().strip() or "Unspecified",
                "channel": self.manual_channel.get().strip() or "-",
                "amplitude": float(self.manual_amplitude.get()),
                "frequency": float(self.manual_frequency.get()),
                "offset": float(self.manual_offset.get()),
                "phase": float(self.manual_phase.get()),
            }
        except (tk.TclError, ValueError):
            messagebox.showerror("Invalid input", "Amplitude, Frequency, Offset, and Phase must be numbers.")
            return

        try:
            dur = float(self.test_duration.get())
            runs = int(self.num_runs.get())
            if dur <= 0:
                raise ValueError("Seconds per run must be > 0.")
            if runs <= 0:
                raise ValueError("Number of recordings must be at least 1.")
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self._run_waveform_config = cfg
        self._stop_flag.clear()
        self._run_started_at = time.time()
        self._current_file = ""
        self._total_seconds = dur * runs

        self._open_progress_modal()

        self._worker = threading.Thread(target=self._run_sequence, daemon=True)
        self._worker.start()

        self._pump_progress_ui()

    def _open_progress_modal(self):
        w = tk.Toplevel(self)
        w.title("Recording…")
        w.resizable(False, False)

        w.transient(self.winfo_toplevel())
        w.grab_set()

        frm = ttk.Frame(w, padding=16)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Recording in progress", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")

        self._progress_label = ttk.Label(frm, text="Preparing…")
        self._progress_label.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self._progress_sub = ttk.Label(frm, text="")
        self._progress_sub.grid(row=2, column=0, sticky="w", pady=(2, 0))

        self._progress_bar = ttk.Progressbar(frm, length=380, mode="determinate", maximum=100)
        self._progress_bar.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        self._progress_eta = ttk.Label(frm, text="Elapsed: 0s   Remaining: --")
        self._progress_eta.grid(row=4, column=0, sticky="w", pady=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, sticky="e", pady=(12, 0))
        self._progress_btn_stop = ttk.Button(btns, text="Stop", command=self._stop_from_modal)
        self._progress_btn_stop.pack(side="right")

        self._progress_win = w
        w.protocol("WM_DELETE_WINDOW", self._stop_from_modal)

    def _stop_from_modal(self):
        self._stop_flag.set()
        if self._progress_label:
            self._progress_label.config(text="Stopping…")
        if self._progress_btn_stop:
            self._progress_btn_stop.config(state="disabled")

    def _close_progress_modal(self):
        if self._progress_win is not None:
            try:
                self._progress_win.grab_release()
            except Exception:
                pass
            try:
                self._progress_win.destroy()
            except Exception:
                pass

        self._progress_win = None
        self._progress_bar = None
        self._progress_label = None
        self._progress_sub = None
        self._progress_eta = None
        self._progress_btn_stop = None

    def _pump_progress_ui(self):
        if self._progress_win is None:
            return

        now = time.time()
        elapsed = max(0.0, now - (self._run_started_at or now))
        total = max(0.001, float(self._total_seconds or 0.001))
        pct = min(100.0, (elapsed / total) * 100.0)
        remaining = max(0.0, total - elapsed)

        if self._progress_bar is not None:
            self._progress_bar["value"] = pct

        if self._progress_label is not None:
            wave_type = (self._run_waveform_config or {}).get("type", "Waveform")
            self._progress_label.config(text=f"Recording {wave_type}…")

        if self._progress_sub is not None:
            if self._current_file:
                self._progress_sub.config(text=f"File: {os.path.basename(self._current_file)}")
            else:
                self._progress_sub.config(text="")

        if self._progress_eta is not None:
            self._progress_eta.config(text=f"Elapsed: {int(elapsed)}s   Remaining: {int(remaining)}s")

        if self._worker and (not self._worker.is_alive()):
            self._close_progress_modal()
            return

        self.after(200, self._pump_progress_ui)

    # ---------- Worker ----------
    def _run_sequence(self):
        out_dir = None
        try:
            base = self.base_folder.get().strip()
            name = self.folder_name.get().strip() or "umd_logs"
            out_dir = os.path.join(base, name)
            os.makedirs(out_dir, exist_ok=True)

            fs = int(self.sample_freq.get())
            dur = float(self.test_duration.get())
            runs = int(self.num_runs.get())

            cfg = dict(self._run_waveform_config or {})
            wave_type = cfg.get("type", "Unspecified")
            header = self._build_header(fs=fs, cfg=cfg)

            # Record multiple separate files back-to-back.
            # There is no pause between runs unless the user presses Stop.
            for run_num in range(1, runs + 1):
                if self._stop_flag.is_set():
                    break

                filename = os.path.join(
                    out_dir,
                    f"log_{wave_type.lower()}_run{run_num:02d}.txt"
                )
                self._current_file = filename

                self._set_status_mainthread(
                    f"Recording run {run_num}/{runs} -> {os.path.basename(filename)}"
                )

                t_end = time.time() + dur
                with open(filename, "w", encoding="utf-8") as fp:
                    fp.write(header)
                    fp.write(f"Run = {run_num} of {runs}\n\n")

                    serial = 1
                    while time.time() < t_end and not self._stop_flag.is_set():
                        d = getattr(self.display_tab, "last_d_counts", None)
                        if d is not None:
                            fp.write(f"D:{d} N:{serial}\n")
                            serial += 1
                        time.sleep(0.001)

            if self._stop_flag.is_set():
                self._set_status_mainthread("Stopped by user.")
            else:
                self._set_status_mainthread(
                    f"Done. Completed {runs} recording(s). Opening output folder…"
                )
                if out_dir:
                    open_folder_native(out_dir)

        except Exception as e:
            self._set_status_mainthread(f"Error: {e}")

    @staticmethod
    def _build_header(fs: int, cfg: dict) -> str:
        parts = [
            f"Sample Frequency = {fs} Hz",
            f"Voltage = {cfg.get('amplitude', 0):g} Vpp",
            f"Waveform = {cfg.get('type', 'Unspecified')}",
            f"Channel = {cfg.get('channel', '-')}",
            f"Test Frequency = {cfg.get('frequency', 0):g} Hz",
            f"Offset = {cfg.get('offset', 0):g} V",
            f"Phase = {cfg.get('phase', 0):g} deg",
        ]

        return " ".join(parts) + "\n\n"

    def _set_status_mainthread(self, text: str):
        self.after(0, lambda: self.status.set(f"Status: {text}"))