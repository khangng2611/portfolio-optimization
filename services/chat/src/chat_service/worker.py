import signal
import time
from service_observability import configure, log_event
from .runtime import sessions_from_env
from .tools import Tools
from .workflow import Worker


def main():
    configure("chat-worker")
    worker = Worker(sessions_from_env(), Tools())
    stopping = False

    def stop(*args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_prune = 0
    while not stopping:
        try:
            if time.monotonic() - last_prune > 3600:
                worker.prune_events()
                last_prune = time.monotonic()
            if not worker.tick():
                time.sleep(0.5)
        except Exception:
            # Do not log exception text: HTTP errors may contain sensitive headers.
            log_event("chat.worker.error", outcome="retry_after_lease")
            time.sleep(1)


if __name__ == "__main__":
    main()
