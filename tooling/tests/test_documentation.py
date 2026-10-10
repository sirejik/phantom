"""Regression checks for independent document numbering and stable legacy links."""

from pathlib import Path
import tempfile
import unittest

import docindex
import doclint
import implementation_map_check
import configgen
import spec_contract_check
import copy
import re


class DocumentationTests(unittest.TestCase):
    def test_locator_accepts_document_paths(self):
        rows = docindex.collect()
        self.assertEqual(docindex.locate(rows, '3', 'docs/tooling.md'),
                         docindex.locate(rows, '3', 'tooling.md'))
        self.assertTrue(docindex.locate(rows, '3', 'docs/tooling.md'))
    def test_single_tool_entry_and_documented_commands(self):
        from tooling.cli import parser
        cli = parser()
        actions = next(action for action in cli._actions if isinstance(action, __import__('argparse')._SubParsersAction))
        text = (doclint.ROOT/'docs/tooling.md').read_text(encoding='utf-8')
        for command in actions.choices:
            self.assertIn('`'+command+'`', text)
        self.assertTrue((doclint.ROOT/'tooling/__main__.py').is_file())
        for old in ('scripts/phantom.cmd','tools/toolchain.ps1'):
            self.assertFalse((doclint.ROOT/old).exists())

    def test_local_links_require_anchor_in_the_destination_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "README.md"
            source.write_text('<a id="criterion-c-01"></a>\n', encoding="utf-8")
            target = root / "target file.md"
            target.write_text('<a id="sec-test"></a>\n## Repeated\n## Repeated\n', encoding="utf-8")
            valid = ("[section](target%20file.md#sec-test) "
                     "[criterion](#criterion-c-01) [heading](target%20file.md#repeated-1)")
            self.assertEqual(doclint.local_link_errors(valid, source), [])
            for link in ("[wrong file](README.md#sec-test)",
                         "[missing](gone.md)", "[criterion](target%20file.md#criterion-c-01)"):
                with self.subTest(link=link):
                    self.assertTrue(doclint.local_link_errors(link, source))
            self.assertEqual(doclint.local_link_errors("[external](https://example.com/#absent)", source), [])

    def test_prose_declared_measured_fields_exist_in_canonical_config(self):
        sources = configgen.source_objects()
        spec_contract_check.check_prose_measured_contract(sources)
        sources = copy.deepcopy(sources)
        del sources["quest"]["human_mapping"]["max_mapping_scale"]
        self.assertRaises(ValueError, spec_contract_check.check_prose_measured_contract, sources)

    def test_product_requirement_criterion_links(self):
        text = ('| <a id="criterion-c-01"></a>`C-01` | Direction | Observable outcome |\n'
                '| `FR-MAP-01` | Map the arm. | [C-01](#criterion-c-01) |\n')
        self.assertEqual(doclint.product_traceability_errors(text), [])

    def test_acceptance_traceability_covers_current_product(self):
        docs = doclint.ROOT / "docs"
        self.assertEqual(doclint.acceptance_traceability_errors(
            (docs / "product-requirements.md").read_text(encoding="utf-8"),
            (docs / "metrics-and-logs.md").read_text(encoding="utf-8")), [])

    def test_acceptance_traceability_rejects_missing_and_unknown_ids(self):
        docs = doclint.ROOT / "docs"
        product = (docs / "product-requirements.md").read_text(encoding="utf-8")
        acceptance = (docs / "metrics-and-logs.md").read_text(encoding="utf-8")
        for identifier in ("FR-TRK-01", "NFR-PRIV-04"):
            with self.subTest(identifier=identifier):
                changed = acceptance.replace("`" + identifier + "`", "`FR-UNKNOWN-01`")
                errors = doclint.acceptance_traceability_errors(product, changed)
                self.assertTrue(any("missing from acceptance matrix: " + identifier in e for e in errors))
                self.assertTrue(any("unknown acceptance requirement ID" in e for e in errors))

    def test_acceptance_traceability_requires_criteria_owners_and_procedures(self):
        docs = doclint.ROOT / "docs"
        product = (docs / "product-requirements.md").read_text(encoding="utf-8")
        acceptance = (docs / "metrics-and-logs.md").read_text(encoding="utf-8")
        start = acceptance.index('<a id="sec-test-plan-25-1">')
        end = acceptance.index('<a id="sec-test-plan-25-3">')
        matrix = acceptance[start:end]
        mutations = (
            matrix.replace('[C-02](product-requirements.md#criterion-c-02)',
                           '[C-01](product-requirements.md#criterion-c-01)'),
            matrix.replace('quest-specification.md#', 'product-requirements.md#'),
            matrix.replace('#sec-', '#missing-'),
            matrix.replace('`FR-TRK-07`', '`FR-TRK-01`'),
            matrix.replace('`FR-TRK-01`, `FR-TRK-07`', '`FR-TRK-01..07`'),
        )
        for changed in mutations:
            with self.subTest(matrix=changed[:120]):
                text = acceptance[:start] + changed + acceptance[end:]
                self.assertTrue(doclint.acceptance_traceability_errors(product, text))

    def test_rejects_incomplete_or_ambiguous_product_traceability(self):
        criterion = '| <a id="criterion-c-01"></a>`C-01` | Direction | Outcome |\n'
        row = '| `FR-MAP-01` | Map the arm. | [C-01](#criterion-c-01) |\n'
        for text in (criterion, criterion + criterion + row,
                     criterion + row + row,
                     criterion + row.replace('C-01](#criterion-c-01)', 'C-02](#criterion-c-02)'),
                     criterion + row.replace('#criterion-c-01', '#criterion-c-02'),
                     criterion + row + row.replace('`FR-MAP-01` |', '`FR-MAP-02` (old ID) |'),
                     criterion + row.replace('[C-01](#criterion-c-01)', ''),
                     criterion + row.replace('[C-01](#criterion-c-01)', 'C-01')):
            with self.subTest(text=text):
                self.assertTrue(doclint.product_traceability_errors(text))

    def setUp(self):
        self.rows = [
            ("sec-7", "§7", "docs/ev3-specification.md", "EV3", 2),
            ("sec-7-1", "§7.1", "docs/ev3-specification.md", "1. Среда", 5),
            ("sec-5-1", "§5.1", "docs/quest-specification.md", "1. Основа", 4),
        ]

    def test_local_numbers_require_document_context(self):
        self.assertEqual(docindex.locate(self.rows, "1", "ev3-specification.md"), self.rows[1:2])
        self.assertEqual(docindex.locate(self.rows, "§1", "quest-specification.md"), self.rows[2:])
        self.assertEqual(docindex.locate(self.rows, "7.1", "ev3-specification.md"), [])
        self.assertEqual(docindex.locate(self.rows, "1", "MISSING.md"), [])

    def test_legacy_lookup_keeps_exact_anchor(self):
        self.assertEqual(docindex.locate(self.rows, "7.1"), self.rows[1:2])
        self.assertEqual(docindex.locate(self.rows, "sec-7"), self.rows[:1])

    def test_merged_section_keeps_legacy_alias_without_duplicate_local_result(self):
        first = ("sec-2-1", "§2.1", "docs/product-requirements.md", "1. Цель", 10)
        alias = ("sec-2-2", "§2.2", first[2], first[3], first[4])
        self.assertEqual(docindex.locate([first, alias], "1", "product-requirements.md"), [first])
        self.assertEqual(docindex.locate([first, alias], "2.2"), [alias])
        original = '# Title\n\n<a id="sec-2-1"></a>\n<a id="sec-2-2"></a>\n## 1. Цель\n'
        toc = docindex.document_toc([first, alias], first[2])
        generated = docindex.with_document_toc(original, toc)
        self.assertIn('<a id="sec-2-1"></a>\n<a id="sec-2-2"></a>\n## 1. Цель', generated)
        self.assertEqual(docindex.with_document_toc(generated, toc), generated)

    def test_local_toc_is_idempotent_and_preserves_anchors(self):
        toc = docindex.document_toc(self.rows, "docs/ev3-specification.md")
        self.assertIn("[1. Среда](#sec-7-1)", toc)
        self.assertNotIn("sec-5-1", toc)
        original = '# EV3\n\n<a id="sec-7-1"></a>\n## 1. Среда\n\nContent\n'
        once = docindex.with_document_toc(original, toc)
        self.assertEqual(docindex.with_document_toc(once, toc), once)
        self.assertTrue(once.endswith(original[original.index('<a id='):]))

    def test_multiple_legacy_document_aliases_find_same_title(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.md"
            path.write_bytes(b'<a id="sec-1"></a>\n<a id="sec-4"></a>\n# Architecture\n')
            self.assertEqual(docindex.sections(path), [
                ("sec-1", "Architecture", 3), ("sec-4", "Architecture", 3),
            ])

    def test_consecutive_local_hierarchy_ignores_code(self):
        text = "# Title\n## 1. One\n### 1.1. Child\n```text\n# comment\n## 99. example\n```\n## 2. Two\n"
        self.assertEqual(doclint.numbering_errors(text), [])

    def test_rejects_legacy_numbers_gaps_and_missing_parents(self):
        for text in ("# Title\n## 7.1. Legacy\n", "# Title\n## 1. One\n## 3. Gap\n",
                     "# Title\n### 1.1. Missing parent\n", "# Title\n## Unnumbered\n",
                     "# Title\n# Second title\n"):
            with self.subTest(text=text):
                self.assertTrue(doclint.numbering_errors(text))

    def test_implementation_map_checks_file_and_anchor_together(self):
        known = {"ev3-specification.md#sec-7-1", "safety.md#sec-11-3"}
        check = implementation_map_check.owner_reference_errors
        self.assertEqual(check("ev3-specification.md#sec-7-1; safety.md#sec-11-3 (S20)", known), [])
        for owner in ("quest-specification.md#sec-7-1", "ev3-specification.md#sec-7-99",
                      "EV3_SPECIFICATION 7.1", ""):
            with self.subTest(owner=owner):
                self.assertTrue(check(owner, known))


if __name__ == "__main__":
    unittest.main()
