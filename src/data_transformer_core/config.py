from dataclasses import dataclass

from data_transformer_core.credentials import CredentialProvider
from data_transformer_core.kv_store import KeyValueStore
from data_transformer_core.storage import Storage


@dataclass
class transformerConfig:
    """transformer configuration container."""

    credential_provider: CredentialProvider
    kv_store: KeyValueStore
    storage: Storage
