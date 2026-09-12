"""Disposable provider probe. No model, download, or benchmark."""
import json
import sys
from .contracts import ProviderSpec
from .registry import ProviderRegistry


def main():
    data = json.loads(sys.stdin.read(65536))
    registry = ProviderRegistry()
    spec = ProviderSpec(**data)
    registry.register(spec)
    try:
        result = registry.get(spec.provider_id).probe()
    except Exception as exc:
        result = {'provider': spec.provider_id, 'availability': 'unavailable',
                  'devices': [], 'error': type(exc).__name__}
    finally:
        registry.close()
    print('THM_RESULT:' + json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
