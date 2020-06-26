import datetime
from decimal import Decimal
from io import BytesIO
from uuid import uuid4
import fastavro
from .conftest import assert_naive_datetime_equal_to_tz_datetime

schema = {
    "fields": [
        {
            "name": "union_uuid",
            "type": ["null", {"type": "string",
                              "logicalType": "uuid"}]
        },
        {
            "name": "array_string",
            "type": {"type": "array", "items": "string"}
        },
        {
            "name": "multi_union_time",
            "type": ["null", "string", {"type": "long",
                                        "logicalType": "timestamp-micros"}]
        },
        {
            "name": "array_bytes_decimal",
            "type": ["null", {"type": "array",
                              "items": {"type": "bytes",
                                        "logicalType": "decimal",
                                        "precision": 18,
                                        "scale": 6, }
                              }]
        },
        {
            "name": "array_fixed_decimal",
            "type": ["null", {"type": "array",
                              "items": {"type": "fixed",
                                        "name": "FixedDecimal",
                                        "size": 8,
                                        "logicalType": "decimal",
                                        "precision": 18,
                                        "scale": 6, }
                              }]
        },
        {
            "name": "array_record",
            "type": {"type": "array", "items": {
                "type": "record",
                "name": "some_record",
                "fields": [
                    {
                        "name": "f1",
                        "type": "string"
                    },
                    {
                        "name": "f2",
                        "type": {"type": "bytes",
                                 "logicalType": "decimal",
                                 "precision": 18,
                                 "scale": 6, }

                    }
                ]
            }
            }
        }, {
            "name": "array_of_unions_with_floats",
            "type": ["null", {"type": "array",
                              # The order here is chosen very carefully.
                              # We want a float before a double to ensure that
                              # our special case backwards compatibility logic
                              # is triggered, and we want a long to follow that
                              # float to ensure that integers are allowed to
                              # match the float type.
                              "items": [
                                  "float",
                                  "long",
                                  "double",
                                  "int",
                              ]
                              }]
        },
    ],
    "namespace": "namespace",
    "name": "name",
    "type": "record"
}


def serialize(schema, data):
    bytes_writer = BytesIO()
    fastavro.schemaless_writer(bytes_writer, schema, data)
    return bytes_writer.getvalue()


def deserialize(schema, binary):
    bytes_writer = BytesIO()
    bytes_writer.write(binary)
    bytes_writer.seek(0)

    res = fastavro.schemaless_reader(bytes_writer, schema)
    return res


def test_complex_schema():
    data1 = {
        'union_uuid': uuid4(),
        'array_string': ['a', "b", "c"],
        'multi_union_time': datetime.datetime.now(),
        'array_bytes_decimal': [Decimal("123.456")],
        'array_fixed_decimal': [Decimal("123.456")],
        'array_record': [{'f1': '1', 'f2': Decimal("123.456")}],
        'array_of_unions_with_floats': [],
    }
    binary = serialize(schema, data1)
    data2 = deserialize(schema, binary)
    assert len(data1) == len(data2)
    for field in [
        'array_string',
        'array_bytes_decimal',
        'array_fixed_decimal',
        'array_record',
    ]:
        assert data1[field] == data2[field]
    assert_naive_datetime_equal_to_tz_datetime(
        data1['multi_union_time'],
        data2['multi_union_time']
    )


def test_complex_schema_nulls():
    data1 = {
        'array_string': ['a', "b", "c"],
        'array_record': [{'f1': '1', 'f2': Decimal("123.456")}]
    }
    binary = serialize(schema, data1)
    data2 = deserialize(schema, binary)
    data1_compare = data1
    data1_compare.update(
        {'multi_union_time': None, 'array_bytes_decimal': None,
         'array_fixed_decimal': None, 'union_uuid': None,
         'array_of_unions_with_floats': None})
    assert (data1_compare == data2)


def test_array_from_tuple():
    data_list = serialize({"type": "array", "items": "int"}, [1, 2, 3])
    data_tuple = serialize({"type": "array", "items": "int"}, (1, 2, 3))
    assert data_list == data_tuple


def test_complex_schema_unions_with_floats():
    data1 = {
        'array_string': [],
        'array_record': [],
        'array_of_unions_with_floats': [
            1,
            2,
            3.14159265358979323846,
            9007199254740993,
        ],
    }
    binary = serialize(schema, data1)
    data2 = deserialize(schema, binary)
    data1_compare = data1
    data1_compare.update(
        {'multi_union_time': None, 'array_bytes_decimal': None,
         'array_fixed_decimal': None, 'union_uuid': None})
    # 9007199254740993 is 2**53+1, which cannot be represented precisely
    # as a floating point. fastavro allows the "float" type to match for
    # integers and "float" comes first in the union, so "float" is selected
    # and we get the nearest double available. Yes, double even though we said
    # "float", because the conversion using the python float() function, which
    # converts to a 64 bit floating point, aka a double. All of this behavior
    # is logically wrong, but backwards compatibility is king.
    data1_compare['array_of_unions_with_floats'][3] = 9007199254740992.0
    assert (data1_compare == data2)
