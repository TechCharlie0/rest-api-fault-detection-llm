import re
import subprocess


class ValidatorAgent:

    def run(self, state):

        print("\n=== Validator Agent Running ===")

        result = subprocess.run(
            ["pytest", "generated_tests", "-q"],
            capture_output=True,
            text=True
        )

        output = result.stdout + result.stderr

        passed = 0
        failed = 0

        match = re.search(r"(\d+) passed", output)
        if match:
            passed = int(match.group(1))

        match = re.search(r"(\d+) failed", output)
        if match:
            failed = int(match.group(1))

        state.validation = {
            "passed": passed,
            "failed": failed,
            "raw_output": output
        }

        print(output)

        return state