import json

from agents.parser.graph_extractor import APIGraphFeatureExtractor


class ParserAgent:

    def run(self, state):

        print("\n=== Parser Agent Running ===")

        with open("petstore.json", encoding="utf-8") as file:
            state.spec = json.load(file)

        state.paths = state.spec.get(
            "paths",
            {}
        )

        state.endpoints = list(
            state.paths.keys()
        )

        # OpenAPI v2 schemas
        state.schemas = state.spec.get(
            "definitions",
            {}
        )

        print(
            f"Found {len(state.endpoints)} endpoints"
        )

        extractor = APIGraphFeatureExtractor(
            "petstore.json"
        )

        state.features = (
            extractor.extract_all_features()
        )

        state.graph = state.features

        print("\nExtracted Features:")

        for feature, value in (
            state.features.items()
        ):
            print(
                f"{feature}: {value}"
            )

        if "dependency_graph" in state.features:

            print("\nDependency Graph:")

            for endpoint, deps in (
                state.features[
                    "dependency_graph"
                ].items()
            ):
                print(
                    f"{endpoint} -> {deps}"
                )

        return state