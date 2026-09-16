from .base import StrictModel
from .packages import Identifier, Version, SymbolReference


class BlockManifest(StrictModel):
    block_id: Identifier
    version: Version
    entry: SymbolReference
    input_model: SymbolReference
    output_model: SymbolReference
