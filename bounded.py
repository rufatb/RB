"""Independent, killable acquisition budgets; no data-provider text is logged."""
import multiprocessing as mp
import time
import threading
from multiprocessing.connection import wait

_progress_pipe = None
_progress_lock = None


def progress(stage, **fields):
    """Small, credential-free stage observations survive a worker timeout.

    Callers supply fixed stage names, ticker identities and numeric counts;
    exception messages and provider URLs are deliberately not accepted.
    """
    allowed = {'ticker', 'count', 'error_class'}
    if not isinstance(stage, str) or not stage.replace('_', '').isalnum():
        raise ValueError('invalid acquisition stage')
    if set(fields) - allowed:
        raise ValueError('unsupported progress field')
    if any(not isinstance(v, (str, int, float, bool)) or len(str(v)) > 80
           or any(c in str(v) for c in ('/', '?', '=', '\n')) for v in fields.values()):
        raise ValueError('unsafe acquisition progress')
    if _progress_pipe is not None:
        with _progress_lock:
            _progress_pipe.send({'progress': {'stage': stage, **fields}})


def _work(pipe, fn):
    global _progress_pipe, _progress_lock
    _progress_pipe, _progress_lock = pipe, threading.Lock()
    started = time.monotonic()
    try:
        pipe.send({'value': fn(), 'status': 'OK', 'error': None,
                   'seconds': round(time.monotonic()-started, 3)})
    except Exception as exc:
        pipe.send({'value': None, 'status': 'UNAVAILABLE',
                   'error': type(exc).__name__, 'seconds': round(time.monotonic()-started, 3)})
    finally:
        _progress_pipe = None
        pipe.close()


def acquire(tasks):
    """Run {name: (callable, seconds)} concurrently on the supported Linux host.

    A timed-out section cannot erase a completed sibling or continue mutating
    data after return. Only read-only acquisition functions belong here.
    """
    ctx = mp.get_context('fork')
    active, results, stages = {}, {}, {}
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
                        message = pipe.recv()
                        if 'progress' in message:
                            history = stages.setdefault(name, [])
                            if len(history) < 96:
                                history.append({**message['progress'],
                                                'seconds': round(time.monotonic()-start, 3)})
                            if time.monotonic()-start < budget:
                                continue
                            results[name] = {'value': None, 'status': 'UNAVAILABLE',
                                             'error': 'TimeoutExpired', 'seconds': budget}
                        else:
                            results[name] = message
                    except EOFError:
                        results[name] = {'value': None, 'status': 'UNAVAILABLE',
                                         'error': 'WorkerExited', 'seconds': round(time.monotonic()-start, 3)}
                elif time.monotonic()-start >= budget:
                    results[name] = {'value': None, 'status': 'UNAVAILABLE',
                                     'error': 'TimeoutExpired', 'seconds': budget}
                else:
                    continue
                if name in stages:
                    results[name]['progress'] = stages[name]
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
