"""Кроссплатформенное чтение строки: Tab-автодополнение и история.

На POSIX используется стандартный readline. На Windows его нет, поэтому
там работает собственный редактор на msvcrt (стрелки, Backspace, Tab).
"""
from __future__ import annotations

import os
import sys


class Editor:
    def __init__(self):
        self.history: list[str] = []
        self._readline = None
        self._complete = None

        if sys.platform != "win32" and sys.stdin.isatty():
            try:
                import readline

                readline.parse_and_bind("tab: complete")
                self._readline = readline
            except ImportError:
                self._readline = None

    # -- POSIX ----------------------------------------------------------
    def _posix_read(self, prompt: str, complete) -> str:
        readline = self._readline
        complete_fn = complete

        def completer(text, state):
            matches = complete_fn(readline.get_line_buffer())
            return matches[state] if state < len(matches) else None

        readline.set_completer(completer)
        line = input(prompt)
        if line.strip():
            readline.add_history(line)
        return line

    # -- Windows --------------------------------------------------------
    def _win_read(self, prompt: str, complete) -> str:
        import msvcrt

        buf: list[str] = []
        pos = 0
        hist_index = len(self.history)

        def redraw() -> None:
            sys.stdout.write("\r\x1b[K" + prompt + "".join(buf))
            back = len(buf) - pos
            if back > 0:
                sys.stdout.write(f"\x1b[{back}D")
            sys.stdout.flush()

        redraw()
        while True:
            char = msvcrt.getwch()

            if char in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                line = "".join(buf)
                if line.strip():
                    self.history.append(line)
                return line

            if char == "\x03":
                raise KeyboardInterrupt

            if char == "\x04":
                if not buf:
                    raise EOFError
                continue

            if char == "\x08":
                if pos > 0:
                    del buf[pos - 1]
                    pos -= 1
                    redraw()
                continue

            if char == "\t":
                pos = self._complete_tab(buf, pos, complete, redraw)
                continue

            if char in ("\x00", "\xe0"):
                scan = msvcrt.getwch()
                if scan == "H" and self.history:
                    hist_index = max(0, hist_index - 1)
                    buf = list(self.history[hist_index])
                    pos = len(buf)
                    redraw()
                elif scan == "P" and self.history:
                    hist_index = min(len(self.history), hist_index + 1)
                    buf = list(self.history[hist_index]) if hist_index < len(self.history) else []
                    pos = len(buf)
                    redraw()
                elif scan == "K":
                    pos = max(0, pos - 1)
                    redraw()
                elif scan == "M":
                    pos = min(len(buf), pos + 1)
                    redraw()
                continue

            if char >= " ":
                buf.insert(pos, char)
                pos += 1
                redraw()

    @staticmethod
    def _complete_tab(buf: list[str], pos: int, complete, redraw) -> int:
        line = "".join(buf)
        candidates = complete(line)
        if not candidates:
            return pos

        token_start = line.rfind(" ") + 1
        prefix = line[token_start:]

        if len(candidates) == 1:
            tail = " " if not line.endswith(" ") else ""
            new_line = line[:token_start] + candidates[0] + tail
            buf[:] = list(new_line)
            redraw()
            return len(buf)

        common = os.path.commonprefix(candidates)
        if len(common) > len(prefix):
            new_line = line[:token_start] + common
            buf[:] = list(new_line)
            redraw()
            return len(buf)

        sys.stdout.write("\n")
        print("  " + "  ".join(sorted(candidates)))
        redraw()
        return pos

    # -- dispatch -------------------------------------------------------
    def read(self, prompt: str, complete) -> str:
        if self._readline is not None:
            return self._posix_read(prompt, complete)
        if sys.platform == "win32" and sys.stdin.isatty() and sys.stdout.isatty():
            return self._win_read(prompt, complete)
        return input(prompt)
