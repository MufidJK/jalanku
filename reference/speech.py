import queue
import threading
import time

import pyttsx3

from config import JEDA_DETIK


class Pembicara:
    """Suara lokal (laptop). Pesan bahaya memotong antrean."""

    def __init__(self, jeda=JEDA_DETIK):
        self.q = queue.Queue()
        self.terakhir = {}
        self.jeda = jeda
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        while True:
            teks = self.q.get()
            engine.say(teks)
            engine.runAndWait()

    def ucapkan(self, kunci, teks, urgent=False):
        sekarang = time.time()
        if sekarang - self.terakhir.get(kunci, 0) < self.jeda:
            return
        if not urgent and not self.q.empty():
            return  # jangan menumpuk pesan biasa
        self.terakhir[kunci] = sekarang
        if urgent:
            with self.q.mutex:
                self.q.queue.clear()
        self.q.put(teks)
