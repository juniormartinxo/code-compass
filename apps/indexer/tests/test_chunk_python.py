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

    def test_extracts_callees_and_reverse_callers_for_python_symbols(self) -> None:
        specs = chunk_python_source(
            text=(
                "def helper() -> str:\n"
                "    return 'ok'\n\n"
                "def load() -> str:\n"
                "    return helper()\n\n"
                "class Service:\n"
                "    def run(self) -> str:\n"
                "        return self.load()\n\n"
                "    def load(self) -> str:\n"
                "        return helper()\n"
            ),
            file_content_type="code_context",
            class_max_lines=3,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        by_symbol = {
            spec.qualifiedSymbolName: spec
            for spec in specs
            if spec.qualifiedSymbolName is not None
        }

        self.assertEqual(by_symbol["helper"].callees, ())
        self.assertEqual(by_symbol["helper"].callers, ("load", "Service", "Service.load"))
        self.assertEqual(by_symbol["load"].callees, ("helper",))
        self.assertEqual(by_symbol["Service"].callees, ("Service.load", "helper"))
        self.assertEqual(by_symbol["Service.run"].callees, ("Service.load",))
        self.assertEqual(by_symbol["Service.load"].callees, ("helper",))

    def test_extracts_decorator_calls_into_python_call_graph(self) -> None:
        specs = chunk_python_source(
            text=(
                "@register(helper())\n"
                "def load() -> int:\n"
                "    return 1\n"
            ),
            file_content_type="code_context",
            class_max_lines=20,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        by_symbol = {
            spec.qualifiedSymbolName: spec
            for spec in specs
            if spec.qualifiedSymbolName is not None
        }

        self.assertEqual(by_symbol["load"].callees, ("register", "helper"))

    def test_does_not_link_temporary_receiver_calls_to_local_functions(self) -> None:
        specs = chunk_python_source(
            text=(
                "def load() -> int:\n"
                "    return 1\n\n"
                "def wrapper() -> int:\n"
                "    return get_client().load()\n"
            ),
            file_content_type="code_context",
            class_max_lines=20,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        by_symbol = {
            spec.qualifiedSymbolName: spec
            for spec in specs
            if spec.qualifiedSymbolName is not None
        }

        self.assertEqual(by_symbol["load"].callers, ())
        self.assertEqual(by_symbol["wrapper"].callees, ("get_client",))

    def test_does_not_link_super_calls_to_current_class_method(self) -> None:
        specs = chunk_python_source(
            text=(
                "class Base:\n"
                "    def load(self) -> int:\n"
                "        return 1\n\n"
                "class Service(Base):\n"
                "    def run(self) -> int:\n"
                "        return super().load()\n\n"
                "    def load(self) -> int:\n"
                "        return 2\n"
            ),
            file_content_type="code_context",
            class_max_lines=3,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        by_symbol = {
            spec.qualifiedSymbolName: spec
            for spec in specs
            if spec.qualifiedSymbolName is not None
        }

        self.assertEqual(by_symbol["Service.run"].callees, ())
        self.assertEqual(by_symbol["Service.load"].callers, ())


if __name__ == "__main__":
    unittest.main()
