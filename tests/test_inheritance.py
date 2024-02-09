from sqlbag import S

from schemainspect import get_inspector

INHERITANCE = """

create table normal (id integer);

create table parent (t timestamp);

create table child (a integer, b integer) inherits (parent);
"""

COMPLEX_INHERITANCE = """

CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) NOT NULL
);

CREATE VIEW product_listings AS
SELECT product_id, product_name, price
FROM products;

CREATE OR REPLACE FUNCTION get_product_listings()
RETURNS SETOF product_listings AS $$
BEGIN
    RETURN QUERY SELECT * FROM product_listings;
END;
$$ LANGUAGE plpgsql;
"""


def test_inheritance(db):
    with S(db) as s:
        s.execute(INHERITANCE)

        ii = get_inspector(s)

        normal = ii.tables['"public"."normal"']
        parent = ii.tables['"public"."parent"']
        child = ii.tables['"public"."child"']

        assert list(normal.columns) == ["id"]
        assert list(parent.columns) == ["t"]
        assert list(child.columns) == "t a b".split()

        assert normal.columns["id"].is_inherited is False
        assert parent.columns["t"].is_inherited is False

        if ii.pg_version <= 9:
            return

        # uncertain why this fails on <=pg9 only
        assert child.columns["t"].is_inherited is True

        for c in "a b".split():
            child.columns[c].is_inherited is False

        assert parent.dependents == ['"public"."child"']
        assert child.dependent_on == ['"public"."parent"']


def test_table_dependency_order(db):
    with S(db) as s:
        i = get_inspector(s)

        if i.pg_version <= 9:
            return
        s.execute(INHERITANCE)

        ii = get_inspector(s)

        dep_order = ii.dependency_order()

        assert list(ii.tables.keys()) == [
            '"public"."child"',
            '"public"."normal"',
            '"public"."parent"',
        ]

        assert dep_order == [
            '"public"."parent"',
            '"public"."normal"',
            '"public"."child"',
        ]

def test_complex_inheritance(db):
    with S(db) as s:
        s.execute(COMPLEX_INHERITANCE)

        ii = get_inspector(s)

        assert list(ii.tables.keys()) == [
            '"public"."products"'
        ]

        assert list(ii.functions.keys()) == [
            '"public"."get_product_listings"()',
        ]

        assert list(ii.views.keys()) == [
            '"public"."product_listings"',
        ]

        ## Assert that the function depends on the view and the view depends on the table
        assert ii.functions['"public"."get_product_listings"()'].dependent_on == ['"public"."product_listings"']
        assert ii.views['"public"."product_listings"'].dependent_on == ['"public"."products"']
