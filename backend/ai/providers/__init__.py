from .nvidia import NvidiaProvider
from .emergent import EmergentProvider

_PROVIDERS = {
    "nvidia": NvidiaProvider(),
    "emergent": EmergentProvider(),
}


def get_provider(name: str):
    return _PROVIDERS.get(name)
