with kinds as (
    select
        case c.relkind
            when 'I' then 'index'
            when 'c' then 'type'
            when 'i' then 'index'
            when 'm' then 'materialized view'
            when 'p' then 'table'
            when 'r' then 'table'
            when 's' then 'sequence'
            when 'v' then 'view'
        end as kind,
        c.oid
    from
        pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where
        n.nspname <> 'pg_catalog'
        and n.nspname <> 'information_schema'
        and pg_catalog.obj_description(c.oid, 'pg_class') is not null
),
things1 as (
  select
    oid as objid,
    pronamespace as namespace,
    proname as name,
    pg_get_function_identity_arguments(oid) as identity_arguments,
    'f' as kind,
    null as rel_object_type
  from pg_proc
  -- 11_AND_LATER where pg_proc.prokind != 'a'
  -- 10_AND_EARLIER where pg_proc.proisagg is False
  union
  select
    oid,
    relnamespace as namespace,
    relname as name,
    null as identity_arguments,
    relkind as kind,
    null as rel_object_type
  from pg_class
  where oid not in (
    select ftrelid from pg_foreign_table
  )
  union
  select
    oid,
    typnamespace as namespace,
    CASE
        WHEN typcategory = 'A' AND typname LIKE '\_%' THEN SUBSTRING(typname FROM 2)
        ELSE typname
    END as name,
    null as identity_arguments,
    't' as kind,
    null as rel_object_type
  from pg_type
  union
  select
    objoid,
    relnamespace as namespace,
    pc.relname as name,
    null as identity_arguments,
    'd' as kind,
    k.kind as rel_object_type
  from pg_description d
  join pg_class pc
    on d.objoid = pc.oid
  join kinds k
    on d.objoid = k.oid
),
extension_objids as (
  select
      objid as extension_objid
  from
      pg_depend d
  WHERE
      d.refclassid = 'pg_extension'::regclass
    union
    select
        t.typrelid as extension_objid
    from
        pg_depend d
        join pg_type t on t.oid = d.objid
    where
        d.refclassid = 'pg_extension'::regclass
),
things as (
    select
      objid,
      kind,
      n.nspname as schema,
      name,
      identity_arguments,
      rel_object_type
    from things1 t
    inner join pg_namespace n
      on t.namespace = n.oid
    left outer join extension_objids
      on t.objid = extension_objids.extension_objid
    where
      kind in ('r', 'v', 'm', 'c', 'f', 't', 'd') and
      nspname not in ('pg_internal', 'pg_catalog', 'information_schema', 'pg_toast')
      and nspname not like 'pg_temp_%' and nspname not like 'pg_toast_temp_%'
      and extension_objids.extension_objid is null
),
combined as (
  select distinct * from (
  select
    t.objid,
    t.schema,
    t.name,
    t.identity_arguments,
    t.kind,
    t.rel_object_type,
    things_dependent_on.objid as objid_dependent_on,
    things_dependent_on.schema as schema_dependent_on,
    things_dependent_on.name as name_dependent_on,
    things_dependent_on.identity_arguments as identity_arguments_dependent_on,
    things_dependent_on.kind as kind_dependent_on
  FROM
      pg_depend d
      inner join things things_dependent_on
        on d.refobjid = things_dependent_on.objid
      inner join pg_rewrite rw
        on d.objid = rw.oid
        and things_dependent_on.objid != rw.ev_class
        and rw.rulename = '_RETURN'
      inner join things t
        on rw.ev_class = t.objid
  where
    d.deptype in ('n')
  UNION
  select distinct
    t.objid,
    t.schema,
    t.name,
    t.identity_arguments,
    t.kind,
    t.rel_object_type,
    things_dependent_on.objid as objid_dependent_on,
    things_dependent_on.schema as schema_dependent_on,
    things_dependent_on.name as name_dependent_on,
    things_dependent_on.identity_arguments as identity_arguments_dependent_on,
    things_dependent_on.kind as kind_dependent_on
  FROM
      pg_depend d
      inner join things things_dependent_on
        on d.refobjid = things_dependent_on.objid
      inner join things t
        on d.objid = t.objid
  where
    d.deptype in ('n','t','d')
  ) as subquery
)
select * from combined
order by
schema, name, identity_arguments, kind_dependent_on,
schema_dependent_on, name_dependent_on, identity_arguments_dependent_on
