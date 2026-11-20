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
