class AgentState:
    def __init__(self):

        self.spec = None

        self.paths = {}

        self.endpoints = []

        # graph features
        self.graph = {}

        # dependency graph
        self.dependencies = {}

        self.features = {}

        self.plan = []

        self.tests = []

        self.generated_files = []

        self.validation = {}

        self.debug_info = {}

        self.logs = []