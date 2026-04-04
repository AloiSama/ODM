# OpenDroneMap - display.py
# Textual progress interface for the ODM pipeline
#
# Copyright (c) OpenDroneMap Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import os, sys, time, re, threading, shutil

# NOTE: Do NOT import opendm.log here (circular import).
# Use print() directly for display output.

STAGE_DISPLAY_NAMES = {
    'dataset': 'Dataset',
    'split': 'Split',
    'merge': 'Merge',
    'opensfm': 'OpenSfM',
    'openmvs': 'OpenMVS',
    'odm_filterpoints': 'Filter Points',
    'odm_meshing': 'Meshing',
    'mvs_texturing': 'Texturing',
    'odm_georeferencing': 'Georeferencing',
    'odm_dem': 'DEM',
    'odm_orthophoto': 'Orthophoto',
    'odm_report': 'Report',
    'odm_postprocess': 'PostProcess',
}

# Use ASCII on Windows, box-drawing on Unix
if sys.platform == 'win32':
    BOX_TL = '+'; BOX_TR = '+'; BOX_BL = '+'; BOX_BR = '+'
    BOX_H = '-'; BOX_V = '|'
    BOX_LT = '+'; BOX_RT = '+'; BOX_TT = '+'; BOX_BT = '+'; BOX_X = '+'
    SYM_DONE = '*'; SYM_RUN = '>'; SYM_PENDING = '.'; SYM_FAIL = 'X'
    BAR_FILL = '#'; BAR_EMPTY = '-'
else:
    BOX_TL = '\u250c'; BOX_TR = '\u2510'; BOX_BL = '\u2514'; BOX_BR = '\u2518'
    BOX_H = '\u2500'; BOX_V = '\u2502'
    BOX_LT = '\u251c'; BOX_RT = '\u2524'; BOX_TT = '\u252c'; BOX_BT = '\u2534'; BOX_X = '\u253c'
    SYM_DONE = '\u2714'; SYM_RUN = '\u25b8'; SYM_PENDING = '\u00b7'; SYM_FAIL = '\u2718'
    BAR_FILL = '\u2588'; BAR_EMPTY = '\u2591'

RENDER_INTERVAL = 0.5  # seconds between TTY redraws


class StageInfo:
    def __init__(self, name):
        self.name = name
        self.display_name = STAGE_DISPLAY_NAMES.get(name, name)
        self.status = 'pending'  # pending, running, done, error
        self.start_time = None
        self.elapsed = 0.0
        self.progress_pct = 0.0
        self.detail_line = ''


class ETAEstimator:
    def __init__(self, benchmarking_file=None):
        self.historical = {}
        if benchmarking_file and os.path.exists(benchmarking_file):
            self._load_history(benchmarking_file)

    def _load_history(self, path):
        """Parse benchmarking.txt: '{stage} runtime: {seconds} seconds'"""
        try:
            with open(path) as f:
                for line in f:
                    m = re.match(r'(\S+)\s+runtime:\s+([\d.]+)\s+seconds', line)
                    if m:
                        self.historical[m.group(1)] = float(m.group(2))
        except Exception:
            pass

    def estimate_remaining(self, stage_name, elapsed, progress_pct):
        """Return estimated seconds remaining, or None if unknown."""
        if progress_pct <= 0:
            hist = self.historical.get(stage_name)
            if hist and hist > elapsed:
                return hist - elapsed
            return None

        # Linear extrapolation from current progress
        current_estimate = (elapsed / progress_pct) * (100.0 - progress_pct)

        # Blend with historical if available and early in stage
        hist = self.historical.get(stage_name)
        if hist and progress_pct < 50:
            hist_estimate = hist * (1.0 - progress_pct / 100.0)
            weight = progress_pct / 50.0  # 0 at 0%, 1 at 50%
            return current_estimate * weight + hist_estimate * (1.0 - weight)

        return current_estimate


