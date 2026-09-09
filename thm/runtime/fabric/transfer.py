"""Public copy APIs with observed byte accounting. Capability is not execution."""
import time
from .contracts import finite


class HostTransfer:
    def __init__(self, spec=None):
        self.spec = spec; self.last = {}

    def supports(self, source, target):
        return source in ('dram', 'mmap', 'filesystem') and target == 'dram'

    def estimate(self, size, source, target):
        finite(size, 'bytes')
        return {'bytes': size, 'source': source, 'destination': target, 'latency_ms': None, 'supported': self.supports(source, target)}

    def stage(self, data, **options):
        return self.transfer(data, 'dram', **options)

    def transfer(self, data, target, *, source='dram', **options):
        if not self.supports(source, target):
            raise ValueError('unsupported host transfer')
        start = time.perf_counter()
        result = bytes(memoryview(data))
        self.last = {'bytes': len(result), 'source': source, 'destination': target,
                     'transfer_ms': (time.perf_counter()-start)*1000, 'sync_ms': 0,
                     'copy_kind': 'host-copy', 'staging': source != 'dram', 'pinned': False,
                     'zero_copy': False, 'gds': False}
        return result

    def synchronize(self):
        return None

    def telemetry(self):
        return dict(self.last)

    def probe(self):
        return {'availability': 'available', 'devices': ['cpu']}

    def close(self):
        pass


class TorchTransfer(HostTransfer):
    def probe(self):
        from .indexes import ExactAccelerator
        return ExactAccelerator(self.spec).probe()

    def _runtime(self):
        import importlib
        options = dict(self.spec.options) if self.spec else {}
        if options.get('extension'):
            importlib.import_module(options['extension'])
        return importlib.import_module('torch'), options.get('device', 'cuda')

    def supports(self, source, target):
        device = dict(self.spec.options).get('device', 'cuda') if self.spec else 'cuda'
        return (source == 'dram' and target.split(':')[0] == device) or (source.split(':')[0] == device and target == 'dram')

    def stage(self, data, *, pinned=False, **options):
        torch, device = self._runtime()
        value = torch.as_tensor(data)
        if pinned:
            if device != 'cuda':
                raise ValueError('pinned staging unavailable for this adapter')
            value = value.pin_memory()
        return value

    def transfer(self, data, target, *, source='dram', asynchronous=False, pinned=False):
        if not self.supports(source, target):
            raise ValueError('unsupported device transfer')
        torch, device = self._runtime()
        start = time.perf_counter()
        value = self.stage(data, pinned=pinned) if source == 'dram' else data
        if asynchronous and (device != 'cuda' or not value.is_pinned()):
            raise ValueError('async host transfer requires observed pinned input')
        result = value.to('cpu' if target == 'dram' else target, non_blocking=asynchronous)
        self.last = {'bytes': result.numel()*result.element_size(), 'source': source, 'destination': target,
                     'transfer_ms': (time.perf_counter()-start)*1000, 'sync_ms': None,
                     'copy_kind': 'async-copy' if asynchronous else 'copy', 'staging': source == 'dram',
                     'pinned': bool(source == 'dram' and value.is_pinned()), 'zero_copy': False, 'gds': False}
        return result

    def synchronize(self):
        torch, device = self._runtime(); start = time.perf_counter()
        getattr(torch, device).synchronize()
        self.last['sync_ms'] = (time.perf_counter()-start)*1000
