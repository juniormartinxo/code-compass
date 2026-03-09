from __future__ import annotations

import unittest

from indexer.chunk_models import TS_SYMBOL_CHUNK_STRATEGY
from indexer.chunk_ts import chunk_ts_source


class TsChunkSourceTests(unittest.TestCase):
    def test_extracts_imports_hook_and_component_chunks(self) -> None:
        specs = chunk_ts_source(
            text=(
                "import { useMemo } from 'react';\n"
                "import { api } from './api';\n\n"
                "export const useService = (id: string) => {\n"
                "  return api.load(id);\n"
                "};\n\n"
                "export function ProductCard({ title }: { title: string }) {\n"
                "  return <section>{title}</section>;\n"
                "}\n"
            ),
            language="typescriptreact",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0].contentType, "code_context")
        self.assertIsNone(specs[0].symbolName)
        self.assertIn("import { useMemo }", specs[0].content)

        hook_chunk = specs[1]
        self.assertEqual(hook_chunk.chunkStrategy, TS_SYMBOL_CHUNK_STRATEGY)
        self.assertEqual(hook_chunk.symbolName, "useService")
        self.assertEqual(hook_chunk.qualifiedSymbolName, "useService")
        self.assertEqual(hook_chunk.symbolType, "hook")
        self.assertEqual(hook_chunk.imports, ("react", "./api"))
        self.assertEqual(hook_chunk.exports, ("useService", "ProductCard"))

        component_chunk = specs[2]
        self.assertEqual(component_chunk.symbolName, "ProductCard")
        self.assertEqual(component_chunk.symbolType, "component")
        self.assertIn("<section>{title}</section>", component_chunk.content)

    def test_supports_exported_expression_body_helper(self) -> None:
        specs = chunk_ts_source(
            text="export const sum = (a: number, b: number) => a + b;\n",
            language="typescript",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].symbolName, "sum")
        self.assertEqual(specs[0].symbolType, "helper")
        self.assertEqual(specs[0].signature, "export const sum = (a: number, b: number) => a + b")

    def test_splits_large_class_into_summary_context_and_methods(self) -> None:
        specs = chunk_ts_source(
            text=(
                "export class Service {\n"
                "  private baseUrl = '/api';\n\n"
                "  // important comment\n"
                "  load(id: string): string {\n"
                "    return id;\n"
                "  }\n\n"
                "  save(id: string): string {\n"
                "    return id;\n"
                "  }\n"
                "}\n"
            ),
            language="typescript",
            file_content_type="code_context",
            class_max_lines=4,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 4)
        self.assertEqual(specs[0].symbolName, "Service")
        self.assertEqual(specs[0].symbolType, "class")
        self.assertIn("fields: baseUrl", specs[0].content)
        self.assertIn("methods: load, save", specs[0].content)

        self.assertEqual(specs[1].contentType, "code_context")
        self.assertIn("private baseUrl = '/api';", specs[1].content)
        self.assertIn("// important comment", specs[1].content)

        self.assertEqual(specs[2].qualifiedSymbolName, "Service.load")
        self.assertEqual(specs[2].symbolType, "method")
        self.assertEqual(specs[2].parentSymbol, "Service")
        self.assertEqual(specs[3].qualifiedSymbolName, "Service.save")

    def test_returns_none_when_structure_is_unbalanced(self) -> None:
        specs = chunk_ts_source(
            text=(
                "export const broken = () => {\n"
                "  return 1;\n"
            ),
            language="typescript",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNone(specs)

    def test_keeps_overload_signatures_as_context_and_implementation_as_symbol(self) -> None:
        specs = chunk_ts_source(
            text=(
                "export function format(value: string): string;\n"
                "export function format(value: number): string;\n"
                "export function format(value: string | number): string {\n"
                "  return String(value);\n"
                "}\n"
            ),
            language="typescript",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].contentType, "code_context")
        self.assertIn("export function format(value: string): string;", specs[0].content)

        implementation = specs[1]
        self.assertEqual(implementation.symbolName, "format")
        self.assertEqual(implementation.symbolType, "helper")
        self.assertEqual(
            implementation.signature,
            "export function format(value: string | number): string",
        )
        self.assertNotIn("export function format(value: number): string;", implementation.content)

    def test_keeps_default_export_names_in_exports_metadata(self) -> None:
        named_specs = chunk_ts_source(
            text=(
                "export default function ProductCard() {\n"
                "  return <section />;\n"
                "}\n"
            ),
            language="typescriptreact",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(named_specs)
        assert named_specs is not None
        self.assertEqual(named_specs[0].symbolName, "ProductCard")
        self.assertEqual(named_specs[0].symbolType, "component")
        self.assertEqual(named_specs[0].exports, ("ProductCard",))

        wrapped_specs = chunk_ts_source(
            text=(
                "export default memo(function ProductCard() {\n"
                "  return <section />;\n"
                "});\n"
            ),
            language="typescriptreact",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(wrapped_specs)
        assert wrapped_specs is not None
        self.assertEqual(wrapped_specs[0].symbolName, "ProductCard")
        self.assertEqual(wrapped_specs[0].symbolType, "component")
        self.assertEqual(wrapped_specs[0].exports, ("ProductCard",))

        anonymous_class_specs = chunk_ts_source(
            text=(
                "export default class extends BaseService {\n"
                "  run(): void {}\n"
                "}\n"
            ),
            language="typescript",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(anonymous_class_specs)
        assert anonymous_class_specs is not None
        self.assertEqual(anonymous_class_specs[0].symbolName, "default")
        self.assertEqual(anonymous_class_specs[0].symbolType, "class")
        self.assertEqual(anonymous_class_specs[0].exports, ("default",))

    def test_extracts_anonymous_default_exports_as_semantic_chunks(self) -> None:
        anonymous_function_specs = chunk_ts_source(
            text=(
                "export default function() {\n"
                "  return <section />;\n"
                "}\n"
            ),
            language="typescriptreact",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(anonymous_function_specs)
        assert anonymous_function_specs is not None
        self.assertEqual(len(anonymous_function_specs), 1)
        self.assertEqual(anonymous_function_specs[0].symbolName, "default")
        self.assertEqual(anonymous_function_specs[0].symbolType, "component")
        self.assertEqual(anonymous_function_specs[0].exports, ("default",))

        anonymous_arrow_specs = chunk_ts_source(
            text="export default () => <div />;\n",
            language="typescriptreact",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(anonymous_arrow_specs)
        assert anonymous_arrow_specs is not None
        self.assertEqual(len(anonymous_arrow_specs), 1)
        self.assertEqual(anonymous_arrow_specs[0].symbolName, "default")
        self.assertEqual(anonymous_arrow_specs[0].symbolType, "component")
        self.assertEqual(anonymous_arrow_specs[0].exports, ("default",))

        wrapped_arrow_specs = chunk_ts_source(
            text=(
                "export default forwardRef((props, ref) => {\n"
                "  return <input ref={ref} />;\n"
                "});\n"
            ),
            language="typescriptreact",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(wrapped_arrow_specs)
        assert wrapped_arrow_specs is not None
        self.assertEqual(len(wrapped_arrow_specs), 1)
        self.assertEqual(wrapped_arrow_specs[0].symbolName, "default")
        self.assertEqual(wrapped_arrow_specs[0].symbolType, "component")
        self.assertEqual(wrapped_arrow_specs[0].exports, ("default",))

    def test_attaches_decorators_to_class_and_method_chunks(self) -> None:
        specs = chunk_ts_source(
            text=(
                "@Injectable()\n"
                "export class Service {\n"
                "  @Get(\n"
                "    '/items',\n"
                "  )\n"
                "  load(): string {\n"
                "    return 'ok';\n"
                "  }\n"
                "}\n"
            ),
            language="typescript",
            file_content_type="code_context",
            class_max_lines=3,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].symbolName, "Service")
        self.assertIn("@Injectable()", specs[0].content)
        self.assertEqual(specs[1].qualifiedSymbolName, "Service.load")
        self.assertIn("@Get(", specs[1].content)
        self.assertIn("'/items',", specs[1].content)

    def test_keeps_multiline_class_header_inside_large_class_summary(self) -> None:
        specs = chunk_ts_source(
            text=(
                "export class Service\n"
                "  extends BaseService\n"
                "  implements Loader, Saver\n"
                "{\n"
                "  load(): string {\n"
                "    return 'ok';\n"
                "  }\n\n"
                "  save(): string {\n"
                "    return 'ok';\n"
                "  }\n"
                "}\n"
            ),
            language="typescript",
            file_content_type="code_context",
            class_max_lines=3,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0].symbolName, "Service")
        self.assertIn("extends BaseService", specs[0].content)
        self.assertIn("implements Loader, Saver", specs[0].content)
        self.assertEqual(specs[1].qualifiedSymbolName, "Service.load")
        self.assertEqual(specs[2].qualifiedSymbolName, "Service.save")

    def test_supports_abstract_class_as_class_symbol(self) -> None:
        specs = chunk_ts_source(
            text=(
                "export abstract class Service {\n"
                "  run(): void {}\n"
                "}\n"
            ),
            language="typescript",
            file_content_type="code_context",
            class_max_lines=12,
        )

        self.assertIsNotNone(specs)
        assert specs is not None

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].symbolName, "Service")
        self.assertEqual(specs[0].symbolType, "class")
        self.assertIn("export abstract class Service", specs[0].content)


if __name__ == "__main__":
    unittest.main()
