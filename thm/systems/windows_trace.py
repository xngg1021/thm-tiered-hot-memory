"""Explicit bounded ETW collection through the Windows native logman/tracerpt tools."""
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from .contracts import PermissionGate, finite, integer
from thm._bounded_files import bounded_file_bytes
from thm.runtime.fabric.resources import ChildBudget, stop_owned_process_tree


class EtwProbe:
    evidence='native-executed'

    def __init__(self,provider_guid,*,keywords=0,level=4,gate=PermissionGate()):
        gate.require('S2')
        if platform.system()!='Windows':raise OSError('ETW requires Windows')
        self.provider='{'+str(uuid.UUID(provider_guid))+'}'
        integer(keywords,maximum=2**64-1);integer(level,maximum=5)
        self.keywords,self.level=keywords,level
        self.name='thm-'+uuid.uuid4().hex
        self.owner=tempfile.TemporaryDirectory(prefix='thm-etw-')
        self.root=Path(self.owner.name);self.active=False;self.closed=False
        system=Path(os.environ['SystemRoot'])/'System32'
        self.logman=str(system/'logman.exe');self.tracerpt=str(system/'tracerpt.exe')
        self.sequence=0

    def _run(self,command,timeout=5):
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        budget=None
        try:
            budget=ChildBudget(process,memory=256*1024**2,cpu=timeout+1,io=64*1024**2)
            process.wait(timeout=timeout)
            if process.returncode:raise OSError('ETW native command failed: '+str(process.returncode))
        finally:
            stop_owned_process_tree(process,budget)
            if budget is not None:budget.close()

    def _stop(self):
        if self.active:
            self._run([self.logman,'stop',self.name,'-ets'])
            self.active=False

    def poll(self,timeout=.1,capacity=1024):
        finite(timeout);integer(capacity,minimum=1,maximum=100000)
        if self.closed or timeout>5:raise ValueError('closed/unbounded ETW collection window')
        self.sequence+=1;trace=self.root/f'{self.sequence}.etl';output=self.root/f'{self.sequence}.xml'
        self.active=True
        try:
            self._run([self.logman,'create','trace',self.name,'-o',str(trace),'-p',self.provider,
                       hex(self.keywords),str(self.level),'-f','bincirc','-max','2','-ets'])
            time.sleep(timeout)
        finally:self._stop()
        self._run([self.tracerpt,str(trace),'-o',str(output),'-of','XML','-y'])
        data=bounded_file_bytes(output,maximum=32*1024**2)
        root=ET.fromstring(data)
        events=[]
        for event in root.iter():
            if event.tag.rsplit('}',1)[-1]!='Event':continue
            if len(events)>=capacity:break
            # Preserve native XML field provenance; vendor field decoding is explicit.
            fields={node.tag.rsplit('}',1)[-1]:{'text':node.text,'attributes':dict(node.attrib)}
                    for node in event.iter() if node is not event}
            events.append({'kind':'tracepoint','provider':self.provider,'fields':fields,
                           'source':'Windows-ETW-tracerpt','collection_window_seconds':timeout})
        trace.unlink(missing_ok=True);output.unlink(missing_ok=True)
        return events

    def close(self):
        if self.closed:return
        self._stop();self.owner.cleanup();self.closed=True
