def ingest_file(*args, **kwargs):
    # Import only when dispatch is requested; importing OCR/PPT helpers should
    # not require a speech model runtime.
    from .ingest import ingest_file as dispatch
    return dispatch(*args, **kwargs)

__all__ = ["ingest_file"]
