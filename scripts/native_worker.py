"""Picklable native worker target: install the same adapter before worker startup."""


def worker_main(*args, **kwargs):
    from native_ouroboros import configure_runtime
    from supervisor import worker_process

    upstream_worker_main = getattr(
        worker_process, "_oilagent_original_worker_main", worker_process.worker_main
    )

    configure_runtime()
    return upstream_worker_main(*args, **kwargs)
