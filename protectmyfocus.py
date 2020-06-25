
import select
import subprocess
import time
import argparse
from collections import deque
from queue import Queue, Empty
from threading import Thread

import toml
import log

t_startup = time.time()

# number of focus switches within 1 second to classify a bad actor window
# (e.x. the Steam "exiting" dialog focuses itself when any other steam window gains focus)
DoS_trigger_count = 25

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        strd = line.decode('utf-8').rstrip()
        # log.debug(strd)
        queue.put(strd)
    out.close()

class FocusProtector():
    def __init__(self, config = None):
        self.xprop_listener = subprocess.Popen(
            ['xprop', '-root', '-spy',
            '\t$0+\n', '_NET_ACTIVE_WINDOW',
            '\t$0+\n', '_NET_CLIENT_LIST_STACKING'],
            stdout=subprocess.PIPE
        )
        self.config = toml.load(config)
        log.debug(self.config)
        try:
            if "startuptime" not in self.config:
                self.config["startuptime"] = {}
            if "whitelist" not in self.config:
                self.config["whitelist"] = []
        except AssertionError as e:
            log.err(e)
            raise e
        self.output_queue = Queue()
        self.output_queueing_thread = Thread(
            target=enqueue_output,
            args=(self.xprop_listener.stdout, self.output_queue)
        )
        self.output_queueing_thread.daemon = True

        self._WM_CLASS_MAP = {} # id to name
        self._WM_CREATED_TIME = {} # id to created epoch time
        self._NET_ACTIVE_WINDOW = None
        self.dos_detect_queue = deque([0.0] * DoS_trigger_count, DoS_trigger_count)

        self.update_wm_class_map()
        self._NET_ACTIVE_WINDOW = self.get_active_windowid()
        log.debug(f"Init _NET_ACTIVE_WINDOW: {self.get_windowid_str(self._NET_ACTIVE_WINDOW)}")
        self._NET_CLIENT_LIST_STACKING = self.get_stacking_list()
        log.debug(f"Init _NET_CLIENT_LIST_STACKING: {self._NET_CLIENT_LIST_STACKING}")

        for cid in self._NET_CLIENT_LIST_STACKING:
            self._WM_CREATED_TIME[cid] = 0.0

    def update_wm_class_map(self, windowid=None):
        if windowid:
            self._WM_CLASS_MAP[windowid] = self.get_window_classname(windowid)
            return self._WM_CLASS_MAP[windowid]
        else:
            for c in self.get_stacking_list():
                self._WM_CLASS_MAP[c] = self.get_window_classname(c)

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

    def get_window_classname(self, windowid):
        if windowid in self._WM_CLASS_MAP:
            return self._WM_CLASS_MAP[windowid]
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
        n = time.time()
        self.dos_detect_queue.append(n)
        if self.dos_detect_queue[0] > (n - 1.0):
            log.warn(f"Focus steal DoS prevention! More than {DoS_trigger_count} attempts to regain focus in the last second.")
            log.debug(f"DoS queue: {self.dos_detect_queue}")
            return
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

    def handle_new_window(self, wid):
        self.update_wm_class_map(wid)
        self._WM_CREATED_TIME[wid] = time.time()

    def active_window_changed(self, windowid, newstack):
        allow_new_focus = True
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
                self.handle_new_window(w)
                log.info(f"New window: {self.get_windowid_str(w)}")
            wname = self.get_window_classname(windowid)
            if wname in self.config["whitelist"]:
                log.info(f"{self.get_windowid_str(windowid)} is in whitelist, allowing.")
            elif wname == self.get_window_classname(self._NET_ACTIVE_WINDOW):
                # allow automated focus between windows of the same application:
                log.info(f"Allowing {self.get_windowid_str(self._NET_ACTIVE_WINDOW)} to {self.get_windowid_str(windowid)} since they are the same class.")
            else:
                log.info(f"Focusing previous focus holder: {self.get_windowid_str(self._NET_ACTIVE_WINDOW)}")
                try:
                    self.set_window_focus(self._NET_ACTIVE_WINDOW)
                    allow_new_focus = False
                except subprocess.CalledProcessError as e:
                    log.err(f"Could not re-focus the previous window! previous: {self._NET_ACTIVE_WINDOW} new: {windowid}")
        elif len(newstack) == len(self._NET_CLIENT_LIST_STACKING):
            log.info(f"Window focus changed from {self.get_windowid_str(self._NET_ACTIVE_WINDOW)} to {self.get_windowid_str(windowid)}")
            wname = self.get_window_classname(windowid)
            if wname not in self.config["whitelist"] and wname in self.config["startuptime"]:
                if time.time() <= self.config["startuptime"][wname] + self._WM_CREATED_TIME[windowid]:
                    log.info(f"Preventing focus of {self.get_windowid_str(windowid)}, which is still within startup timeout.")
                    self.set_window_focus(self._NET_ACTIVE_WINDOW)
                    allow_new_focus = False
        else:
            old_windows = [x for x in self._NET_CLIENT_LIST_STACKING if x not in set(newstack)]
            for w in old_windows:
                log.info(f"Window destroyed: {self.get_windowid_str(w)}")
            log.info(f"{self.get_windowid_str(windowid)} inherits focus.")
        log.debug("Setting new _NET_ACTIVE_WINDOW and _NET_CLIENT_LIST_STACKING")
        self._NET_CLIENT_LIST_STACKING = newstack
        if allow_new_focus:
            self._NET_ACTIVE_WINDOW = windowid

    def mainloop(self):
        self.output_queueing_thread.start()
        while True:
            try:
                rawline = self.output_queue.get()
            except Empty:
                # log.debug("waiting for input...")
                pass
            except Exception as e:
                log.err(e)
            else:
                self.xprop_event(rawline)

    def quit(self):
        self.xprop_listener.terminate()

fp = None

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c", "--config",
        type=str,
        help="Config file",
        required=False,
        default="config.toml"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbosity increase"
    )

    args = parser.parse_args()
    if (args.verbose):
        log.setLevel(log.DEBUG)

    try:
        fp = FocusProtector(args.config)
        fp.mainloop()
    except KeyboardInterrupt as e:
        fp.quit()
        # raise e
