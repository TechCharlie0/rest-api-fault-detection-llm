class SchemaPayloadGenerator:

    def generate(
        self,
        schema,
        definitions=None
    ):

        if not schema:
            return {}

        # Resolve OpenAPI $ref
        if "$ref" in schema:

            ref_name = (
                schema["$ref"]
                .split("/")
                [-1]
            )

            if (
                definitions
                and
                ref_name in definitions
            ):
                return self.generate(
                    definitions[ref_name],
                    definitions
                )

            return {}

        schema_type = schema.get("type")

        if schema_type == "object":

            result = {}

            for (
                field,
                field_schema
            ) in schema.get(
                "properties",
                {}
            ).items():

                result[field] = self.generate(
                    field_schema,
                    definitions
                )

            return result

        if schema_type == "array":

            item_schema = schema.get(
                "items",
                {}
            )

            return [
                self.generate(
                    item_schema,
                    definitions
                )
            ]

        if schema_type == "string":

            enum_values = schema.get("enum")

            if enum_values:
                return enum_values[0]

            fmt = schema.get("format")

            if fmt == "date-time":
                return (
                    "2025-01-01T00:00:00.000Z"
                )

            if fmt == "email":
                return "john@test.com"

            return "sample"

        if schema_type == "integer":
            return 1

        if schema_type == "number":
            return 1.0

        if schema_type == "boolean":
            return True

        return "sample"