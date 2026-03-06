"""LaPian GUI — tkinter-based graphical interface for batch video transcoding."""

import os
import sys
import threading
from pathlib import Path
from typing import Optional

from . import __version__
from .core import (
    PRESET_NAMES,
    RESOLUTION_CHOICES,
    FPS_CHOICES,
    DEFAULT_OUTPUT_DIR,
    SUPPORTED_EXTENSIONS,
    check_ffmpeg,
    detect_hw_encoders,
    collect_input_files,
    build_output_path,
    TranscodeJob,
    BatchSummary,
    run_batch,
    run_deadvert,
    format_timestamp,
)
from .i18n import _t


def launch_gui():
    """Launch the tkinter GUI."""
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, scrolledtext, messagebox
    except ImportError:
        print(
            "ERROR: tkinter is not available.\n"
            "Install it with:\n"
            "  Ubuntu/Debian: sudo apt install python3-tk\n"
            "  Fedora: sudo dnf install python3-tkinter\n"
            "  macOS: brew install python-tk",
            file=sys.stderr,
        )
        sys.exit(1)

    class TranscoderGUI:
        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title("LaPian (拉片)")
            self.root.minsize(950, 680)
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(2, weight=1)

            self.cancel_event = threading.Event()
            self.worker_thread = None
            self.file_paths = []

            # Pick a monospace font that supports CJK characters
            self._mono_font = self._pick_mono_font()
            # Pick a proportional font for lists that reliably renders CJK
            self._list_font = self._pick_list_font()

            self._build_ui()
            self._detect_hw_on_startup()

        @staticmethod
        def _pick_list_font():
            """Return a (family, size) tuple for the file list with CJK support."""
            import tkinter.font as tkfont
            families = set(tkfont.families())
            for name in (
                "Noto Sans CJK SC",
                "WenQuanYi Micro Hei",
                "WenQuanYi Zen Hei",
                "Microsoft YaHei",
                "SimSun",
                "PingFang SC",
                "Hiragino Sans",
            ):
                if name in families:
                    return (name, 9)
            return ("TkDefaultFont", 9)

        @staticmethod
        def _pick_mono_font():
            """Return a (family, size) tuple for a monospace font with CJK support."""
            import tkinter.font as tkfont
            families = set(tkfont.families())
            for name in (
                "WenQuanYi Micro Hei Mono",
                "WenQuanYi Zen Hei Mono",
                "Noto Sans Mono CJK SC",
                "Source Han Mono SC",
                "Microsoft YaHei Mono",
            ):
                if name in families:
                    try:
                        f = tkfont.Font(family=name, size=9)
                        if f.measure("\u4e2d") > 0:
                            return (name, 9)
                    except Exception:
                        continue
            for name in ("Consolas", "Courier New"):
                if name in families:
                    return (name, 9)
            return ("TkFixedFont", 9)

        def _build_ui(self):
            import tkinter as tk
            from tkinter import ttk, scrolledtext

            # --- Top toolbar ---
            toolbar = ttk.Frame(self.root, padding=5)
            toolbar.grid(row=0, column=0, sticky="ew")

            ttk.Button(toolbar, text=_t("add_files"), command=self._add_files).pack(
                side="left", padx=2)
            ttk.Button(toolbar, text=_t("add_directory"), command=self._add_directory).pack(
                side="left", padx=2)
            ttk.Button(toolbar, text=_t("clear_list"), command=self._clear_list).pack(
                side="left", padx=2)
            ttk.Button(toolbar, text=_t("about"), command=self._show_about).pack(
                side="right", padx=2)

            self.file_count_var = tk.StringVar(value=_t("items", count=0))
            ttk.Label(toolbar, textvariable=self.file_count_var).pack(
                side="left", padx=10)

            # --- Middle area: file list + options ---
            mid = ttk.PanedWindow(self.root, orient="horizontal")
            mid.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
            self.root.rowconfigure(1, weight=1)

            # File list
            list_frame = ttk.LabelFrame(mid, text=_t("file_queue"), padding=5)
            self.file_listbox = tk.Listbox(
                list_frame, selectmode="extended",
                font=self._list_font,
            )
            list_sb = ttk.Scrollbar(
                list_frame, orient="vertical", command=self.file_listbox.yview)
            self.file_listbox.configure(yscrollcommand=list_sb.set)
            self.file_listbox.pack(side="left", fill="both", expand=True)
            list_sb.pack(side="right", fill="y")
            mid.add(list_frame, weight=3)

            # Options panel
            opt_frame = ttk.LabelFrame(mid, text=_t("options"), padding=10)
            mid.add(opt_frame, weight=1)

            row = 0
            ttk.Label(opt_frame, text=_t("preset")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.preset_var = tk.StringVar(value="android")
            preset_cb = ttk.Combobox(
                opt_frame, textvariable=self.preset_var,
                values=list(PRESET_NAMES), state="readonly", width=15,
            )
            preset_cb.grid(row=row, column=1, sticky="ew", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("output_dir")).grid(
                row=row, column=0, sticky="w", pady=3)
            out_frame = ttk.Frame(opt_frame)
            out_frame.grid(row=row, column=1, sticky="ew", pady=3)
            self.output_dir_var = tk.StringVar(
                value=str(Path(DEFAULT_OUTPUT_DIR).resolve()))
            ttk.Entry(out_frame, textvariable=self.output_dir_var, width=20).pack(
                side="left", fill="x", expand=True)
            ttk.Button(out_frame, text="...", width=3,
                       command=self._browse_output).pack(side="right")

            row += 1
            ttk.Label(opt_frame, text=_t("hw_encoder")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.hw_label_var = tk.StringVar(value=_t("detecting"))
            ttk.Label(opt_frame, textvariable=self.hw_label_var,
                      wraplength=200).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Separator(opt_frame, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=8)

            row += 1
            ttk.Label(opt_frame, text=_t("crf")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.crf_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.crf_var, width=8).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("resolution")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.resolution_var = tk.StringVar(value="")
            ttk.Combobox(
                opt_frame, textvariable=self.resolution_var,
                values=[""] + RESOLUTION_CHOICES,
                state="readonly", width=12,
            ).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("bitrate")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.bitrate_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.bitrate_var, width=10).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("video_fps")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.video_fps_var = tk.StringVar(value="")
            ttk.Combobox(
                opt_frame, textvariable=self.video_fps_var,
                values=[""] + [str(f) for f in FPS_CHOICES],
                state="readonly", width=8,
            ).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("gif_fps")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.fps_var = tk.StringVar(value="10")
            ttk.Entry(opt_frame, textvariable=self.fps_var, width=8).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("max_width")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.width_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.width_var, width=8).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("audio_fmt")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.audio_fmt_var = tk.StringVar(value="mp3")
            ttk.Combobox(
                opt_frame, textvariable=self.audio_fmt_var,
                values=["mp3", "aac"], state="readonly", width=8,
            ).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            self.recursive_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(opt_frame, text=_t("recursive"),
                            variable=self.recursive_var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            self.dryrun_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(opt_frame, text=_t("dry_run"),
                            variable=self.dryrun_var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            self.verbose_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(opt_frame, text=_t("verbose"),
                            variable=self.verbose_var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("encoder")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.encoder_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.encoder_var, width=15).grid(
                row=row, column=1, sticky="w", pady=3)

            # -- Deadvert section --
            row += 1
            ttk.Separator(opt_frame, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=8)

            row += 1
            self.deadvert_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(opt_frame, text=_t("deadvert"),
                            variable=self.deadvert_var,
                            command=self._toggle_deadvert).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("deadvert_method")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.deadvert_method_var = tk.StringVar(value="audio")
            self.deadvert_method_cb = ttk.Combobox(
                opt_frame, textvariable=self.deadvert_method_var,
                values=["audio", "video"], state="disabled", width=12,
            )
            self.deadvert_method_cb.grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("deadvert_min_dur")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.deadvert_min_dur_var = tk.StringVar(value="5.0")
            self.deadvert_min_dur_entry = ttk.Entry(
                opt_frame, textvariable=self.deadvert_min_dur_var,
                width=8, state="disabled",
            )
            self.deadvert_min_dur_entry.grid(
                row=row, column=1, sticky="w", pady=3)

            opt_frame.columnconfigure(1, weight=1)

            # --- Progress area ---
            prog_frame = ttk.LabelFrame(self.root, text=_t("progress"), padding=5)
            prog_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)

            ttk.Label(prog_frame, text=_t("file")).grid(row=0, column=0, sticky="w")
            self.file_progress_var = tk.DoubleVar(value=0)
            self.file_progress_bar = ttk.Progressbar(
                prog_frame, variable=self.file_progress_var,
                maximum=100, length=400,
            )
            self.file_progress_bar.grid(row=0, column=1, sticky="ew", padx=5)
            self.file_progress_label = tk.StringVar(value="0%")
            ttk.Label(prog_frame, textvariable=self.file_progress_label, width=15).grid(
                row=0, column=2, sticky="w")

            ttk.Label(prog_frame, text=_t("overall")).grid(row=1, column=0, sticky="w")
            self.overall_progress_var = tk.DoubleVar(value=0)
            self.overall_progress_bar = ttk.Progressbar(
                prog_frame, variable=self.overall_progress_var,
                maximum=100, length=400,
            )
            self.overall_progress_bar.grid(row=1, column=1, sticky="ew", padx=5)
            self.overall_progress_label = tk.StringVar(value="0%")
            ttk.Label(prog_frame, textvariable=self.overall_progress_label, width=15).grid(
                row=1, column=2, sticky="w")
            prog_frame.columnconfigure(1, weight=1)

            # --- Buttons ---
            btn_frame = ttk.Frame(self.root, padding=5)
            btn_frame.grid(row=3, column=0, sticky="ew", padx=5)

            self.start_btn = ttk.Button(
                btn_frame, text=_t("start"), command=self._start)
            self.start_btn.pack(side="left", padx=5)
            self.cancel_btn = ttk.Button(
                btn_frame, text=_t("cancel"), command=self._cancel, state="disabled")
            self.cancel_btn.pack(side="left", padx=5)

            # --- Log area ---
            log_frame = ttk.LabelFrame(self.root, text=_t("log"), padding=5)
            log_frame.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
            self.root.rowconfigure(4, weight=2)

            self.log_area = scrolledtext.ScrolledText(
                log_frame, height=10, state="disabled",
                font=self._mono_font, wrap="word",
            )
            self.log_area.pack(fill="both", expand=True)
            self.log_area.tag_config("INFO", foreground="black")
            self.log_area.tag_config("DONE", foreground="green")
            self.log_area.tag_config("WARN", foreground="orange")
            self.log_area.tag_config("ERROR", foreground="red")

        def _log(self, msg: str, tag: str = "INFO"):
            def _do():
                self.log_area.configure(state="normal")
                self.log_area.insert("end", msg + "\n", tag)
                self.log_area.see("end")
                self.log_area.configure(state="disabled")
            self.root.after(0, _do)

        def _add_files(self):
            from tkinter import filedialog
            exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
            paths = filedialog.askopenfilenames(
                title=_t("select_video"),
                filetypes=[(_t("video_files"), exts), (_t("all_files"), "*.*")],
            )
            for p in paths:
                if p not in self.file_paths:
                    self.file_paths.append(p)
                    self.file_listbox.insert("end", os.path.basename(p))
            self._update_count()

        def _add_directory(self):
            from tkinter import filedialog
            d = filedialog.askdirectory(title=_t("select_dir"))
            if d:
                if d not in self.file_paths:
                    self.file_paths.append(d)
                    self.file_listbox.insert("end", f"{_t('dir_prefix')} {d}")
                self._update_count()

        def _clear_list(self):
            self.file_paths.clear()
            self.file_listbox.delete(0, "end")
            self._update_count()

        def _update_count(self):
            self.file_count_var.set(_t("items", count=len(self.file_paths)))

        def _browse_output(self):
            from tkinter import filedialog
            d = filedialog.askdirectory(title=_t("select_output"))
            if d:
                self.output_dir_var.set(d)

        def _show_about(self):
            from tkinter import messagebox
            messagebox.showinfo(
                _t("about"),
                _t("about_text", version=__version__),
            )

        def _toggle_deadvert(self):
            enabled = self.deadvert_var.get()
            state = "readonly" if enabled else "disabled"
            entry_state = "normal" if enabled else "disabled"
            self.deadvert_method_cb.configure(state=state)
            self.deadvert_min_dur_entry.configure(state=entry_state)

        def _show_deadvert_confirm(self, dv_summary):
            """Show a modal dialog for deadvert confirmation. Thread-safe."""
            import tkinter as tk
            from tkinter import ttk

            result_event = threading.Event()
            user_choice = [False]

            def _show():
                dlg = tk.Toplevel(self.root)
                dlg.title(_t("deadvert_confirm_title"))
                dlg.transient(self.root)
                dlg.grab_set()
                dlg.minsize(500, 350)

                tree_frame = ttk.Frame(dlg, padding=10)
                tree_frame.pack(fill="both", expand=True)

                tree = ttk.Treeview(
                    tree_frame,
                    columns=("start", "end", "duration"),
                    show="tree headings", height=12,
                )
                tree.heading("start", text="Start")
                tree.heading("end", text="End")
                tree.heading("duration", text="Duration")
                tree.column("start", width=100)
                tree.column("end", width=100)
                tree.column("duration", width=80)

                for r in dv_summary.results:
                    if r.ad_segments:
                        vid_id = tree.insert(
                            "", "end",
                            text=os.path.basename(r.video_path),
                            open=True,
                        )
                        for ad in r.ad_segments:
                            tree.insert(
                                vid_id, "end", text="",
                                values=(
                                    format_timestamp(ad.start),
                                    format_timestamp(ad.end),
                                    f"{ad.end - ad.start:.1f}s",
                                ),
                            )

                sb = ttk.Scrollbar(tree_frame, orient="vertical",
                                   command=tree.yview)
                tree.configure(yscrollcommand=sb.set)
                tree.pack(side="left", fill="both", expand=True)
                sb.pack(side="right", fill="y")

                ttk.Label(
                    dlg,
                    text=_t("deadvert_total_removed",
                            time=dv_summary.total_time_removed),
                    padding=5,
                ).pack()

                btn_frame = ttk.Frame(dlg, padding=10)
                btn_frame.pack()

                def _proceed():
                    user_choice[0] = True
                    dlg.destroy()
                    result_event.set()

                def _cancel():
                    user_choice[0] = False
                    dlg.destroy()
                    result_event.set()

                ttk.Button(
                    btn_frame, text=_t("deadvert_proceed"),
                    command=_proceed,
                ).pack(side="left", padx=10)
                ttk.Button(
                    btn_frame, text=_t("deadvert_cancel_trim"),
                    command=_cancel,
                ).pack(side="left", padx=10)

                dlg.protocol("WM_DELETE_WINDOW", _cancel)

            self.root.after(0, _show)
            result_event.wait()
            return user_choice[0]

        def _detect_hw_on_startup(self):
            def _detect():
                try:
                    check_ffmpeg()
                    encoders = detect_hw_encoders()
                    hw = [k for k, v in encoders.items() if v and k not in (
                        "libx264", "libx265", "libmp3lame", "aac", "libvpx")]
                    if hw:
                        self.root.after(0, lambda: self.hw_label_var.set(
                            ", ".join(sorted(hw))))
                        self._log(_t("hw_detected", encoders=", ".join(sorted(hw))), "DONE")
                    else:
                        self.root.after(0, lambda: self.hw_label_var.set(
                            _t("none_sw_only")))
                        self._log(_t("no_hw"), "WARN")
                except RuntimeError as e:
                    self.root.after(0, lambda: self.hw_label_var.set(_t("ffmpeg_not_found")))
                    self._log(f"ERROR: {e}", "ERROR")
                    self.root.after(0, lambda: self.start_btn.configure(state="disabled"))

            threading.Thread(target=_detect, daemon=True).start()

        def _start(self):
            from tkinter import messagebox

            if not self.file_paths:
                messagebox.showwarning(_t("no_files_title"), _t("no_files_msg"))
                return

            preset = self.preset_var.get()
            output_dir = self.output_dir_var.get()
            recursive = self.recursive_var.get()
            dry_run = self.dryrun_var.get()

            crf_str = self.crf_var.get().strip()
            crf = int(crf_str) if crf_str.isdigit() else None
            fps_str = self.fps_var.get().strip()
            fps = int(fps_str) if fps_str.isdigit() else 10
            width_str = self.width_var.get().strip()
            width = int(width_str) if width_str.isdigit() else None
            audio_fmt = self.audio_fmt_var.get()
            encoder = self.encoder_var.get().strip() or None
            resolution = self.resolution_var.get().strip() or None
            bitrate = self.bitrate_var.get().strip() or None
            vfps_str = self.video_fps_var.get().strip()
            video_fps = int(vfps_str) if vfps_str.isdigit() else None

            self.cancel_event.clear()
            self.start_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
            self.file_progress_var.set(0)
            self.overall_progress_var.set(0)
            self.file_progress_label.set("0%")
            self.overall_progress_label.set("0%")

            self._log(_t("starting_batch", preset=preset, output=output_dir), "INFO")

            def _worker():
                files = collect_input_files(self.file_paths, recursive)
                if not files:
                    self._log(_t("no_video_found"), "ERROR")
                    self.root.after(0, self._on_complete, None)
                    return

                self._log(_t("found_files", count=len(files)), "INFO")
                out_dir = Path(output_dir)
                out_dir.mkdir(parents=True, exist_ok=True)

                def _logmsg(msg):
                    verbose = self.verbose_var.get()
                    if verbose or not (
                        msg.startswith("frame=") or msg.startswith("size=")
                    ):
                        tag = "INFO"
                        if "[DONE]" in msg:
                            tag = "DONE"
                        elif "[FAIL]" in msg or "ERROR" in msg:
                            tag = "ERROR"
                        self._log(msg, tag)

                # -- Deadvert preprocessing --
                use_deadvert = self.deadvert_var.get()
                if use_deadvert:
                    video_paths = [str(f) for f, _ in files]
                    dv_method = self.deadvert_method_var.get()
                    dv_min_str = self.deadvert_min_dur_var.get().strip()
                    try:
                        dv_min_dur = float(dv_min_str)
                    except ValueError:
                        dv_min_dur = 5.0

                    dv_summary = run_deadvert(
                        video_paths,
                        method=dv_method,
                        threshold=2,
                        min_duration=dv_min_dur,
                        output_dir=str(out_dir),
                        confirm_cb=self._show_deadvert_confirm,
                        log_cb=_logmsg,
                        cancel_event=self.cancel_event,
                    )

                    if self.cancel_event.is_set():
                        self.root.after(0, self._on_complete, None)
                        return

                    if dv_summary.total_ads_found > 0:
                        self._log(
                            _t("deadvert_found",
                                count=dv_summary.total_ads_found,
                                videos=dv_summary.videos_with_ads),
                            "DONE",
                        )

                    trimmed_files = []
                    for r in dv_summary.results:
                        if r.trimmed_output and os.path.isfile(r.trimmed_output):
                            trimmed_files.append(
                                (Path(r.trimmed_output), Path(".")))
                        else:
                            trimmed_files.append(
                                (Path(r.video_path), Path(".")))
                    files_to_use = trimmed_files
                else:
                    files_to_use = files

                jobs = []
                for f, rel_subdir in files_to_use:
                    out = build_output_path(
                        f, out_dir, preset, audio_fmt,
                        relative_subdir=rel_subdir,
                    )
                    job = TranscodeJob(
                        input_path=str(f),
                        output_path=str(out),
                        preset=preset,
                        options={
                            "encoder": encoder,
                            "crf": crf,
                            "fps": fps,
                            "width": width,
                            "audio_format": audio_fmt,
                            "resolution": resolution,
                            "bitrate": bitrate,
                            "video_fps": video_fps,
                        },
                    )
                    jobs.append(job)

                def _progress(file_pct, overall_pct, idx):
                    self.root.after(0, lambda: self.file_progress_var.set(
                        max(0, file_pct)))
                    self.root.after(0, lambda: self.overall_progress_var.set(
                        overall_pct))
                    self.root.after(0, lambda: self.file_progress_label.set(
                        f"{max(0, file_pct):.1f}%  file {idx + 1}/{len(jobs)}"))
                    self.root.after(0, lambda: self.overall_progress_label.set(
                        f"{overall_pct:.1f}%"))

                summary = run_batch(
                    jobs, _progress, _logmsg, self.cancel_event, dry_run,
                )
                self.root.after(0, self._on_complete, summary)

            self.worker_thread = threading.Thread(target=_worker, daemon=True)
            self.worker_thread.start()

        def _cancel(self):
            self.cancel_event.set()
            self._log(_t("cancel_requested"), "WARN")
            self.cancel_btn.configure(state="disabled")

        def _on_complete(self, summary: Optional[BatchSummary]):
            from tkinter import messagebox

            self.start_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")

            if summary is None:
                return

            self.file_progress_var.set(100)
            self.overall_progress_var.set(100)

            msg = (
                f"{_t('batch_complete')}\n\n"
                f"{_t('done')}: {summary.done}\n"
                f"{_t('failed')}: {summary.failed}\n"
                f"{_t('skipped')}: {summary.skipped}\n"
                f"{_t('time_elapsed')}: {summary.elapsed:.1f}s"
            )
            if summary.failed_files:
                msg += f"\n\n{_t('failed_files')}:\n" + "\n".join(
                    f"  - {os.path.basename(f)}" for f in summary.failed_files
                )

            self._log(
                "\n" + _t("batch_summary",
                           done=summary.done, failed=summary.failed,
                           skipped=summary.skipped, elapsed=summary.elapsed),
                "DONE" if summary.failed == 0 else "WARN",
            )

            messagebox.showinfo(_t("batch_complete_title"), msg)

    root = tk.Tk()
    app = TranscoderGUI(root)
    root.mainloop()
