"""Offline structural wire checks; runtime alone proves native source/pin semantics."""
import copy
import json
from pathlib import Path
import unittest

import jsonschema
from referencing import Registry, Resource


class NativeFileSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.schema = json.loads((root / 'schemas/native-protocol.schema.json').read_text(encoding='utf-8'))
        evidence = json.loads((root / 'schemas/evidence.schema.json').read_text(encoding='utf-8'))
        def offline_only(_uri):
            raise AssertionError('External schema retrieval is forbidden')
        cls.registry = Registry(retrieve=offline_only).with_resources([
            ('urn:devsift:native:1', Resource.from_contents(cls.schema)),
            ('urn:devsift:evidence:1', Resource.from_contents(evidence)),
            ('evidence.schema.json', Resource.from_contents(evidence)),
        ])
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.validator = jsonschema.Draft202012Validator(cls.schema, registry=cls.registry)
        cls.diagnostic_validator = jsonschema.Draft202012Validator(
            {'$ref': 'urn:devsift:native:1#/$defs/diagnostic'}, registry=cls.registry)

    def reply(self, *, files=False):
        response = {'protocol_version': '1', 'tool_id': 'devsift-sql', 'tool_version': '1.1.0',
                    'complete': True, 'reason': 'COMPLETED', 'metadata': {'dialect': 'tsql160'}}
        if files:
            response['diagnostic_count'] = 1201
        else:
            response['diagnostics'] = [self.diagnostic()]
        return response

    def diagnostic(self):
        return {'rule_id': 'LOG002', 'region': {'start_line': 1, 'start_column': 1,
                                               'end_line': 1, 'end_column': 2}}

    def test_legacy_inline_response_keeps_existing_aggregate_limits(self):
        response = self.reply()
        response['metadata'].update(unqualified_references=1_000_000, ddl_statements=1_000_000)
        self.validator.validate(response)
        for field in ('unqualified_references', 'ddl_statements'):
            too_large = copy.deepcopy(response)
            too_large['metadata'][field] += 1
            self.assertFalse(self.validator.is_valid(too_large))
        response['diagnostics'] = [self.diagnostic()] * 1000
        self.validator.validate(response)
        response['diagnostics'].append(self.diagnostic())
        self.assertFalse(self.validator.is_valid(response))

    def test_file_summary_accepts_full_counts_without_aggregate_metadata_cap(self):
        response = self.reply(files=True)
        response['metadata'].update(unqualified_references=2_000_001, ddl_statements=10**12)
        self.validator.validate(response)
        response['diagnostic_count'] = 10**12
        self.validator.validate(response)
        response['diagnostic_count'] = 0
        self.validator.validate(response)

    def test_exactly_one_transport_shape_and_strict_summary_fields(self):
        response = self.reply(files=True)
        both = dict(response, diagnostics=[])
        neither = self.reply()
        del neither['diagnostics']
        invalid = [both, neither, dict(response, unexpected='private text')]
        invalid.extend(dict(response, diagnostic_count=value) for value in (-1, True, False, 1.5, '1201', None))
        invalid.extend(dict(response, **{field: value}) for field, value in (
            ('protocol_version', '2'), ('complete', 1), ('reason', 'UNKNOWN'),
            ('metadata', {'unknown': 1}), ('metadata', {'ddl_statements': -1}),
            ('metadata', {'unqualified_references': True}), ('metadata', {'dialect': 'unknown'})))
        for record in invalid:
            with self.subTest(record=record):
                self.assertFalse(self.validator.is_valid(record))

    def test_jsonl_item_uses_shared_local_region_contract(self):
        item = self.diagnostic()
        self.diagnostic_validator.validate(item)
        for changed in (dict(item, message='tool-controlled text'), dict(item, rule_id=1),
                        dict(item, region=dict(item['region'], end_column=0)),
                        dict(item, region=dict(item['region'], start_line=True)),
                        dict(item, region=dict(item['region'], extra=1))):
            with self.subTest(item=changed):
                self.assertFalse(self.diagnostic_validator.is_valid(changed))
        # Duplicate keys, exact source bounds/order, canonical rules, encoded
        # JSONL byte limits, count agreement and artifact pins stay runtime checks.
        self.assertEqual(self.schema['$defs']['diagnostic']['properties']['region']['$ref'],
                         'evidence.schema.json#/$defs/region')


if __name__ == '__main__':
    unittest.main()
