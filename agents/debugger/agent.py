class DebuggerAgent:

    def run(self, state):

        print("\n=== Debugger Agent Running ===")

        failed = state.validation.get("failed", 0)

        if failed == 0:
            state.debug_info = {
                "status": "success",
                "message": "No errors found"
            }

        else:
            state.debug_info = {
                "status": "failure",
                "message": f"{failed} tests failed",
                "details": state.validation.get("raw_output", "")
            }

        return state