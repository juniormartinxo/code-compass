from __future__ import annotations

import unittest

from indexer.chunk_models import PYTHON_SYMBOL_CHUNK_STRATEGY
from indexer.chunk_python import chunk_python_source


class PythonChunkSourceTests(unittest.TestCase):
    def test_extracts_module_context_and_function_chunks(self) -> None:
        specs = chunk_python_source(
            text=(
                "# module comment\n"
                "import os\n\n"
                "def load_data(user_id: str) -> dict[str, str]:\n"
                "    return {'id': user_id}\n"
            ),
            file_content_type="code_context",
            class_max_lines=20,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0].contentType, "code_context")
        self.assertIsNone(specs[0].symbolName)
        self.assertIn("# module comment", specs[0].content)
        self.assertEqual(specs[1].contentType, "code_context")
        self.assertIn("import os", specs[1].content)
        self.assertEqual(specs[2].contentType, "code_symbol")
        self.assertEqual(specs[2].symbolName, "load_data")
        self.assertEqual(specs[2].qualifiedSymbolName, "load_data")
        self.assertEqual(specs[2].symbolType, "function")
        self.assertEqual(specs[2].signature, "def load_data(user_id: str) -> dict[str, str]:")
        self.assertEqual(specs[2].chunkStrategy, PYTHON_SYMBOL_CHUNK_STRATEGY)

    def test_keeps_small_class_as_single_chunk(self) -> None:
        specs = chunk_python_source(
            text=(
                "class Service:\n"
                "    def run(self, item: str) -> str:\n"
                "        return item.upper()\n"
            ),
            file_content_type="code_context",
            class_max_lines=10,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].symbolName, "Service")
        self.assertEqual(specs[0].qualifiedSymbolName, "Service")
        self.assertEqual(specs[0].symbolType, "class")
        self.assertIn("class Service:", specs[0].content)

    def test_splits_large_class_into_summary_and_methods(self) -> None:
        specs = chunk_python_source(
            text=(
                "class Service:\n"
                "    KIND = 'service'\n\n"
                "    # important comment\n"
                "    def load(self, item: str) -> str:\n"
                "        return item\n\n"
                "    def save(self, item: str) -> str:\n"
                "        return item\n"
            ),
            file_content_type="code_context",
            class_max_lines=3,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 4)
        self.assertEqual(specs[0].symbolName, "Service")
        self.assertEqual(specs[0].symbolType, "class")
        self.assertIn("methods: load, save", specs[0].content)
        self.assertEqual(specs[1].contentType, "code_context")
        self.assertIn("KIND = 'service'", specs[1].content)
        self.assertIn("# important comment", specs[1].content)
        self.assertEqual(specs[2].qualifiedSymbolName, "Service.load")
        self.assertEqual(specs[2].symbolType, "method")
        self.assertEqual(specs[2].parentSymbol, "Service")
        self.assertEqual(specs[3].qualifiedSymbolName, "Service.save")

    def test_returns_none_when_python_parse_fails(self) -> None:
        specs = chunk_python_source(
            text="def broken(\n",
            file_content_type="code_context",
            class_max_lines=20,
        )

        self.assertIsNone(specs)

    def test_distinguishes_property_getter_and_setter_chunks(self) -> None:
        specs = chunk_python_source(
            text=(
                "class Service:\n"
                "    @property\n"
                "    def value(self) -> str:\n"
                "        return 'x'\n\n"
                "    @value.setter\n"
                "    def value(self, new_value: str) -> None:\n"
                "        self._value = new_value\n"
            ),
            file_content_type="code_context",
            class_max_lines=3,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        value_methods = [
            spec for spec in specs if spec.qualifiedSymbolName == "Service.value"
        ]
        self.assertEqual(len(value_methods), 2)
        self.assertNotEqual(value_methods[0].signature, value_methods[1].signature)


if __name__ == "__main__":
    unittest.main()
