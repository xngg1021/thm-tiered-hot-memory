"""Public failure categories never serialize exception messages or filenames."""
import subprocess
from .hardware import versions


def failure(exc, stage, backend, code=None):
    if code is None:
        if isinstance(exc, (ImportError, ModuleNotFoundError)):code='dependency-missing'
        elif isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):code='timeout'
        elif isinstance(exc, FileExistsError):code='publication-conflict'
        elif isinstance(exc, NotImplementedError):code='export-unsupported'
        else:code='conversion-failed'
    # Exception type names from third-party code are not trusted public text.
    classes=(ModuleNotFoundError,ImportError,TimeoutError,FileExistsError,ValueError,OSError,RuntimeError,NotImplementedError)
    klass=next((c.__name__ for c in classes if isinstance(exc,c)),'Exception')
    return {'status':'failed','stage':stage,'error_code':code,'error_class':klass,
        'error_type':klass,'backend':backend,'dependency_state':versions(),
        'retryability':'retry-after-budget-change' if code=='timeout' else 'requires-diagnosis-or-environment-change',
        'private_details_redacted':True,'generation_calls':0}
