
import select
import subprocess
import log
from queue import Queue, Empty
from threading import Thread

log.setLevel(log.DEBUG)
active = True

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        strd = line.decode('utf-8').rstrip()
        # log.debug(strd)
        queue.put(strd)
    out.close()

class FocusProtector():
    def __init__(self):
        self.xprop_listener = subprocess.Popen(
            ['xprop', '-root', '-spy',
            '\t$0+\n', '_NET_ACTIVE_WINDOW',
            '\t$0+\n', '_NET_CLIENT_LIST_STACKING'],
            stdout=subprocess.PIPE
        )
        self.output_queue = Queue()
        self.output_queueing_thread = Thread(
            target=enqueue_output,
            args=(self.xprop_listener.stdout, self.output_queue)
        )
        self.output_queueing_thread.daemon = True

        self._WM_CLASS_MAP = {}
        self.update_wm_class_map()
        self._NET_ACTIVE_WINDOW = None
        self._NET_ACTIVE_WINDOW = self.get_active_windowid()
        log.debug(f"Init _NET_ACTIVE_WINDOW: {self.get_windowid_str(self._NET_ACTIVE_WINDOW)}")
        self._NET_CLIENT_LIST_STACKING = self.get_stacking_list()
        log.debug(f"Init _NET_CLIENT_LIST_STACKING: {self._NET_CLIENT_LIST_STACKING}")


    def update_wm_class_map(self, windowid=None):
        if windowid:
            self._WM_CLASS_MAP[windowid] = self.get_window_name(windowid)
            return self._WM_CLASS_MAP[windowid]
        else:
            for c in self.get_stacking_list():
                self._WM_CLASS_MAP[c] = self.get_window_name(c)

    def parse_client_list_stacking(self, line):
        slist = ( line.split("\t") )[-1]
        winlist = slist.split(', ')
        return winlist

    def get_stacking_list(self):
        p = subprocess.run(
            ['xprop', '-root', '\\t$0+\\n', '_NET_CLIENT_LIST_STACKING'],
            stdout=subprocess.PIPE
        )
        return self.parse_client_list_stacking(p.stdout.decode('utf-8').rstrip())

    def get_window_name(self, windowid):
        p = subprocess.run(
            ['xprop', '-id', windowid, '\\t$0+\\n', 'WM_CLASS'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        l = [x for x in p.stdout.decode('utf-8').rstrip().split('"') if x]
        # log.debug(l)
        try:
            return l[-1]
        except IndexError as e:
            log.err(f"Failed to get name for window {windowid}")
            # log.err(e)
            log.err(f"xprop stdout: {p.stdout.decode('utf-8').rstrip()}")
            log.err(f"xprop stderr: {p.stderr.decode('utf-8').rstrip()}")
            return '???'

    def get_active_windowid(self):
        p = subprocess.run(
            ['xprop', '-root', '\t$0\n', '_NET_ACTIVE_WINDOW'],
            stdout=subprocess.PIPE
        )
        return p.stdout.decode('utf-8').rstrip().split('\t')[-1]

    def get_windowid_str(self, windowid):
        name = None
        try:
            name = self._WM_CLASS_MAP[windowid]
        except KeyError:
            name = self.update_wm_class_map(windowid)
        finally:
            return f"{name}/{windowid}"

    def set_window_focus(self, windowid):
        p = subprocess.run(
            ['wmctrl', '-i', '-a', windowid],
        )
        p.check_returncode()

    def xprop_event(self, event):
        event_type = event.split('\t')[0]
        log.debug("event:" + str(event.split('\t')[0]))

        if event_type == "_NET_ACTIVE_WINDOW(WINDOW)":
            # _NET_ACTIVE_WINDOW(WINDOW): window id # 0x76000b9
            windowid = event.split('\t')[-1]
            log.debug(f"_NET_ACTIVE_WINDOW event to {self.get_windowid_str(windowid)}")
            self.active_window_changed(windowid, self.get_stacking_list())
        elif event_type == "_NET_CLIENT_LIST_STACKING(WINDOW)":
            newstack = self.parse_client_list_stacking(event)
            log.debug(f"_NET_CLIENT_LIST_STACKING, top: {newstack[-4:]}")
            # windowid = newstack[-1]
            self.active_window_changed(self._NET_ACTIVE_WINDOW, newstack)

    def active_window_changed(self, windowid, newstack):
        # log.debug(f"Window focus changed to window {self.get_windowid_str(windowid)}")
        if (windowid == self._NET_ACTIVE_WINDOW and newstack == self._NET_CLIENT_LIST_STACKING):
            log.debug(f"Event with no change detected.")
            return

        stacking_index = None
        try:
            stacking_index = newstack.index(windowid)
            stacking_index_from_top = stacking_index - len(newstack)
        except ValueError:
            log.warn(f"Window {self.get_windowid_str(windowid)} no longer exists in stacking index! Ignoring this focus change.")
            log.warn(f"newstack: {newstack}")
            return
        log.debug(f"Window is index {stacking_index} ({stacking_index_from_top}) of {len(newstack)} in stack")
        # log.info(f"Window stack currently: {newstack}")
        if len(newstack) > len(self._NET_CLIENT_LIST_STACKING):
            new_windows = [x for x in newstack if x not in set(self._NET_CLIENT_LIST_STACKING)]
            for w in new_windows:
                self.update_wm_class_map(w)
                log.info(f"New window: {self.get_windowid_str(w)}")
            log.info(f"Focusing previous focus holder: {self.get_windowid_str(self._NET_ACTIVE_WINDOW)}")
            try:
                self.set_window_focus(self._NET_ACTIVE_WINDOW)
            except subprocess.CalledProcessError as e:
                log.err(f"Could not re-focus the previous window! previous: {self._NET_ACTIVE_WINDOW} new: {windowid}")
        elif len(newstack) == len(self._NET_CLIENT_LIST_STACKING):
            log.info(f"Window focus changed from {self.get_windowid_str(self._NET_ACTIVE_WINDOW)} to {self.get_windowid_str(windowid)}")
        else:
            old_windows = [x for x in self._NET_CLIENT_LIST_STACKING if x not in set(newstack)]
            for w in old_windows:
                log.info(f"Window destroyed: {self.get_windowid_str(w)}")
            log.info(f"{self.get_windowid_str(windowid)} inherits focus.")
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
            except Exception as e:
                log.err(e)
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
        raise e
