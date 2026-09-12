"""Deterministic protocol fixtures; these do not represent a deployed storage service."""
import io
from pathlib import Path
import time
from .backends import FixtureTransport


class FakeS3Client:
    evidence='fixture-validated'
    def __init__(self,close_marker=None):self.objects={};self.close_marker=close_marker
    def put_object(self,**kwargs):
        if kwargs['IfNoneMatch']!='*':raise ValueError('create-only publication required')
        if kwargs['Key'] in self.objects:raise FileExistsError('conditional put')
        self.objects[kwargs['Key']]=kwargs['Body']
    def get_object(self,**kwargs):
        first,last=map(int,kwargs['Range'][6:].split('-'))
        return {'Body':io.BytesIO(self.objects[kwargs['Key']][first:last+1])}
    def head_object(self,**kwargs):return {'ContentLength':len(self.objects[kwargs['Key']])}
    def close(self):
        if self.close_marker:Path(self.close_marker).write_text('client-close')


class DelayedTransport(FixtureTransport):
    def __init__(self,stage):super().__init__();self.delay_stage=stage
    def _fault(self,stage):
        if stage==self.delay_stage:time.sleep(30)
        super()._fault(stage)
    def size(self,key):self._fault('size');return super().size(key)
    def close(self):self._fault('close');super().close()
