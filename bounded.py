"""Independent, killable acquisition budgets; no data-provider text is logged."""
import multiprocessing as mp
import time
from multiprocessing.connection import wait


def _work(pipe, fn):
    started = time.monotonic()
    try:
        pipe.send({'value': fn(), 'status': 'OK', 'error': None,
                   'seconds': round(time.monotonic()-started, 3)})
    except Exception as exc:
        pipe.send({'value': None, 'status': 'UNAVAILABLE',
                   'error': type(exc).__name__, 'seconds': round(time.monotonic()-started, 3)})
    finally:
        pipe.close()


def acquire(tasks):
    """Run {name: (callable, seconds)} concurrently on the supported Linux host.

    A timed-out section cannot erase a completed sibling or continue mutating
    data after return. Only read-only acquisition functions belong here.
    """
    ctx = mp.get_context('fork')
    active, results = {}, {}
    try:
        for name, (fn, budget) in tasks.items():
            parent, child = ctx.Pipe(duplex=False)
            proc = ctx.Process(target=_work, args=(child, fn), daemon=True)
            proc.start(); child.close()
            active[parent] = (name, proc, time.monotonic(), max(.01, float(budget)))
        while active:
            timeout = max(0, min(start+budget-time.monotonic()
                                 for _, _, start, budget in active.values()))
            ready = wait(list(active), timeout)
            for pipe in list(active):
                name, proc, start, budget = active[pipe]
                if pipe in ready:
                    try:
                        results[name] = pipe.recv()
                    except EOFError:
                        results[name] = {'value': None, 'status': 'UNAVAILABLE',
                                         'error': 'WorkerExited', 'seconds': round(time.monotonic()-start, 3)}
                elif time.monotonic()-start >= budget:
                    results[name] = {'value': None, 'status': 'UNAVAILABLE',
                                     'error': 'TimeoutExpired', 'seconds': budget}
                else:
                    continue
                if proc.is_alive(): proc.terminate()
                proc.join(timeout=1)
                if proc.is_alive(): proc.kill(); proc.join()
                pipe.close(); del active[pipe]
    finally:
        for pipe, (_, proc, _, _) in active.items():
            if proc.is_alive(): proc.terminate()
            proc.join(timeout=1)
            if proc.is_alive(): proc.kill(); proc.join()
            pipe.close()
    return results
