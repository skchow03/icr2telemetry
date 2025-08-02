from PyQt5.QtCore import Qt

class SplitTracker:
    def __init__(self, split1_dlong, split2_dlong):
        self.split_points = [split1_dlong, split2_dlong]
        self.reset()

    def reset(self):
        self.split_times = [None, None, None]
        self.best_times = [None, None, None]
        self.prev_best_times = [None, None, None]
        self.last_lap_time = None
        self.best_lap_time = None
        self.prev_best_lap_time = None
        self.last_dlong = 0
        self.last_time = 0
        self.current_time = 0
        self.current_sector = 0
        self.out_lap_complete = False

    def update(self, dlong, session_time):
        delta_dlong = dlong - self.last_dlong
        events = []

        self.current_time = session_time  # track for live timer

        # Sector crossings
        if self.current_sector == 0 and dlong >= self.split_points[0]:
            self.split_times[0] = session_time - self.last_time
            self._update_best(0)
            self.last_time = session_time
            self.current_sector = 1
            events.append("S1")

        elif self.current_sector == 1 and dlong >= self.split_points[1]:
            self.split_times[1] = session_time - self.last_time
            self._update_best(1)
            self.last_time = session_time
            self.current_sector = 2
            events.append("S2")

        elif delta_dlong < -50 * 6000:
            if self.current_sector == 2:
                self.split_times[2] = session_time - self.last_time
                self._update_best(2)
                events.append("S3")

                if all(self.split_times):
                    if not self.out_lap_complete:
                        self.split_times = [None, None, None]
                        self.out_lap_complete = True
                        events.append("lap_skipped")
                    else:
                        lap_time = sum(self.split_times)
                        self.last_lap_time = lap_time
                        if self.best_lap_time is None or lap_time < self.best_lap_time:
                            self.prev_best_lap_time = self.best_lap_time
                            self.best_lap_time = lap_time
                        events.append("lap")

            self.last_time = session_time
            self.current_sector = 0

        self.last_dlong = dlong
        return events

    def _update_best(self, sector_index):
        if not self.out_lap_complete:
            return
        t = self.split_times[sector_index]
        b = self.best_times[sector_index]
        if b is None or t < b:
            self.prev_best_times[sector_index] = b
            self.best_times[sector_index] = t

    def formatted_summary(self):
        def fmt_colored(t, best, is_purple=False):
            if t is None:
                return "--.--"
            color = "#c084fc" if is_purple else "white"
            return f'<span style="color:{color}">{t / 1000:.3f}</span>'

        def fmt_delta(current, best, previous_best):
            if current is None:
                return "--.--"
            ref = previous_best if (current == best and previous_best is not None) else best
            if ref is None:
                return "--.--"
            delta = current - ref
            sign = "+" if delta >= 0 else "-"
            return f"{sign}{abs(delta)/1000:.3f}"

        # Row 1: Bests
        best_row = "Best: " + " | ".join(
            "--.--" if t is None else f"{t / 1000:.3f}" for t in self.best_times
        ) + " | " + (
            "--.--" if self.best_lap_time is None else f"{self.best_lap_time / 1000:.3f}"
        )

        # Row 2: Last (live timer in current sector)
        last_row_parts = []
        for i in range(3):
            if self.out_lap_complete and i == self.current_sector and self.last_time:
                live_time = self.current_time - self.last_time
                last_row_parts.append(f'<span style="color:white">{live_time / 1000:.3f}</span>')
            else:
                t = self.split_times[i]
                b = self.best_times[i]
                is_purple = (
                    self.out_lap_complete and t is not None and b is not None and t == b
                )
                last_row_parts.append(fmt_colored(t, b, is_purple))

        is_lap_purple = (
            self.out_lap_complete
            and self.last_lap_time is not None
            and self.best_lap_time is not None
            and self.last_lap_time == self.best_lap_time
        )
        lap_str = fmt_colored(self.last_lap_time, self.best_lap_time, is_lap_purple)

        last_row = "Last: " + " | ".join(last_row_parts) + " | " + lap_str

        # Row 3: Delta
        delta_row = [
            fmt_delta(self.split_times[0], self.best_times[0], self.prev_best_times[0]),
            fmt_delta(self.split_times[1], self.best_times[1], self.prev_best_times[1]),
            fmt_delta(self.split_times[2], self.best_times[2], self.prev_best_times[2]),
            fmt_delta(self.last_lap_time, self.best_lap_time, self.prev_best_lap_time)
        ]
        delta_row_str = "Delta: " + " | ".join(delta_row)

        return f"{best_row}<br>{last_row}<br>{delta_row_str}"
