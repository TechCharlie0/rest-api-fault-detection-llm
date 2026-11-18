import os

from agents.data_generator.agent import DataGeneratorAgent


class CoderAgent:

    def run(self, state):

        print("\n=== Coder Agent Running ===")

        os.makedirs(
            "generated_tests",
            exist_ok=True
        )

        generator = DataGeneratorAgent()

        tests = []

        for plan in state.plan:

            endpoint = plan["endpoint"]
            method = plan["method"]

            filename = (
                f"test_{method.lower()}_"
                f"{endpoint.strip('/').replace('/', '_').replace('{', '').replace('}', '')}.py"
            )

            payload = (
                generator.generate_payload(
                    endpoint,
                    method,
                    state
                )
            )

            url = (
                "https://petstore.swagger.io/v2"
                + endpoint
            )

            url = url.replace(
                "{petId}",
                "1"
            )

            url = url.replace(
                "{orderId}",
                "1"
            )

            url = url.replace(
                "{username}",
                "testuser"
            )

            if method in [
                "POST",
                "PUT",
                "PATCH"
            ]:

                test_code = f'''
import requests

def {filename.replace(".py", "")}():

    url = "{url}"

    payload = {payload}

    response = requests.request(
        "{method}",
        url,
        json=payload
    )

    assert response.status_code < 500
'''

            else:

                test_code = f'''
import requests

def {filename.replace(".py", "")}():

    url = "{url}"

    response = requests.request(
        "{method}",
        url
    )

    assert response.status_code < 500
'''

            file_path = (
                f"generated_tests/{filename}"
            )

            with open(
                file_path,
                "w",
                encoding="utf-8"
            ) as f:
                f.write(test_code)

            tests.append(test_code)

        state.tests = tests

        print(
            f"Generated {len(tests)} tests"
        )

        print(
            f"Saved {len(tests)} files"
        )

        return state