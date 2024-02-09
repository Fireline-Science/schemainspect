import pytest
from sqlbag import S

from schemainspect import get_inspector

CREATES = """
    create extension pg_trgm;

    create or replace function "public"."fff"(t text)
    returns TABLE(score decimal) as
    $$ select similarity('aaa', 'aaab')::decimal $$
    language SQL VOLATILE CALLED ON NULL INPUT SECURITY INVOKER;

    create view vvv as select similarity('aaa', 'aaab')::decimal as x;

    create view depends_on_fff as select * from fff('t');

    create or replace function "public"."depends_on_vvv"(t text)
    returns TABLE(score decimal) as
    $$ select * from vvv $$
    language SQL VOLATILE CALLED ON NULL INPUT SECURITY INVOKER;

    create view doubledep as
    select * from depends_on_vvv('x')
    union
    select * from depends_on_fff;
"""


def test_can_replace(db):
    with S(db) as s:
        s.execute(CREATES)

    with S(db) as s:
        s.execute("""create table t(a int, b varchar);""")
        i = get_inspector(s)
        s.execute(
            """
create or replace view vvv as select similarity('aaa', 'aaabc')::decimal as x, 1 as y;
        """
        )
        i2 = get_inspector(s)
        v1 = i.views['"public"."vvv"']
        v2 = i2.views['"public"."vvv"']
        assert v1 != v2
        assert v2.can_replace(v1)

        s.execute(
            """
            drop function "public"."fff"(t text) cascade;
        """
        )
        s.execute(
            """
            create or replace function "public"."fff"(t text)
    returns TABLE(score decimal, x integer) as
    $$ select similarity('aaa', 'aaabc')::decimal, 1 as x $$
    language SQL VOLATILE CALLED ON NULL INPUT SECURITY INVOKER;
            drop table t;
            create table t(a int, b varchar primary key not null, c int);
        """
        )
        i2 = get_inspector(s)
        f1 = i.selectables['"public"."fff"(t text)']
        f2 = i2.selectables['"public"."fff"(t text)']
        assert f1 != f2
        assert f2.can_replace(f1) is False

        t1 = i.selectables['"public"."t"']
        t2 = i2.selectables['"public"."t"']

        assert t2.can_replace(t1) is True
        assert t1.can_replace(t2) is False


def test_enum_deps(db):
    ENUM_DEP_SAMPLE = """\
create type e as enum('a', 'b', 'c');

create table t(id integer primary key, category e);

create view v as select * from t;

"""
    with S(db) as s:
        s.execute(ENUM_DEP_SAMPLE)

        i = get_inspector(s)

        e = '"public"."e"'
        t = '"public"."t"'
        v = '"public"."v"'

        assert e in i.enums

        assert i.enums[e].dependents == [t, v]
        assert e in i.selectables[t].dependent_on
        assert e in i.selectables[v].dependent_on


def test_view_deps(db):
    VIEW_DEP_SAMPLE = """\
create table foo
(
    id   serial primary key,
    name text
);

create or replace
    function f()
    returns setof foo
    security invoker
    language sql
as
$$
select *
from foo
where true;
$$;

create or replace view f_v with (security_invoker) as
select *
from f()
where true
;

comment on view f_v is 'my comment';

"""

    with S(db) as s:
        i = get_inspector(s)

        if i.pg_version < 15:
            pytest.skip("views cannot have options before pg15")

        s.execute(VIEW_DEP_SAMPLE)

        i = get_inspector(s)

        foo = '"public"."foo"'
        f = '"public"."f"()'
        f_v = '"public"."f_v"'
        co = 'view "public"."f_v"'

        assert foo in i.tables
        assert f in i.functions
        assert f_v in i.views
        assert co in i.comments

        assert i.tables[foo].dependents == [f, f_v, co]
        assert i.tables[foo].dependent_on == []
        assert i.functions[f].dependents == [f_v, co]
        assert i.functions[f].dependent_on == [foo]
        assert i.views[f_v].dependents == [co]
        assert i.views[f_v].dependent_on == [f, foo]

        assert i.views[f_v].comment == 'my comment'


def test_relationships(db):
    # commented-out dependencies are the dependencies that aren't tracked directly by postgres
    with S(db) as s:
        s.execute(CREATES)
    with S(db) as s:
        i = get_inspector(s)
        dependencies_by_name = {
            k: v.dependent_on for k, v in i.selectables.items() if v.dependent_on
        }
        assert dependencies_by_name == {
            # '"public"."depends_on_vvv"(t text)': [
            #     '"public"."vvv"'
            # ],
            '"public"."depends_on_fff"': ['"public"."fff"(t text)'],
            '"public"."doubledep"': [
                '"public"."depends_on_fff"',
                '"public"."depends_on_vvv"(t text)',
            ],
        }
        dependents_by_name = {
            k: v.dependents for k, v in i.selectables.items() if v.dependents
        }
        assert dependents_by_name == {
            # '"public"."vvv"': ['"public"."depends_on_vvv"(t text)'],
            '"public"."fff"(t text)': ['"public"."depends_on_fff"'],
            '"public"."depends_on_fff"': ['"public"."doubledep"'],
            '"public"."depends_on_vvv"(t text)': ['"public"."doubledep"'],
        }
        # testing recursive deps
        dependencies_by_name = {
            k: v.dependent_on_all
            for k, v in i.selectables.items()
            if v.dependent_on_all
        }
        assert dependencies_by_name == {
            # '"public"."depends_on_vvv"(t text)': [
            #     '"public"."vvv"'
            # ],
            '"public"."depends_on_fff"': ['"public"."fff"(t text)'],
            '"public"."doubledep"': [
                '"public"."depends_on_fff"',
                '"public"."depends_on_vvv"(t text)',
                '"public"."fff"(t text)',
            ],
            # '"public"."vvv"'
        }
        dependents_by_name = {
            k: v.dependents_all for k, v in i.selectables.items() if v.dependents_all
        }
        assert dependents_by_name == {
            # '"public"."vvv"': ['"public"."depends_on_vvv"(t text)', '"public"."doubledep"'],
            '"public"."fff"(t text)': [
                '"public"."depends_on_fff"',
                '"public"."doubledep"',
            ],
            '"public"."depends_on_fff"': ['"public"."doubledep"'],
            '"public"."depends_on_vvv"(t text)': ['"public"."doubledep"'],
        }