class ProgressDisplay:
    def __init__(self, stages_list, version, is_verbose=False):
        self.stages = [StageInfo(name) for name in stages_list]
        self._stage_map = {s.name: s for s in self.stages}
        self.version = version
        self.is_verbose = is_verbose
        self.is_tty = sys.stdout.isatty() and os.environ.get('TERM') != 'dumb'
        self.image_count = 0
        self.global_start_time = time.monotonic()
        self.current_stage = None
        self._lock = threading.Lock()
        self._last_render_time = 0
        self._last_frame_lines = 0
        self._last_log_msg = ''
        self._nontty_last_pct_bucket = {}  # stage -> last printed pct bucket
        self._eta = ETAEstimator()
        self._degraded = False  # set True on render error

    def set_benchmarking_file(self, path):
        self._eta = ETAEstimator(path)

    def set_image_count(self, count):
        self.image_count = count

    def stage_start(self, name):
        with self._lock:
            stage = self._stage_map.get(name)
            if stage is None:
                return
            stage.status = 'running'
            stage.start_time = time.monotonic()
            stage.progress_pct = 0.0
            stage.detail_line = ''
            self.current_stage = name

            if not self.is_verbose:
                if self.is_tty and not self._degraded:
                    self._render_tty()
                else:
                    self._nontty_stage_start(stage)

    def stage_end(self, name):
        with self._lock:
            stage = self._stage_map.get(name)
            if stage is None:
                return
            stage.status = 'done'
            if stage.start_time is not None:
                stage.elapsed = time.monotonic() - stage.start_time
            stage.progress_pct = 100.0

            if not self.is_verbose:
                if self.is_tty and not self._degraded:
                    self._render_tty()
                else:
                    self._nontty_stage_end(stage)

    def update_progress(self, name, pct, detail=None):
        with self._lock:
            stage = self._stage_map.get(name)
            if stage is None:
                return
            stage.progress_pct = max(0.0, min(100.0, pct))
            if detail is not None:
                stage.detail_line = detail
            if stage.start_time is not None:
                stage.elapsed = time.monotonic() - stage.start_time

            if not self.is_verbose:
                if self.is_tty and not self._degraded:
                    self._maybe_render_tty()
                else:
                    self._nontty_progress(stage)

    def log_message(self, level, msg):
        with self._lock:
            self._last_log_msg = '[%s] %s' % (level, msg)

            if not self.is_verbose:
                if self.is_tty and not self._degraded:
                    self._maybe_render_tty()

    def subprocess_line(self, line):
        from opendm.output_parsers import parse_line
        with self._lock:
            if self.current_stage is not None:
                result = parse_line(line.strip(), self.current_stage)
                if result:
                    pct, detail = result
                    stage = self._stage_map.get(self.current_stage)
                    if stage:
                        stage.progress_pct = max(stage.progress_pct, pct)
                        if detail:
                            stage.detail_line = detail
                        if stage.start_time is not None:
                            stage.elapsed = time.monotonic() - stage.start_time

            if not self.is_verbose:
                if self.is_tty and not self._degraded:
                    self._maybe_render_tty()

    def show_summary(self):
        """Print the final summary table."""
        total_elapsed = time.monotonic() - self.global_start_time

        # Determine widths
        name_w = 20
        time_w = 8
        detail_w = 22
        inner_w = name_w + time_w + detail_w + 8  # separators + padding

        lines = []
        lines.append(BOX_TL + BOX_H * (inner_w) + BOX_TR)

        status_sym = SYM_DONE
        status_text = 'Processing Complete'
        for s in self.stages:
            if s.status == 'error':
                status_sym = SYM_FAIL
                status_text = 'Processing Failed'
                break

        total_str = _format_time(total_elapsed)
        header = '  %s %s' % (status_sym, status_text)
        total_part = 'Total: %s  ' % total_str
        pad = inner_w - len(header) - len(total_part)
        if pad < 1:
            pad = 1
        lines.append(BOX_V + header + ' ' * pad + total_part + BOX_V)

        lines.append(BOX_LT + BOX_H * (name_w + 2) + BOX_TT + BOX_H * (time_w + 2) + BOX_TT + BOX_H * (detail_w + 2) + BOX_RT)
        lines.append(BOX_V + '  %-*s' % (name_w, 'Stage') + BOX_V + ' %-*s' % (time_w, 'Time') + ' ' + BOX_V + ' %-*s' % (detail_w, 'Detail') + ' ' + BOX_V)
        lines.append(BOX_LT + BOX_H * (name_w + 2) + BOX_X + BOX_H * (time_w + 2) + BOX_X + BOX_H * (detail_w + 2) + BOX_RT)

        for s in self.stages:
            if s.status == 'pending':
                continue

            if s.status == 'error':
                sym = SYM_FAIL
            else:
                sym = SYM_DONE

            time_str = _format_time(s.elapsed) if s.elapsed > 0 else ''
            detail = s.detail_line[:detail_w] if s.detail_line else ''

            lines.append(BOX_V + '  %s %-*s' % (sym, name_w - 2, s.display_name) + BOX_V + ' %-*s' % (time_w, time_str) + ' ' + BOX_V + ' %-*s' % (detail_w, detail) + ' ' + BOX_V)

        lines.append(BOX_BL + BOX_H * (name_w + 2) + BOX_BT + BOX_H * (time_w + 2) + BOX_BT + BOX_H * (detail_w + 2) + BOX_BR)

        # Clear TTY display area before printing summary
        if self.is_tty and self._last_frame_lines > 0:
            sys.stdout.write('\033[%dA' % self._last_frame_lines)
            sys.stdout.write('\033[J')
            self._last_frame_lines = 0

        print('\n'.join(lines))
        sys.stdout.flush()

    # --- TTY rendering ---

    def _maybe_render_tty(self):
        now = time.monotonic()
        if now - self._last_render_time >= RENDER_INTERVAL:
            self._render_tty()

    def _render_tty(self):
        try:
            self._do_render_tty()
        except Exception:
            self._degraded = True

    def _do_render_tty(self):
        term_w = shutil.get_terminal_size((80, 24)).columns
        inner_w = max(40, term_w - 4)

        lines = []

        # Header
        elapsed_str = _format_time(time.monotonic() - self.global_start_time)
        header_left = '  ODM %s' % self.version
        header_right = 'Elapsed: %s  ' % elapsed_str
        pad = inner_w - len(header_left) - len(header_right)
        if pad < 1:
            pad = 1
        lines.append(BOX_TL + BOX_H * inner_w + BOX_TR)
        lines.append(BOX_V + header_left + ' ' * pad + header_right + BOX_V)

        # Image info line
        if self.image_count > 0:
            info = '  %d images' % self.image_count
            lines.append(BOX_V + '%-*s' % (inner_w, info) + BOX_V)

        lines.append(BOX_LT + BOX_H * inner_w + BOX_RT)

        # Stage list
        for s in self.stages:
            if s.status == 'done':
                sym = SYM_DONE
                time_str = _format_time(s.elapsed)
                line_text = '  %s %-20s %s' % (sym, s.display_name, time_str)
                lines.append(BOX_V + '%-*s' % (inner_w, line_text) + BOX_V)

            elif s.status == 'running':
                sym = SYM_RUN
                elapsed = time.monotonic() - s.start_time if s.start_time else 0
                time_str = _format_time(elapsed)
                line_text = '  %s %-20s %s' % (sym, s.display_name, time_str)
                lines.append(BOX_V + '%-*s' % (inner_w, line_text) + BOX_V)

                # Progress bar
                bar_w = max(10, inner_w - 20)
                pct = s.progress_pct
                filled = int(bar_w * pct / 100.0)
                bar = BAR_FILL * filled + BAR_EMPTY * (bar_w - filled)

                eta_str = ''
                remaining = self._eta.estimate_remaining(s.name, elapsed, pct)
                if remaining is not None and remaining > 0 and pct > 0:
                    eta_str = '  ETA: ~%s' % _format_time(remaining)

                bar_line = '    [%s] %3d%%%s' % (bar, int(pct), eta_str)
                lines.append(BOX_V + '%-*s' % (inner_w, bar_line) + BOX_V)

                # Detail line
                if s.detail_line:
                    detail_text = '    %s' % s.detail_line
                    lines.append(BOX_V + '%-*s' % (inner_w, detail_text[:inner_w]) + BOX_V)

            elif s.status == 'error':
                line_text = '  %s %-20s [FAIL]' % (SYM_FAIL, s.display_name)
                lines.append(BOX_V + '%-*s' % (inner_w, line_text) + BOX_V)

            else:  # pending
                line_text = '  %s %s' % (SYM_PENDING, s.display_name)
                lines.append(BOX_V + '%-*s' % (inner_w, line_text) + BOX_V)

        # Separator and last log message
        lines.append(BOX_LT + BOX_H * inner_w + BOX_RT)
        log_display = self._last_log_msg[:inner_w - 2] if self._last_log_msg else ''
        lines.append(BOX_V + '  %-*s' % (inner_w - 2, log_display) + BOX_V)
        lines.append(BOX_BL + BOX_H * inner_w + BOX_BR)

        # Move cursor up and overwrite
        if self._last_frame_lines > 0:
            sys.stdout.write('\033[%dA' % self._last_frame_lines)
            sys.stdout.write('\033[J')  # clear from cursor down

        output = '\n'.join(lines) + '\n'
        sys.stdout.write(output)
        sys.stdout.flush()
        self._last_frame_lines = len(lines)
        self._last_render_time = time.monotonic()

    # --- Non-TTY rendering ---

    def _nontty_stage_start(self, stage):
        elapsed = _format_time(time.monotonic() - self.global_start_time)
        print('[%s] %s Starting: %s' % (elapsed, SYM_RUN, stage.display_name))
        sys.stdout.flush()

    def _nontty_stage_end(self, stage):
        elapsed_global = _format_time(time.monotonic() - self.global_start_time)
        elapsed_stage = _format_time(stage.elapsed)
        print('[%s] %s Completed: %s (%s)' % (elapsed_global, SYM_DONE, stage.display_name, elapsed_stage))
        sys.stdout.flush()

    def _nontty_progress(self, stage):
        """Print progress at 25% interval thresholds."""
        bucket = int(stage.progress_pct / 25) * 25
        if bucket <= 0 or bucket > 75:
            return
        last = self._nontty_last_pct_bucket.get(stage.name, 0)
        if bucket > last:
            self._nontty_last_pct_bucket[stage.name] = bucket
            elapsed = _format_time(time.monotonic() - self.global_start_time)
            detail = ' - %s' % stage.detail_line if stage.detail_line else ''
            print('[%s]   %s: %d%%%s' % (elapsed, stage.display_name, int(stage.progress_pct), detail))
            sys.stdout.flush()


def _format_time(seconds):
    """Format seconds into MM:SS or HH:MM:SS."""
    if seconds is None or seconds < 0:
        return '--:--'
    seconds = int(seconds)
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return '%d:%02d:%02d' % (h, m, s)
    else:
        m = seconds // 60
        s = seconds % 60
        return '%02d:%02d' % (m, s)


# Module-level singleton, initialized from stages/odm_app.py
display = None
