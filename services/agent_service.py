from agents.state import AgentState

from agents.parser.agent import ParserAgent
from agents.planner.agent import PlannerAgent
from agents.coder.agent import CoderAgent
from agents.validator.agent import ValidatorAgent
from agents.debugger.agent import DebuggerAgent


class AgentService:

    def __init__(self):

        self.parser = ParserAgent()
        self.planner = PlannerAgent()
        self.coder = CoderAgent()
        self.validator = ValidatorAgent()
        self.debugger = DebuggerAgent()

    def generate(self):

        state = AgentState()

        state = self.parser.run(state)

        state = self.planner.run(state)

        state = self.coder.run(state)

        state = self.validator.run(state)

        state = self.debugger.run(state)

        return state