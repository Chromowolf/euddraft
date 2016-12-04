import sys
import os
import time
from applyeuddraft import applyEUDDraft
from pluginLoader import getGlobalPluginDirectory

import multiprocessing as mp


def hasModifiedFile(dirname, since):
    for root, dirs, files in os.walk(dirname):
        for f in files:
            finalpath = os.path.join(root, f)
            mtime = max(
                os.path.getmtime(finalpath),
                os.path.getctime(finalpath)
            )
            if mtime > since:
                return True
    return False


if __name__ == '__main__':
    mp.freeze_support()

    print("euddraft v0.6 : Simple eudplib plugin system")

    if len(sys.argv) != 2:
        raise RuntimeError("Usage : euddraft [setting file]")

    # Chdir to setting files
    sfname = sys.argv[1]
    oldpath = os.getcwd()
    dirname, sfname = os.path.split(sfname)
    if dirname:
        os.chdir(dirname)
        sys.path.insert(0, os.path.abspath(dirname))

    # Use simple setting system
    if sfname[-4:] == '.eds':
        applyEUDDraft(sfname)

    # Daemoning system
    elif sfname[-4:] == '.edd':
        mp.set_start_method('spawn')
        q = mp.Queue()
        lasttime = None

        globalPluginDir = getGlobalPluginDirectory()

        try:
            while True:
                if (
                    not lasttime or
                    hasModifiedFile(globalPluginDir, lasttime) or
                    hasModifiedFile('.', lasttime)
                ):
                    p = mp.Process(target=applyEUDDraft, args=(sfname,))
                    p.start()
                    p.join()
                    lasttime = time.time()

                time.sleep(1)
        except KeyboardInterrupt:
            pass

    else:
        print("Invalid extension %s" % os.path.splitext(sfname)[1])

    os.chdir(os.getcwd())
