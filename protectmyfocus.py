
import select
import subprocess
import log
from queue import Queue, Empty
from threading import Thread

log.setLevel(log.DEBUG)
active = True

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        strd = line.decode('utf-8').strip()
        # log.debug(strd)
        queue.put(strd)
    out.close()

class FocusProtector():
    def __init__(self):
        self.xprop_listener = subprocess.Popen(
            ['xprop', '-spy', '-root', '_NET_ACTIVE_WINDOW'],
            stdout=subprocess.PIPE
        )
        self.output_queue = Queue()
        self.output_queueing_thread = Thread(
            target=enqueue_output,
            args=(self.xprop_listener.stdout, self.output_queue)
        )
        self.output_queueing_thread.daemon = True

        self._NET_ACTIVE_WINDOW = None
        self._NET_CLIENT_LIST_STACKING = self.get_stacking_list()

    def get_stacking_list(self):
        p = subprocess.run(
            ['xprop', '-root', '_NET_CLIENT_LIST_STACKING'],
            stdout=subprocess.PIPE
        )
        slist = p.stdout.decode('utf-8').strip().split('# ')[-1]
        log.debug(slist)
        winlist = slist.split(', ')
        return winlist

    def set_window_focus(self, windowid):
        p = subprocess.run(
            ['wmctrl', '-i', '-a', windowid],
        )
        p.check_returncode()

    def xprop_event(self, event):
        event_type = event.split(' ')[0]
        # log.debug(f"event: {event_type}")

        if event_type == "_NET_ACTIVE_WINDOW(WINDOW):":
            # _NET_ACTIVE_WINDOW(WINDOW): window id # 0x76000b9
            windowid = event.split(' ')[-1]
            self.active_window_changed(windowid)
        # elif event_type == "_NET_CLIENT_LIST(WINDOW):":
        #     log.info("Client list updated.")
        # elif event_type == "_NET_CLIENT_LIST_STACKING(WINDOW):":
        #     log.info("Stacking list updated.")

    def active_window_changed(self, windowid):
        log.info(f"Window focus changed to window {windowid}")
        # log.debug(windowid)
        newstack = self.get_stacking_list()
        # log.info(f"Window stack currently: {newstack}")
        if len(newstack) > len(self._NET_CLIENT_LIST_STACKING):
            log.info("Window creation detected! Focusing previous window!")
            try:
                self.set_window_focus(self._NET_ACTIVE_WINDOW)
            except subprocess.CalledProcessError as e:
                log.err(f"Could not re-focus the previous window! previous: {self._NET_ACTIVE_WINDOW} new: {windowid}")
        elif len(newstack) == len(self._NET_CLIENT_LIST_STACKING):
            log.debug("Window focus changed.")
        else:
            log.info("Window lost.")
        self._NET_CLIENT_LIST_STACKING = newstack
        self._NET_ACTIVE_WINDOW = windowid

    def mainloop(self):
        self.output_queueing_thread.start()
        while True:
            try:
                rawline = self.output_queue.get_nowait()
            except Empty:
                # log.debug("waiting for input...")
                pass
            else:
                self.xprop_event(rawline)

    def quit(self):
        self.xprop_listener.terminate()

fp = FocusProtector()

if __name__ == '__main__':
    try:
        fp.mainloop()
    except KeyboardInterrupt as e:
        fp.quit()
