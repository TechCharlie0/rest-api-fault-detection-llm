class PlannerAgent:

    def run(self, state):

        print("\n=== Planner Agent Running ===")

        state.plan = []

        paths = state.paths

        for endpoint, methods in paths.items():

            for method, details in methods.items():

                if method.lower() not in [
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch"
                ]:
                    continue

                expected_status = 200

                responses = details.get("responses", {})

                for code in responses.keys():

                    if str(code).startswith("2"):
                        expected_status = int(code)
                        break

                risk = 40

                if method.upper() == "POST":
                    risk = 70

                elif method.upper() == "DELETE":
                    risk = 80

                plan = {
                    "endpoint": endpoint,
                    "method": method.upper(),
                    "expected_status": expected_status,
                    "risk": risk
                }

                state.plan.append(plan)

        print(f"Generated {len(state.plan)} plans")

        return state