"""
Graph-Theoretic Feature Extraction for API Specifications
Maps to PDF Section 5A: Expanding Feature Engineering
"""
import json
import os
from typing import Any


class APIGraphFeatureExtractor:
    """
    Extracts graph-theoretic features from OpenAPI specifications.
    These features predict test generation quality (PDF Finding 2 & 4).
    """

    def __init__(self, spec_path: str):
        with open(spec_path) as f:
            self.spec = json.load(f)
        self.paths = self.spec.get('paths', {})
        self.components = self.spec.get('components', {})

    def extract_all_features(self) -> dict[str, Any]:
        """Extract all graph-theoretic features from the API spec."""
        features = {
            # Basic structural features
            'total_endpoints': self._count_endpoints(),
            'total_methods': self._count_methods(),

            # Graph-theoretic features (PDF Section 5A)
            'max_schema_depth': self._calculate_max_schema_depth(),
            'avg_schema_depth': self._calculate_avg_schema_depth(),
            'auth_dependency_index': self._calculate_auth_dependency_index(),
            'param_complexity_score': self._calculate_param_complexity(),
            'out_degree_centrality': self._calculate_out_degree_centrality(),

            # Additional predictive features
            'has_auth_required': self._has_auth_required(),
            'avg_params_per_endpoint': self._avg_params_per_endpoint(),
            'has_nested_objects': self._has_nested_objects(),
            'enum_complexity': self._calculate_enum_complexity(),
            'request_body_complexity': self._calculate_request_body_complexity(),
        }
        return features

    # --- FEATURE 1: Max Schema Depth (PDF Finding 4) ---
    def _calculate_max_schema_depth(self) -> int:
        """
        PDF Section 5A: "How deeply nested a request/response schema tree is"
        Deep schemas require more test combinations (combinatorial explosion).
        """
        max_depth = 0
        schemas = self.components.get('schemas', {})

        for _schema_name, schema_def in schemas.items():
            depth = self._measure_schema_depth(schema_def, current_depth=0)
            max_depth = max(max_depth, depth)

        return max_depth

    def _measure_schema_depth(self, schema: dict, current_depth: int) -> int:
        """Recursively measure the depth of nested schema objects."""
        if not isinstance(schema, dict):
            return current_depth

        max_child_depth = current_depth

        # Check properties (nested objects)
        if 'properties' in schema:
            for _prop_name, prop_schema in schema['properties'].items():
                child_depth = self._measure_schema_depth(prop_schema, current_depth + 1)
                max_child_depth = max(max_child_depth, child_depth)

        # Check items (arrays of objects)
        if 'items' in schema:
            child_depth = self._measure_schema_depth(schema['items'], current_depth + 1)
            max_child_depth = max(max_child_depth, child_depth)

        # Check allOf/oneOf/anyOf (composition)
        for key in ['allOf', 'oneOf', 'anyOf']:
            if key in schema:
                for sub_schema in schema[key]:
                    child_depth = self._measure_schema_depth(sub_schema, current_depth + 1)
                    max_child_depth = max(max_child_depth, child_depth)

        return max_child_depth

    def _calculate_avg_schema_depth(self) -> float:
        """Average schema depth across all schemas."""
        schemas = self.components.get('schemas', {})
        if not schemas:
            return 0.0

        depths = []
        for _schema_name, schema_def in schemas.items():
            depth = self._measure_schema_depth(schema_def, current_depth=0)
            depths.append(depth)

        return round(sum(depths) / len(depths), 2) if depths else 0.0

    # --- FEATURE 2: Auth Dependency Index (PDF Section 5A) ---
    def _calculate_auth_dependency_index(self) -> float:
        """
        PDF Section 5A: "What percentage of endpoints require chained auth tokens"
        High auth dependency = harder for LLMs to generate valid tests.
        """
        if not self.paths:
            return 0.0

        total_endpoints = 0
        auth_required_count = 0

        for _path, methods in self.paths.items():
            for method, details in methods.items():
                if method in ['get', 'post', 'put', 'delete', 'patch']:
                    total_endpoints += 1
                    # Check for security requirements
                    if 'security' in details and details['security']:
                        auth_required_count += 1

        return round(auth_required_count / total_endpoints, 2) if total_endpoints > 0 else 0.0

    def _has_auth_required(self) -> bool:
        """Boolean: Does the API have any auth requirements?"""
        return self._calculate_auth_dependency_index() > 0

    # --- FEATURE 3: Parameter Complexity Score (PDF Section 5A) ---
    def _calculate_param_complexity(self) -> float:
        """
        PDF Section 5A: "Counts required vs optional params, enum values,
        and nested object schemas to estimate test case explosion factor"
        """
        if not self.paths:
            return 0.0

        total_complexity = 0
        endpoint_count = 0

        for _path, methods in self.paths.items():
            for method, details in methods.items():
                if method not in ['get', 'post', 'put', 'delete', 'patch']:
                    continue

                endpoint_count += 1
                complexity = 0

                # Count parameters
                params = details.get('parameters', [])
                complexity += len(params)

                # Add weight for required params
                required_params = [p for p in params if p.get('required', False)]
                complexity += len(required_params) * 0.5

                # Add weight for enum values (combinatorial explosion)
                for param in params:
                    schema = param.get('schema', {})
                    if 'enum' in schema:
                        complexity += len(schema['enum']) * 0.3

                # Add weight for path parameters (harder than query params)
                path_params = [p for p in params if p.get('in') == 'path']
                complexity += len(path_params) * 0.7

                total_complexity += complexity

        return round(total_complexity / endpoint_count, 2) if endpoint_count > 0 else 0.0

    # --- FEATURE 4: Out-Degree Centrality (PDF Section 5A) ---
    def _calculate_out_degree_centrality(self) -> float:
        """
        PDF Section 5A: "Identifies 'hub' endpoints that are called by many services"
        High centrality = highest regression risk.
        """
        if not self.paths:
            return 0.0

        # Count references to each path in other schemas
        path_references = {path: 0 for path in self.paths.keys()}

        # Check $ref usage in schemas
        schemas = self.components.get('schemas', {})
        for _schema_name, schema_def in schemas.items():
            schema_str = json.dumps(schema_def)
            for path in self.paths.keys():
                # Count how many times this path's components are referenced
                path_base = path.split('/')[-1].replace('{', '').replace('}', '')
                if path_base.lower() in schema_str.lower():
                    path_references[path] += 1

        # Calculate normalized centrality
        max_refs = max(path_references.values()) if path_references else 1
        if max_refs == 0:
            return 0.0

        avg_centrality = sum(path_references.values()) / len(path_references)
        return round(avg_centrality / max_refs, 2)

    # --- FEATURE 5: Average Parameters Per Endpoint ---
    def _avg_params_per_endpoint(self) -> float:
        """Average number of parameters per endpoint."""
        if not self.paths:
            return 0.0

        total_params = 0
        endpoint_count = 0

        for _path, methods in self.paths.items():
            for method, details in methods.items():
                if method in ['get', 'post', 'put', 'delete', 'patch']:
                    endpoint_count += 1
                    total_params += len(details.get('parameters', []))

        return round(total_params / endpoint_count, 2) if endpoint_count > 0 else 0.0

    # --- FEATURE 6: Nested Objects Detection ---
    def _has_nested_objects(self) -> bool:
        """Does the API have nested object schemas?"""
        return self._calculate_max_schema_depth() > 2

    # --- FEATURE 7: Enum Complexity ---
    def _calculate_enum_complexity(self) -> int:
        """Total number of enum values across all parameters."""
        enum_count = 0

        for _path, methods in self.paths.items():
            for method, details in methods.items():
                if method not in ['get', 'post', 'put', 'delete', 'patch']:
                    continue

                for param in details.get('parameters', []):
                    schema = param.get('schema', {})
                    if 'enum' in schema:
                        enum_count += len(schema['enum'])

        return enum_count

    # --- FEATURE 8: Request Body Complexity ---
    def _calculate_request_body_complexity(self) -> float:
        """Complexity of request bodies (POST/PUT endpoints)."""
        complexity = 0
        body_count = 0

        for _path, methods in self.paths.items():
            for method, details in methods.items():
                if method not in ['post', 'put', 'patch']:
                    continue

                if 'requestBody' in details:
                    body_count += 1
                    content = details['requestBody'].get('content', {})

                    for _media_type, media_def in content.items():
                        schema = media_def.get('schema', {})
                        # Count properties in request body
                        if 'properties' in schema:
                            complexity += len(schema['properties'])
                        # Add depth
                        complexity += self._measure_schema_depth(schema, 0) * 0.5

        return round(complexity / body_count, 2) if body_count > 0 else 0.0

    # --- Helper: Count endpoints and methods ---
    def _count_endpoints(self) -> int:
        return len(self.paths)

    def _count_methods(self) -> int:
        count = 0
        for _path, methods in self.paths.items():
            for method in methods.keys():
                if method in ['get', 'post', 'put', 'delete', 'patch']:
                    count += 1
        return count


# --- MAIN: Test on Petstore API ---
if __name__ == "__main__":
    print("="*70)
    print("GRAPH FEATURE EXTRACTION (PDF Section 5A)")
    print("="*70)

    extractor = APIGraphFeatureExtractor('petstore.json')
    features = extractor.extract_all_features()

    print("\n📊 Extracted Graph-Theoretic Features:\n")
    for feature_name, value in features.items():
        print(f"  {feature_name:30s} = {value}")

    # Save to JSON for ML pipeline
    os.makedirs("results", exist_ok=True)
    with open("results/petstore_features.json", "w") as f:
        json.dump(features, f, indent=2)

    print("\n✅ Features saved to results/petstore_features.json")
    print("\n📝 These features will be used as ML inputs (X) to predict test quality (Y)")
