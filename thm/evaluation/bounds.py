"""Process-tree deadline for installed, dependency-free acceptance."""
def bounded_process(command, seconds, root):
    """Bound the entire owned process tree, including prepare/autotune children."""
    import os
    import signal
    import subprocess
    from thm.runtime.receipts import write_receipt
    if root.exists():raise FileExistsError('verification output namespace exists')
    process=subprocess.Popen(command,start_new_session=(os.name=='posix'))
    try:return process.wait(timeout=seconds)
    except (subprocess.TimeoutExpired,KeyboardInterrupt) as exc:
        if os.name=='posix':
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
            if process.poll() is None:process.kill()
        process.wait(timeout=10)
        root.mkdir(parents=True,exist_ok=True)
        if not (root/'interrupted.json').exists():
            write_receipt(root/'interrupted.json',{'status':'interrupted-or-wall-budget-exceeded',
                'error_type':type(exc).__name__,'wall_budget_seconds':seconds,'full_dataset_acceptance':False})
        return 124
