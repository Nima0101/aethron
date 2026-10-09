from ._startup_trace import mark

mark("process_entry")


def _run():
    from .cli import main

    main()


_run()
