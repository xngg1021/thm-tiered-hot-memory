"""Lazy registration and isolated native discovery; no automatic installation."""
from dataclasses import replace
import importlib
from importlib import metadata, util
import json
import platform
import subprocess
import sys
import threading

from .contracts import ProviderSpec


class ProviderUnavailable(RuntimeError):
    pass


class ProviderRegistry:
    def __init__(self):
        self._specs = {}
        self._instances = {}
        self._failures = {}
        self._lock = threading.RLock()

    def register(self, spec):
        if not isinstance(spec, ProviderSpec):
            raise TypeError('ProviderSpec required')
        with self._lock:
            if spec.provider_id in self._specs:
                raise ValueError('duplicate provider ID: ' + spec.provider_id)
            self._specs[spec.provider_id] = spec

    def register_entry_points(self):
        """Inspect metadata only. Third-party code is loaded only on explicit get."""
        entries = metadata.entry_points()
        entries = entries.select(group='thm.providers') if hasattr(entries, 'select') else entries.get('thm.providers', ())
        for ep in sorted(entries, key=lambda x: x.name):
            try:
                self.register(ProviderSpec(ep.name, 'extension', 'entry-point', ep.value,
                                          validation_state='untrusted-unvalidated'))
            except (ValueError, TypeError) as exc:
                self._failures['entry-point:' + ep.name] = type(exc).__name__

    def describe(self, provider_id):
        spec = self._specs[provider_id]
        versions = {}
        for dependency in spec.dependencies:
            try:
                versions[dependency] = metadata.version(dependency)
            except metadata.PackageNotFoundError:
                versions[dependency] = None
        supported = platform.system() in spec.supported_os
        return {**spec.public(), 'versions': versions,
                'availability': 'unsupported-os' if not supported else
                'dependency-missing' if any(v is None for v in versions.values()) else 'unprobed',
                'failure': self._failures.get(provider_id), 'observed_kernel_dispatch': None}

    def list(self, *, operation=None, device_class=None):
        specs = sorted(self._specs.values(), key=lambda s: (-s.priority, s.provider_id))
        return [self.describe(s.provider_id) for s in specs
                if (operation is None or operation in s.supported_operations)
                and (device_class is None or device_class in s.supported_device_classes)]

    def get(self, provider_id, *, allow_untrusted=False):
        with self._lock:
            if provider_id in self._instances:
                return self._instances[provider_id]
            spec = self._specs[provider_id]
            if spec.validation_state.startswith('untrusted') and not allow_untrusted:
                raise ProviderUnavailable('entry-point requires explicit trust')
            if platform.system() not in spec.supported_os:
                raise ProviderUnavailable('unsupported OS')
            try:
                module, name = spec.factory.split(':', 1)
                factory = getattr(importlib.import_module(module), name)
                instance = factory(spec)
                self._instances[provider_id] = instance
                return instance
            except Exception as exc:
                self._failures[provider_id] = type(exc).__name__
                raise ProviderUnavailable(type(exc).__name__) from None

    def probe(self, provider_id, *, timeout=3.0):
        """Probe native libraries in a disposable process, outside startup."""
        if not 0 < timeout <= 10:
            raise ValueError('bounded probe timeout required')
        spec = self._specs[provider_id]
        if spec.validation_state.startswith('untrusted'):
            return {'provider': provider_id, 'availability': 'untrusted', 'devices': []}
        try:
            result = subprocess.run([sys.executable, '-m', 'thm.runtime.fabric.probe_worker'],
                                    input=json.dumps(spec.public()), text=True,
                                    capture_output=True, timeout=timeout, check=True)
            # Native libraries may log; the worker writes a distinct final JSON line.
            line = next(line[11:] for line in reversed(result.stdout.splitlines()) if line.startswith('THM_RESULT:'))
            return json.loads(line)
        except Exception as exc:
            self._failures[provider_id] = type(exc).__name__
            return {'provider': provider_id, 'availability': 'probe-failed',
                    'error': type(exc).__name__, 'devices': [], 'observed_kernel_dispatch': None}

    def close(self):
        for key, instance in list(self._instances.items()):
            try:
                instance.close()
            except Exception as exc:
                self._failures[key] = type(exc).__name__
        self._instances.clear()


def builtin_registry(*, extensions=True):
    from .catalog import BUILTINS
    registry = ProviderRegistry()
    for spec in BUILTINS:
        registry.register(spec)
    if extensions:
        registry.register_entry_points()
    return registry

