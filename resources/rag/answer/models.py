from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.retrieval import EvidenceContext, GroundedAnswer


class Entry(NodeInput[EvidenceContext, tuple[()]]):
    pass
